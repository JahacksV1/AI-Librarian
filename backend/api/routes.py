from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from agent.loop import _get_mcp_client, run_agent_loop
from api.sse import action_executed_event, error_event, execution_complete_event, from_payload
from config import settings
from db.connection import db_manager
from db.enums import ActionStatus, PlanStatus, SessionMode, SessionState, SessionStatus
from db.models import Device, FileEntity, Plan, PlanAction, Session, SessionMessage, TaskState
from db.utils import recompute_plan_status
from tools.scan_folder import scan_folder

router = APIRouter()


class CreateSessionRequest(BaseModel):
    user_id: str
    mode: SessionMode = SessionMode.CHAT
    title: str | None = None
    device_id: str | None = None


class UpdateSessionRequest(BaseModel):
    status: SessionStatus | None = None
    title: str | None = None


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)


class UpdateActionRequest(BaseModel):
    status: ActionStatus


class ScanRequest(BaseModel):
    path: str
    session_id: str
    recursive: bool = True


def _session_payload(session_row: Session) -> dict[str, Any]:
    return {
        "id": str(session_row.id),
        "user_id": str(session_row.user_id),
        "device_id": str(session_row.device_id) if session_row.device_id else None,
        "mode": session_row.mode.value,
        "status": session_row.status.value,
        "title": session_row.title,
        "started_at": session_row.started_at.isoformat() if session_row.started_at else None,
        "ended_at": session_row.ended_at.isoformat() if session_row.ended_at else None,
        "summary": session_row.summary,
        "updated_at": session_row.updated_at.isoformat() if session_row.updated_at else None,
    }


def _message_payload(message: SessionMessage) -> dict[str, Any]:
    return {
        "id": str(message.id),
        "role": message.role.value,
        "content": message.content,
        "tool_name": message.tool_name,
        "tool_call_id": message.tool_call_id,
        "metadata_json": message.metadata_json,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _action_payload(action: PlanAction) -> dict[str, Any]:
    return {
        "id": str(action.id),
        "plan_id": str(action.plan_id),
        "action_type": action.action_type.value,
        "target_type": action.target_type,
        "target_id": str(action.target_id) if action.target_id else None,
        "action_payload_json": action.action_payload_json,
        "requires_approval": action.requires_approval,
        "status": action.status.value,
        "result_json": action.result_json,
        "created_at": action.created_at.isoformat() if action.created_at else None,
        "updated_at": action.updated_at.isoformat() if action.updated_at else None,
    }


def _plan_payload(plan: Plan, actions: list[PlanAction] | None = None) -> dict[str, Any]:
    payload = {
        "id": str(plan.id),
        "session_id": str(plan.session_id),
        "plan_type": plan.plan_type,
        "goal": plan.goal,
        "plan_json": plan.plan_json,
        "rationale_summary": plan.rationale_summary,
        "status": plan.status.value,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "updated_at": plan.updated_at.isoformat() if plan.updated_at else None,
    }
    if actions is not None:
        payload["actions"] = [_action_payload(action) for action in actions]
    return payload



def _validate_action_update_status(status_value: ActionStatus) -> None:
    if status_value not in {ActionStatus.APPROVED, ActionStatus.REJECTED}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only APPROVED or REJECTED are allowed for action updates.",
        )


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(body: CreateSessionRequest) -> dict[str, Any]:
    try:
        user_uuid = uuid.UUID(body.user_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid user_id UUID.") from exc

    device_uuid: uuid.UUID | None = None
    if body.device_id:
        try:
            device_uuid = uuid.UUID(body.device_id)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid device_id UUID.") from exc

    async with db_manager.session() as session:
        if device_uuid is None:
            default_device = await session.scalar(
                select(Device)
                .where(Device.user_id == user_uuid)
                .order_by(Device.created_at.asc(), Device.id.asc())
            )
            device_uuid = default_device.id if default_device else None
        else:
            device_row = await session.get(Device, device_uuid)
            if device_row is None or device_row.user_id != user_uuid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="device_id does not belong to user_id or does not exist.",
                )

        session_row = Session(
            user_id=user_uuid,
            device_id=device_uuid,
            mode=body.mode,
            status=SessionStatus.ACTIVE,
            title=body.title,
        )
        session.add(session_row)
        await session.flush()

        session.add(
            TaskState(
                session_id=session_row.id,
                current_step=SessionState.IDLE.value,
            )
        )

        await session.commit()
        await session.refresh(session_row)

    return _session_payload(session_row)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict[str, Any]:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id UUID.") from exc

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

    return _session_payload(session_row)


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, body: UpdateSessionRequest) -> dict[str, Any]:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id UUID.") from exc

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        if body.status is not None:
            session_row.status = body.status
            if body.status in {SessionStatus.COMPLETED, SessionStatus.FAILED}:
                session_row.ended_at = datetime.now(timezone.utc)
        if body.title is not None:
            session_row.title = body.title

        await session.commit()
        await session.refresh(session_row)

    return {
        "id": str(session_row.id),
        "status": session_row.status.value,
        "updated_at": session_row.updated_at.isoformat() if session_row.updated_at else None,
    }


@router.post("/sessions/{session_id}/messages")
async def send_session_message(session_id: str, body: SendMessageRequest) -> StreamingResponse:
    try:
        uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id UUID.") from exc

    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def _event_callback(payload: dict[str, Any]) -> None:
        await queue.put(payload)

    async def _run_loop() -> None:
        try:
            await run_agent_loop(
                session_id=session_id,
                user_message=body.content,
                event_callback=_event_callback,
            )
        except Exception as exc:
            await queue.put({"type": "error", "message": "Agent loop failed", "detail": str(exc)})
        finally:
            await queue.put(None)

    asyncio.create_task(_run_loop())

    async def _event_stream():
        while True:
            payload = await queue.get()
            if payload is None:
                break
            yield from_payload(payload)

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str) -> dict[str, Any]:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id UUID.") from exc

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        messages = list(
            await session.scalars(
                select(SessionMessage)
                .where(SessionMessage.session_id == session_uuid)
                .order_by(SessionMessage.created_at.asc(), SessionMessage.id.asc())
            )
        )

    return {"messages": [_message_payload(message) for message in messages]}


@router.get("/sessions/{session_id}/plans")
async def list_session_plans(session_id: str) -> dict[str, Any]:
    try:
        session_uuid = uuid.UUID(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session_id UUID.") from exc

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")

        plans = list(
            await session.scalars(
                select(Plan)
                .where(Plan.session_id == session_uuid)
                .order_by(Plan.created_at.desc(), Plan.id.desc())
            )
        )

    return {"plans": [_plan_payload(plan) for plan in plans]}


@router.get("/plans/{plan_id}")
async def get_plan(plan_id: str) -> dict[str, Any]:
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan_id UUID.") from exc

    async with db_manager.session() as session:
        plan_row = await session.get(Plan, plan_uuid)
        if plan_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

        actions = list(
            await session.scalars(
                select(PlanAction)
                .where(PlanAction.plan_id == plan_uuid)
                .order_by(PlanAction.created_at.asc(), PlanAction.id.asc())
            )
        )

    return _plan_payload(plan_row, actions=actions)


@router.patch("/actions/{action_id}")
async def patch_action(action_id: str, body: UpdateActionRequest) -> dict[str, Any]:
    _validate_action_update_status(body.status)
    try:
        action_uuid = uuid.UUID(action_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action_id UUID.") from exc

    async with db_manager.session() as session:
        action_row = await session.get(PlanAction, action_uuid)
        if action_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found.")
        if action_row.status not in {ActionStatus.PENDING, ActionStatus.APPROVED, ActionStatus.REJECTED}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Cannot update action in status {action_row.status.value}.",
            )

        action_row.status = body.status

        plan_row = await session.get(Plan, action_row.plan_id)
        if plan_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found for action.")
        plan_row.status = await recompute_plan_status(session, plan_row.id)

        await session.commit()
        await session.refresh(action_row)

    return {
        "id": str(action_row.id),
        "status": action_row.status.value,
        "updated_at": action_row.updated_at.isoformat() if action_row.updated_at else None,
    }


@router.post("/plans/{plan_id}/approve-all")
async def approve_all_plan_actions(plan_id: str) -> dict[str, Any]:
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan_id UUID.") from exc

    async with db_manager.session() as session:
        plan_row = await session.get(Plan, plan_uuid)
        if plan_row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found.")

        pending_actions = list(
            await session.scalars(
                select(PlanAction).where(
                    PlanAction.plan_id == plan_uuid,
                    PlanAction.status == ActionStatus.PENDING,
                )
            )
        )

        for action in pending_actions:
            action.status = ActionStatus.APPROVED

        plan_row.status = await recompute_plan_status(session, plan_row.id)
        await session.commit()

    return {"approved_count": len(pending_actions), "plan_id": str(plan_uuid)}


@router.post("/plans/{plan_id}/execute")
async def execute_plan(plan_id: str) -> StreamingResponse:
    try:
        plan_uuid = uuid.UUID(plan_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid plan_id UUID.") from exc

    async def _event_stream():
        succeeded = 0
        failed = 0

        async with db_manager.session() as session:
            plan_row = await session.get(Plan, plan_uuid)
            if plan_row is None:
                yield error_event("Plan not found", f"plan_id={plan_id}")
                return

            approved_actions = list(
                await session.scalars(
                    select(PlanAction)
                    .where(
                        PlanAction.plan_id == plan_uuid,
                        PlanAction.status == ActionStatus.APPROVED,
                    )
                    .order_by(PlanAction.created_at.asc(), PlanAction.id.asc())
                )
            )

        if not approved_actions:
            yield error_event(
                "No approved actions",
                "Cannot execute plan because no actions are in APPROVED status.",
            )
            return

        for action in approved_actions:
            mcp_client = _get_mcp_client()
            async with mcp_client:
                call_result = await mcp_client.call_tool(
                    "execute_action",
                    arguments={"action_id": str(action.id)},
                )
            # Unwrap FastMCP result envelope
            if hasattr(call_result, "data") and isinstance(call_result.data, dict):
                result = call_result.data
            elif isinstance(call_result, dict):
                result = call_result
            else:
                result = {"outcome": "FAILED", "error": str(call_result)}
            outcome = str(result.get("outcome", "FAILED"))
            if outcome == "SUCCESS":
                succeeded += 1
            else:
                failed += 1

            yield action_executed_event(
                action_id=str(action.id),
                outcome=outcome,
                action_type=action.action_type.value,
            )

        async with db_manager.session() as session:
            plan_row = await session.get(Plan, plan_uuid)
            if plan_row is not None:
                task_state = await session.scalar(
                    select(TaskState).where(TaskState.session_id == plan_row.session_id)
                )
                if task_state is not None:
                    if succeeded > 0 and failed > 0:
                        task_state.current_step = SessionState.COMPLETE.value
                    elif failed > 0:
                        task_state.current_step = SessionState.ERROR.value
                    else:
                        task_state.current_step = SessionState.COMPLETE.value
                await session.commit()

        yield execution_complete_event(str(plan_uuid), succeeded, failed)

    return StreamingResponse(_event_stream(), media_type="text/event-stream")


@router.post("/scan")
async def scan_filesystem(body: ScanRequest) -> dict[str, Any]:
    result = await scan_folder(
        path=body.path,
        recursive=body.recursive,
        session_id=body.session_id,
    )
    return {
        "files_found": len(result.get("files", [])),
        "folders_found": len(result.get("folders", [])),
        "session_id": body.session_id,
        "scan_completed_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/files")
async def list_files(
    device_id: str | None = Query(default=None),
    path_prefix: str | None = Query(default=None),
    exists_now: bool = Query(default=True),
) -> dict[str, Any]:
    filters = [FileEntity.exists_now.is_(exists_now)]

    if device_id is not None:
        try:
            filters.append(FileEntity.device_id == uuid.UUID(device_id))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid device_id UUID.") from exc

    if path_prefix:
        filters.append(FileEntity.canonical_path.like(f"{path_prefix}%"))

    async with db_manager.session() as session:
        file_rows = list(
            await session.scalars(
                select(FileEntity)
                .where(*filters)
                .order_by(FileEntity.canonical_path.asc(), FileEntity.id.asc())
            )
        )

    return {
        "files": [
            {
                "id": str(file_row.id),
                "canonical_path": file_row.canonical_path,
                "filename": file_row.filename,
                "extension": file_row.extension,
                "size_bytes": file_row.size_bytes,
                "exists_now": file_row.exists_now,
                "modified_at": file_row.modified_at.isoformat() if file_row.modified_at else None,
            }
            for file_row in file_rows
        ]
    }


@router.get("/health")
async def health() -> dict[str, Any]:
    db_status = "connected"
    try:
        await db_manager.healthcheck()
    except Exception:
        db_status = "disconnected"

    provider = settings.model_provider.lower()
    model_status = "unknown"

    if provider == "ollama":
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{settings.ollama_url.rstrip('/')}/api/tags")
                response.raise_for_status()
            model_status = "reachable"
        except Exception:
            model_status = "unreachable"
    elif provider == "anthropic":
        model_status = "configured" if settings.anthropic_api_key else "missing_api_key"
    elif provider == "openai":
        model_status = "configured" if settings.openai_api_key else "missing_api_key"

    healthy = db_status == "connected" and model_status in ("reachable", "configured")
    overall_status = "ok" if healthy else "degraded"

    result: dict[str, Any] = {
        "status": overall_status,
        "db": db_status,
        "model_provider": provider,
        "model_name": settings.effective_model_name,
        "model_status": model_status,
    }

    if provider == "ollama":
        result["ollama"] = model_status

    return result
