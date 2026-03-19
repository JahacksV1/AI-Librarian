from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select

from db.connection import db_manager
from db.enums import ActionStatus, ActionType, OutcomeType, PlanStatus, SessionState
from db.models import FileEntity, FolderEntity, MemoryEvent, Plan, PlanAction, Session, TaskState


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

        task_state = await session.scalar(
            select(TaskState).where(TaskState.session_id == session_uuid)
        )

        # Guard 1: reject if a non-final plan is already active for this session.
        # This prevents the model from stacking plans when one is already awaiting approval.
        if task_state is not None and task_state.active_plan_id is not None:
            existing_plan = await session.get(Plan, task_state.active_plan_id)
            if existing_plan is not None and existing_plan.status not in {
                PlanStatus.EXECUTED,
                PlanStatus.REJECTED,
            }:
                return {
                    "error": (
                        f"A plan is already active for this session "
                        f"(plan_id={existing_plan.id}, status={existing_plan.status.value}). "
                        "Ask the user to approve, reject, or complete the existing plan before creating a new one."
                    ),
                    "existing_plan_id": str(existing_plan.id),
                    "existing_plan_status": existing_plan.status.value,
                }

        # Guard 2: collect paths that were already successfully moved/renamed in this session.
        # The model should not include these as source paths in a new plan.
        executed_source_paths: set[str] = set()
        recent_events = list(
            await session.scalars(
                select(MemoryEvent).where(
                    MemoryEvent.session_id == session_uuid,
                    MemoryEvent.outcome == OutcomeType.SUCCESS,
                )
            )
        )
        for event in recent_events:
            if event.pre_state_json and isinstance(event.pre_state_json, dict):
                pre_path = event.pre_state_json.get("path")
                if pre_path:
                    executed_source_paths.add(pre_path)

        # Guard 3: validate each action's source path against already-executed paths.
        flagged_actions: list[str] = []
        for action in actions:
            action_type_str = action.get("action_type", "")
            payload = action.get("action_payload", {})
            from_path = payload.get("from_path")
            if from_path and from_path in executed_source_paths:
                flagged_actions.append(
                    f"{action_type_str} on {from_path} — this file was already moved in this session"
                )

        if flagged_actions:
            return {
                "error": (
                    "One or more proposed actions target files that were already moved in this session. "
                    "Call scan_folder again to get the current file locations before proposing a new plan."
                ),
                "flagged_actions": flagged_actions,
            }

        # Guard 4: validate required payload fields per action_type.
        # The model frequently omits required fields — catch this before writing to DB
        # so the error is returned to the model rather than failing silently at execution time.
        payload_errors: list[str] = []
        for i, action in enumerate(actions):
            action_type_str = action.get("action_type", "")
            payload = action.get("action_payload", {})
            if not isinstance(payload, dict):
                payload_errors.append(f"Action {i} ({action_type_str}): action_payload must be a dict, got {type(payload).__name__}")
                continue

            if action_type_str in {"RENAME", "MOVE"}:
                if not payload.get("from_path"):
                    payload_errors.append(f"Action {i} ({action_type_str}): action_payload must include 'from_path'")
                if not payload.get("to_path"):
                    payload_errors.append(f"Action {i} ({action_type_str}): action_payload must include 'to_path'")
            elif action_type_str == "CREATE_FOLDER":
                if not payload.get("path"):
                    payload_errors.append(f"Action {i} (CREATE_FOLDER): action_payload must include 'path' — the absolute path of the folder to create")
            elif action_type_str == "ARCHIVE":
                if not payload.get("from_path"):
                    payload_errors.append(f"Action {i} (ARCHIVE): action_payload must include 'from_path'")

        if payload_errors:
            return {
                "error": (
                    "One or more actions have missing required payload fields. "
                    "Fix the actions and call propose_plan again."
                ),
                "payload_errors": payload_errors,
            }

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
