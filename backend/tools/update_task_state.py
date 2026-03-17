from __future__ import annotations

import uuid

from sqlalchemy import select

from db.connection import db_manager
from db.models import Session, TaskState


def _uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    return uuid.UUID(value)


async def update_task_state(
    session_id: str,
    goal: str | None = None,
    current_step: str | None = None,
    active_plan_id: str | None = None,
    scratchpad_summary: str | None = None,
) -> dict:
    session_uuid = _uuid(session_id)
    assert session_uuid is not None

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")

        task_state = await session.scalar(
            select(TaskState).where(TaskState.session_id == session_uuid)
        )
        if task_state is None:
            task_state = TaskState(session_id=session_uuid)
            session.add(task_state)

        if goal is not None:
            task_state.goal = goal
        if current_step is not None:
            task_state.current_step = current_step
        if active_plan_id is not None:
            task_state.active_plan_id = _uuid(active_plan_id)
        if scratchpad_summary is not None:
            task_state.scratchpad_summary = scratchpad_summary

        await session.commit()
        await session.refresh(task_state)

        return {
            "updated": True,
            "updated_at": task_state.updated_at.isoformat(),
        }
