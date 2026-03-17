from __future__ import annotations

from sqlalchemy import select

from db.connection import db_manager
from db.models import FileEntity
from safety.sandbox import sandbox_service


def _to_iso(value) -> str | None:
    return value.isoformat() if value is not None else None


async def read_file_metadata(path: str) -> dict:
    file_path = sandbox_service.resolve_path(path)
    metadata = sandbox_service.metadata_for_path(file_path)

    async with db_manager.session() as session:
        file_entity = await session.scalar(
            select(FileEntity).where(FileEntity.canonical_path == str(file_path))
        )

        return {
            "id": str(file_entity.id) if file_entity is not None else None,
            "canonical_path": metadata.canonical_path,
            "filename": metadata.filename,
            "extension": metadata.extension,
            "size_bytes": metadata.size_bytes,
            "modified_at": _to_iso(metadata.modified_at),
            "exists": metadata.exists,
        }
