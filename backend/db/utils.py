from __future__ import annotations

from sqlalchemy import select

from db.enums import ActionStatus, PlanStatus
from db.models import PlanAction
import uuid


async def recompute_plan_status(session, plan_id: uuid.UUID) -> PlanStatus:
    """Derive the aggregate plan status from the current statuses of all its actions.

    This is the single authoritative implementation — imported by both
    tools/execute_action.py and api/routes.py so they can never diverge.
    """
    await session.flush()
    actions = list(
        await session.scalars(select(PlanAction).where(PlanAction.plan_id == plan_id))
    )
    statuses = {action.status for action in actions}

    if not statuses:
        return PlanStatus.PENDING
    if statuses == {ActionStatus.REJECTED}:
        return PlanStatus.REJECTED
    if statuses == {ActionStatus.EXECUTED}:
        return PlanStatus.EXECUTED
    if ActionStatus.EXECUTED in statuses:
        return PlanStatus.PARTIAL
    if ActionStatus.FAILED in statuses or ActionStatus.SKIPPED in statuses:
        return PlanStatus.PARTIAL
    if ActionStatus.REJECTED in statuses:
        return PlanStatus.PARTIAL
    if statuses.issubset({ActionStatus.APPROVED}):
        return PlanStatus.APPROVED
    return PlanStatus.PENDING
