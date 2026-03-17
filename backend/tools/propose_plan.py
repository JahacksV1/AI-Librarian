from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from db.connection import db_manager
from db.enums import ActionStatus, ActionType, PlanStatus, SessionState
from db.models import FileEntity, FolderEntity, Plan, PlanAction, Session, TaskState


async def _resolve_target_id(
    session,
    device_id: uuid.UUID | None,
    target_type: str,
    target_path: str,
) -> uuid.UUID | None:
    if device_id is None:
        return None

    model = FileEntity if target_type == "file" else FolderEntity
    target = await session.scalar(
        select(model).where(
            model.device_id == device_id,
            model.canonical_path == target_path,
        )
    )
    return target.id if target is not None else None


async def propose_plan(
    session_id: str,
    goal: str,
    rationale_summary: str,
    actions: list[dict[str, Any]],
) -> dict:
    session_uuid = uuid.UUID(session_id)

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")

        plan = Plan(
            session_id=session_uuid,
            goal=goal,
            rationale_summary=rationale_summary,
            plan_json={
                "goal": goal,
                "rationale_summary": rationale_summary,
                "actions": actions,
            },
            status=PlanStatus.PENDING,
        )
        session.add(plan)
        await session.flush()

        action_rows: list[PlanAction] = []
        for action in actions:
            action_type = ActionType(action["action_type"])
            target_type = action["target_type"]
            target_path = action.get("target_path", "")
            target_id = await _resolve_target_id(
                session=session,
                device_id=session_row.device_id,
                target_type=target_type,
                target_path=target_path,
            )

            action_row = PlanAction(
                plan_id=plan.id,
                action_type=action_type,
                target_type=target_type,
                target_id=target_id,
                action_payload_json=action.get("action_payload", {}),
                requires_approval=True,
                status=ActionStatus.PENDING,
            )
            session.add(action_row)
            action_rows.append(action_row)

        task_state = await session.scalar(
            select(TaskState).where(TaskState.session_id == session_uuid)
        )
        if task_state is None:
            task_state = TaskState(session_id=session_uuid)
            session.add(task_state)

        task_state.goal = goal
        task_state.active_plan_id = plan.id
        task_state.current_step = SessionState.AWAITING_APPROVAL.value
        task_state.pending_action_ids_json = []
        task_state.scratchpad_summary = rationale_summary

        await session.flush()
        task_state.pending_action_ids_json = [str(action_row.id) for action_row in action_rows]

        await session.commit()

        return {
            "plan_id": str(plan.id),
            "action_count": len(action_rows),
            "status": PlanStatus.PENDING.value,
        }
