from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select

from db.connection import db_manager
from db.enums import (
    ActionStatus,
    ActionType,
    EventType,
    OutcomeType,
    PlanStatus,
    SessionState,
)
from db.models import (
    FileEntity,
    FolderEntity,
    MemoryEvent,
    Plan,
    PlanAction,
    Session,
    TaskState,
)
from db.utils import recompute_plan_status
from safety.sandbox import sandbox_service


def _to_iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _path_state(path: Path | None) -> dict | None:
    if path is None:
        return None

    metadata = sandbox_service.metadata_for_path(path)
    return {
        "path": metadata.canonical_path,
        "filename": metadata.filename,
        "extension": metadata.extension,
        "size_bytes": metadata.size_bytes,
        "modified_at": _to_iso(metadata.modified_at),
        "exists": metadata.exists,
        "is_dir": metadata.is_dir,
    }


def _event_type_for_action(action_type: ActionType) -> EventType:
    mapping = {
        ActionType.RENAME: EventType.RENAME,
        ActionType.MOVE: EventType.MOVE,
        ActionType.ARCHIVE: EventType.ARCHIVE,
        ActionType.CLASSIFY: EventType.CLASSIFY,
        # Phase 1 event ledger has no CREATE_FOLDER event type.
        ActionType.CREATE_FOLDER: EventType.PLAN,
    }
    return mapping[action_type]


async def _update_entity_after_execution(
    session,
    action: PlanAction,
    session_row: Session,
    destination: Path | None,
) -> None:
    if session_row.device_id is None:
        return

    if action.action_type in {ActionType.RENAME, ActionType.MOVE, ActionType.ARCHIVE}:
        if action.target_id is None or destination is None:
            return

        if action.target_type == "file":
            entity = await session.get(FileEntity, action.target_id)
            if entity is None:
                return
            metadata = sandbox_service.metadata_for_path(destination)
            entity.canonical_path = str(destination)
            entity.filename = destination.name
            entity.extension = metadata.extension
            entity.mime_type = metadata.mime_type
            entity.size_bytes = metadata.size_bytes
            entity.modified_at = metadata.modified_at
            entity.created_at_fs = metadata.created_at_fs
            entity.exists_now = metadata.exists
        else:
            entity = await session.get(FolderEntity, action.target_id)
            if entity is None:
                return
            entity.canonical_path = str(destination)
            entity.folder_name = destination.name or destination.anchor
            entity.parent_path = str(destination.parent) if destination != sandbox_service.root else None
            entity.exists_now = destination.exists()

    if action.action_type == ActionType.CREATE_FOLDER and destination is not None:
        existing = await session.scalar(
            select(FolderEntity).where(
                FolderEntity.device_id == session_row.device_id,
                FolderEntity.canonical_path == str(destination),
            )
        )
        if existing is None:
            session.add(
                FolderEntity(
                    device_id=session_row.device_id,
                    canonical_path=str(destination),
                    folder_name=destination.name or destination.anchor,
                    parent_path=str(destination.parent) if destination != sandbox_service.root else None,
                    exists_now=True,
                    metadata_json={"created_via": "execute_action"},
                )
            )
        else:
            existing.exists_now = True
            existing.folder_name = destination.name or destination.anchor
            existing.parent_path = str(destination.parent) if destination != sandbox_service.root else None
            existing.metadata_json = {"created_via": "execute_action"}


async def execute_action(action_id: str) -> dict:
    action_uuid = uuid.UUID(action_id)

    async with db_manager.session() as session:
        action = await session.get(PlanAction, action_uuid)
        if action is None:
            raise ValueError(f"Action not found: {action_id}")

        if action.status != ActionStatus.APPROVED:
            return {
                "action_id": action_id,
                "outcome": OutcomeType.FAILED.value,
                "error": "Action must have status APPROVED before execution.",
            }

        plan = await session.get(Plan, action.plan_id)
        if plan is None:
            raise ValueError(f"Plan not found for action: {action_id}")

        session_row = await session.get(Session, plan.session_id)
        if session_row is None:
            raise ValueError(f"Session not found for plan: {plan.id}")

        task_state = await session.scalar(
            select(TaskState).where(TaskState.session_id == session_row.id)
        )
        if task_state is not None:
            task_state.current_step = SessionState.EXECUTING.value

        payload = action.action_payload_json or {}
        source_path: Path | None = None
        destination_path: Path | None = None
        pre_state: dict | None = None

        try:
            # Validate required payload keys upfront — give a clean error rather than KeyError.
            if action.action_type in {ActionType.RENAME, ActionType.MOVE, ActionType.ARCHIVE}:
                if not payload.get("from_path"):
                    raise ValueError(
                        f"Action payload missing 'from_path' for {action.action_type.value}. "
                        "The model must include from_path in action_payload."
                    )
            if action.action_type in {ActionType.RENAME, ActionType.MOVE}:
                if not payload.get("to_path"):
                    raise ValueError(
                        f"Action payload missing 'to_path' for {action.action_type.value}. "
                        "The model must include to_path in action_payload."
                    )
            if action.action_type == ActionType.CREATE_FOLDER:
                if not payload.get("path"):
                    raise ValueError(
                        "Action payload missing 'path' for CREATE_FOLDER. "
                        "The model must include path in action_payload."
                    )

            if action.action_type in {ActionType.RENAME, ActionType.MOVE, ActionType.ARCHIVE}:
                source_path = sandbox_service.resolve_path(payload["from_path"])
                if not source_path.exists():
                    raise FileNotFoundError(f"Source path does not exist: {source_path}")
                # Validate that file-only operations aren't applied to directories
                if action.action_type == ActionType.RENAME and source_path.is_dir():
                    raise ValueError(
                        f"RENAME cannot be applied to a directory: {source_path}. "
                        "Use MOVE for folders."
                    )
                pre_state = _path_state(source_path)

            if action.action_type in {ActionType.RENAME, ActionType.MOVE}:
                destination_path = sandbox_service.resolve_path(payload["to_path"])
                pre_state = pre_state or _path_state(destination_path)
                # Guard: don't move a directory to a path that looks like a file (has an extension)
                if source_path is not None and source_path.is_dir() and destination_path.suffix:
                    raise ValueError(
                        f"Cannot move directory {source_path} to {destination_path}: "
                        "destination has a file extension, which would corrupt the folder structure. "
                        "Use a destination path without an extension for folder moves."
                    )
                if destination_path.exists():
                    raise FileExistsError(f"Destination already exists: {destination_path}")
                sandbox_service.move_path(source_path, destination_path)

            elif action.action_type == ActionType.CREATE_FOLDER:
                destination_path = sandbox_service.resolve_path(payload["path"])
                pre_state = _path_state(destination_path)
                sandbox_service.create_folder(destination_path)

            elif action.action_type == ActionType.ARCHIVE:
                destination_path = sandbox_service.archive_destination(source_path)
                if destination_path.exists():
                    raise FileExistsError(f"Archive destination already exists: {destination_path}")
                sandbox_service.move_path(source_path, destination_path)

            elif action.action_type == ActionType.CLASSIFY:
                destination_path = None
                pre_state = {"classification": payload}

            post_state = (
                _path_state(destination_path)
                if destination_path is not None
                else {"classification": payload}
            )

            action.status = ActionStatus.EXECUTED
            action.result_json = {
                "outcome": OutcomeType.SUCCESS.value,
                "pre_state": pre_state,
                "post_state": post_state,
            }

            await _update_entity_after_execution(
                session=session,
                action=action,
                session_row=session_row,
                destination=destination_path,
            )

            memory_event = MemoryEvent(
                user_id=session_row.user_id,
                device_id=session_row.device_id,
                session_id=session_row.id,
                event_type=_event_type_for_action(action.action_type),
                scope_type=action.target_type,
                scope_id=action.target_id,
                pre_state_json=pre_state,
                intended_change_json=payload,
                action_taken_json={"action_type": action.action_type.value},
                post_state_json=post_state,
                outcome=OutcomeType.SUCCESS,
                notes=None,
            )
            session.add(memory_event)

            plan.status = await recompute_plan_status(session, plan.id)
            if task_state is not None:
                task_state.current_step = (
                    SessionState.COMPLETE.value
                    if plan.status == PlanStatus.EXECUTED
                    else SessionState.EXECUTING.value
                )

            await session.flush()
            await session.commit()

            return {
                "action_id": str(action.id),
                "outcome": OutcomeType.SUCCESS.value,
                "pre_state": pre_state,
                "post_state": post_state,
                "memory_event_id": str(memory_event.id),
            }

        except Exception as exc:
            action.status = ActionStatus.FAILED
            action.result_json = {
                "outcome": OutcomeType.FAILED.value,
                "error": str(exc),
            }

            failure_event = MemoryEvent(
                user_id=session_row.user_id,
                device_id=session_row.device_id,
                session_id=session_row.id,
                event_type=EventType.FAILURE,
                scope_type=action.target_type,
                scope_id=action.target_id,
                pre_state_json=pre_state or _path_state(source_path),
                intended_change_json=payload,
                action_taken_json={"action_type": action.action_type.value},
                post_state_json=_path_state(destination_path),
                outcome=OutcomeType.FAILED,
                notes=str(exc),
            )
            session.add(failure_event)

            plan.status = await recompute_plan_status(session, plan.id)
            if task_state is not None:
                task_state.current_step = SessionState.ERROR.value

            await session.commit()

            return {
                "action_id": str(action.id),
                "outcome": OutcomeType.FAILED.value,
                "error": str(exc),
            }
