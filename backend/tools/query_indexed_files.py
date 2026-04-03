from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import asc, desc, func, select

from db.connection import db_manager
from db.models import FileEntity, FolderEntity, Session
from safety.sandbox import sandbox_service

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 25
_AGGREGATE_TOP_N = 25


def _to_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _escape_like_prefix(path_prefix: str) -> str:
    # PostgreSQL uses "\" as LIKE escape, so Windows-style paths need escaping.
    escaped = path_prefix.replace("\\", "\\\\")
    return f"{escaped}%"


def _normalize_extension(extension: str | None) -> str | None:
    if extension is None:
        return None
    normalized = extension.strip().lower()
    if normalized.startswith("."):
        normalized = normalized[1:]
    return normalized or None


def _normalize_entity_type(entity_type: str) -> str:
    normalized = (entity_type or "file").strip().lower()
    return "folder" if normalized == "folder" else "file"


def _normalize_category(category: str | None) -> str | None:
    if category is None:
        return None
    normalized = category.strip().lower()
    return normalized or None


def _clamp_limit(limit: int | None) -> int:
    if limit is None:
        return _DEFAULT_LIMIT
    return max(1, min(int(limit), _MAX_LIMIT))


async def query_indexed_files(
    session_id: str = "",
    path_prefix: str | None = None,
    entity_type: str = "file",
    extension: str | None = None,
    category: str | None = None,
    min_size_bytes: int | None = None,
    max_size_bytes: int | None = None,
    exists_now: bool | None = True,
    sort_by: str = "name",
    sort_order: str = "asc",
    limit: int = _DEFAULT_LIMIT,
    include_counts: bool = False,
) -> dict[str, Any]:
    session_uuid = uuid.UUID(session_id)
    result_limit = _clamp_limit(limit)
    normalized_entity = _normalize_entity_type(entity_type)
    normalized_ext = _normalize_extension(extension)
    normalized_category = _normalize_category(category)
    normalized_sort_order = (sort_order or "asc").strip().lower()

    async with db_manager.session() as session:
        session_row = await session.get(Session, session_uuid)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")
        if session_row.device_id is None:
            raise ValueError("Session has no device_id; query_indexed_files requires a device-bound session.")

        if normalized_entity == "folder":
            filters = [FolderEntity.device_id == session_row.device_id]

            if path_prefix:
                safe_prefix = str(sandbox_service.resolve_path(path_prefix))
                filters.append(FolderEntity.canonical_path.like(_escape_like_prefix(safe_prefix)))

            if exists_now is not None:
                filters.append(FolderEntity.exists_now.is_(exists_now))

            sort_map = {
                "name": FolderEntity.folder_name,
                "path": FolderEntity.canonical_path,
            }
            sort_column = sort_map.get((sort_by or "name").strip().lower(), FolderEntity.folder_name)
            sort_clause = desc(sort_column) if normalized_sort_order == "desc" else asc(sort_column)

            total_matching = int(
                await session.scalar(select(func.count(FolderEntity.id)).where(*filters)) or 0
            )
            rows = list(
                await session.scalars(
                    select(FolderEntity)
                    .where(*filters)
                    .order_by(sort_clause, FolderEntity.id.asc())
                    .limit(result_limit)
                )
            )

            payload: dict[str, Any] = {
                "entity_type": "folder",
                "total_matching": total_matching,
                "returned": len(rows),
                "results": [
                    {
                        "id": str(row.id),
                        "canonical_path": row.canonical_path,
                        "folder_name": row.folder_name,
                        "parent_path": row.parent_path,
                        "exists_now": row.exists_now,
                    }
                    for row in rows
                ],
            }

            if include_counts:
                by_parent_rows = await session.execute(
                    select(FolderEntity.parent_path, func.count(FolderEntity.id))
                    .where(*filters)
                    .group_by(FolderEntity.parent_path)
                    .order_by(func.count(FolderEntity.id).desc())
                    .limit(_AGGREGATE_TOP_N)
                )
                payload["counts"] = {
                    "total_folders": total_matching,
                    "by_parent_path": {
                        (parent_path if parent_path else "<root>"): int(count)
                        for parent_path, count in by_parent_rows.all()
                    },
                }

            return payload

        # File query path
        filters = [FileEntity.device_id == session_row.device_id]

        if path_prefix:
            safe_prefix = str(sandbox_service.resolve_path(path_prefix))
            filters.append(FileEntity.canonical_path.like(_escape_like_prefix(safe_prefix)))

        if normalized_ext is not None:
            filters.append(func.lower(FileEntity.extension) == normalized_ext)

        if normalized_category is not None:
            filters.append(func.lower(FileEntity.guessed_category) == normalized_category)

        if min_size_bytes is not None:
            filters.append(FileEntity.size_bytes >= min_size_bytes)
        if max_size_bytes is not None:
            filters.append(FileEntity.size_bytes <= max_size_bytes)

        if exists_now is not None:
            filters.append(FileEntity.exists_now.is_(exists_now))

        sort_map = {
            "name": FileEntity.filename,
            "size": FileEntity.size_bytes,
            "modified_at": FileEntity.modified_at,
            "extension": FileEntity.extension,
            "path": FileEntity.canonical_path,
        }
        sort_column = sort_map.get((sort_by or "name").strip().lower(), FileEntity.filename)
        sort_clause = desc(sort_column) if normalized_sort_order == "desc" else asc(sort_column)

        total_matching = int(await session.scalar(select(func.count(FileEntity.id)).where(*filters)) or 0)
        rows = list(
            await session.scalars(
                select(FileEntity)
                .where(*filters)
                .order_by(sort_clause, FileEntity.id.asc())
                .limit(result_limit)
            )
        )

        payload = {
            "entity_type": "file",
            "total_matching": total_matching,
            "returned": len(rows),
            "results": [
                {
                    "id": str(row.id),
                    "canonical_path": row.canonical_path,
                    "filename": row.filename,
                    "extension": row.extension,
                    "size_bytes": row.size_bytes,
                    "guessed_category": row.guessed_category,
                    "modified_at": _to_iso(row.modified_at),
                    "exists_now": row.exists_now,
                }
                for row in rows
            ],
        }

        if include_counts:
            total_size_bytes = int(
                await session.scalar(
                    select(func.coalesce(func.sum(FileEntity.size_bytes), 0)).where(*filters)
                ) or 0
            )

            category_rows = await session.execute(
                select(FileEntity.guessed_category, func.count(FileEntity.id))
                .where(*filters)
                .group_by(FileEntity.guessed_category)
                .order_by(func.count(FileEntity.id).desc())
                .limit(_AGGREGATE_TOP_N)
            )
            extension_rows = await session.execute(
                select(FileEntity.extension, func.count(FileEntity.id))
                .where(*filters)
                .group_by(FileEntity.extension)
                .order_by(func.count(FileEntity.id).desc())
                .limit(_AGGREGATE_TOP_N)
            )

            payload["counts"] = {
                "total_files": total_matching,
                "total_size_bytes": total_size_bytes,
                "by_category": {
                    (category_name if category_name else "unknown"): int(count)
                    for category_name, count in category_rows.all()
                },
                "by_extension": {
                    (f".{ext}" if ext else "<none>"): int(count)
                    for ext, count in extension_rows.all()
                },
            }

        return payload
