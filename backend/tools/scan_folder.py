from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select

from db.connection import db_manager
from db.models import Device, FileEntity, FolderEntity, Session
from safety.sandbox import sandbox_service


def _to_iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _folder_payload(folder: FolderEntity) -> dict:
    return {
        "id": str(folder.id),
        "canonical_path": folder.canonical_path,
        "folder_name": folder.folder_name,
        "parent_path": folder.parent_path,
    }


def _file_payload(file_entity: FileEntity) -> dict:
    return {
        "id": str(file_entity.id),
        "canonical_path": file_entity.canonical_path,
        "filename": file_entity.filename,
        "extension": file_entity.extension,
        "size_bytes": file_entity.size_bytes,
        "modified_at": _to_iso(file_entity.modified_at),
    }


async def scan_folder(path: str, recursive: bool = True, session_id: str = "") -> dict:
    session_uuid = uuid.UUID(session_id)
    directory = sandbox_service.resolve_directory(path)
    file_paths, folder_paths = sandbox_service.scan_paths(directory, recursive=recursive)
    seen_at = datetime.now(timezone.utc)

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")
        if session_row.device_id is None:
            raise ValueError("Session has no device_id; scan_folder requires a device-bound session.")

        device = await session.get(Device, session_row.device_id)
        if device is None:
            raise ValueError("Session device_id is set, but device row does not exist.")

        folder_entities: list[FolderEntity] = []
        for folder_path in folder_paths:
            existing_folder = await session.scalar(
                select(FolderEntity).where(
                    FolderEntity.device_id == device.id,
                    FolderEntity.canonical_path == str(folder_path),
                )
            )
            if existing_folder is None:
                existing_folder = FolderEntity(
                    device_id=device.id,
                    canonical_path=str(folder_path),
                    folder_name=folder_path.name or folder_path.anchor,
                    parent_path=str(folder_path.parent) if folder_path != sandbox_service.root else None,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    exists_now=True,
                    metadata_json={"scanned_via": "scan_folder"},
                )
                session.add(existing_folder)
            else:
                existing_folder.folder_name = folder_path.name or folder_path.anchor
                existing_folder.parent_path = (
                    str(folder_path.parent) if folder_path != sandbox_service.root else None
                )
                existing_folder.last_seen_at = seen_at
                existing_folder.exists_now = True
                existing_folder.metadata_json = {"scanned_via": "scan_folder"}

            folder_entities.append(existing_folder)

        file_entities: list[FileEntity] = []
        for file_path in file_paths:
            metadata = sandbox_service.metadata_for_path(file_path)
            existing_file = await session.scalar(
                select(FileEntity).where(
                    FileEntity.device_id == device.id,
                    FileEntity.canonical_path == str(file_path),
                )
            )
            if existing_file is None:
                existing_file = FileEntity(
                    device_id=device.id,
                    canonical_path=str(file_path),
                    filename=file_path.name,
                    extension=metadata.extension,
                    mime_type=metadata.mime_type,
                    size_bytes=metadata.size_bytes,
                    content_hash=None,
                    modified_at=metadata.modified_at,
                    created_at_fs=metadata.created_at_fs,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    exists_now=True,
                    metadata_json={"scanned_via": "scan_folder"},
                )
                session.add(existing_file)
            else:
                existing_file.filename = file_path.name
                existing_file.extension = metadata.extension
                existing_file.mime_type = metadata.mime_type
                existing_file.size_bytes = metadata.size_bytes
                existing_file.modified_at = metadata.modified_at
                existing_file.created_at_fs = metadata.created_at_fs
                existing_file.last_seen_at = seen_at
                existing_file.exists_now = True
                existing_file.metadata_json = {"scanned_via": "scan_folder"}

            file_entities.append(existing_file)

        await session.flush()
        await session.commit()

        return {
            "files": [_file_payload(file_entity) for file_entity in file_entities],
            "folders": [_folder_payload(folder) for folder in folder_entities],
            "summary": f"Scanned {len(file_entities)} files across {len(folder_entities)} folders.",
        }
