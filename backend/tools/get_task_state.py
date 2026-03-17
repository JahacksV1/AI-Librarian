from __future__ import annotations

import uuid

from sqlalchemy import select

from db.connection import db_manager
from db.models import TaskState


def _uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)


async def get_task_state(session_id: str) -> dict:
    session_uuid = _uuid(session_id)

    async with db_manager.session() as session:
        task_state = await session.scalar(
            select(TaskState).where(TaskState.session_id == session_uuid)
        )

        if task_state is None:
            return {
                "goal": None,
                "current_step": None,
                "active_plan_id": None,
                "scratchpad_summary": None,
            }

        return {
            "goal": task_state.goal,
            "current_step": task_state.current_step,
            "active_plan_id": str(task_state.active_plan_id) if task_state.active_plan_id else None,
            "scratchpad_summary": task_state.scratchpad_summary,
        }
