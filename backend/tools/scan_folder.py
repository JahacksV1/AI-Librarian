from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from db.connection import db_manager
from db.models import Device, FileEntity, FolderEntity, Session
from safety.sandbox import sandbox_service

# ---------------------------------------------------------------------------
# File intelligence helpers
# ---------------------------------------------------------------------------

# Keyword patterns for category guessing — checked against lowercase filename
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("invoice",       ["invoice", "bill", "billing", "receipt", "payment", "statement"]),
    ("contract",      ["contract", "agreement", "nda", "sow", "terms", "engagement"]),
    ("draft",         ["draft", "wip", "temp", "tmp"]),
    ("report",        ["report", "summary", "analysis", "review", "audit"]),
    ("letter",        ["letter", "ltr", "correspondence", "memo"]),
    ("spreadsheet",   ["budget", "forecast", "expense", "tracker", "sheet"]),
    ("photo",         ["img", "photo", "pic", "scan", "screenshot"]),
    ("presentation",  ["presentation", "deck", "slides", "pitch"]),
    ("archive",       ["archive", "backup", "zip", "compressed"]),
    ("config",        ["config", "settings", "env", "setup", ".ini", ".cfg", ".toml", ".yaml", ".yml"]),
    ("log",           ["log", "logs", ".log"]),
    ("notes",         ["notes", "note", "todo", "ideas", "scratch"]),
]

# Extensions that are safe to attempt a text preview on
_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".md", ".markdown", ".csv", ".log", ".rst",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".js", ".ts", ".html", ".css", ".xml",
    ".sh", ".bat", ".ps1",
})

_PREVIEW_MAX_BYTES = 512   # read limit to avoid large files
_PREVIEW_CHARS = 200       # characters to include in output


def _guess_category(filename: str, extension: str) -> str:
    needle = filename.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in needle:
                return category

    ext_map = {
        ".pdf": "document",
        ".doc": "document", ".docx": "document",
        ".xls": "spreadsheet", ".xlsx": "spreadsheet",
        ".ppt": "presentation", ".pptx": "presentation",
        ".jpg": "photo", ".jpeg": "photo", ".png": "photo",
        ".gif": "photo", ".webp": "photo", ".heic": "photo",
        ".mp4": "video", ".mov": "video", ".avi": "video",
        ".mp3": "audio", ".wav": "audio", ".m4a": "audio",
        ".zip": "archive", ".tar": "archive", ".gz": "archive", ".7z": "archive",
    }
    if extension in ext_map:
        return ext_map[extension]

    return "unknown"


def _read_content_preview(file_path: Path, extension: str) -> str | None:
    if extension not in _TEXT_EXTENSIONS:
        return None
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read(_PREVIEW_MAX_BYTES)
        preview = raw[:_PREVIEW_CHARS].strip()
        # Collapse whitespace runs to keep token count low
        preview = " ".join(preview.split())
        return preview if preview else None
    except OSError:
        return None


def _to_iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _folder_payload(folder: FolderEntity) -> dict:
    return {
        "id": str(folder.id),
        "canonical_path": folder.canonical_path,
        "folder_name": folder.folder_name,
        "parent_path": folder.parent_path,
    }


def _file_payload(file_entity: FileEntity, file_path: Path) -> dict:
    extension = file_entity.extension or ""
    return {
        "id": str(file_entity.id),
        "canonical_path": file_entity.canonical_path,
        "filename": file_entity.filename,
        "extension": extension,
        "size_bytes": file_entity.size_bytes,
        "modified_at": _to_iso(file_entity.modified_at),
        "guessed_category": _guess_category(file_entity.filename, extension),
        "content_preview": _read_content_preview(file_path, extension),
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

        file_entities_with_paths: list[tuple[FileEntity, Path]] = []
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

            file_entities_with_paths.append((existing_file, file_path))

        await session.flush()
        await session.commit()

        # Build folder summaries: per-folder category breakdown
        folder_canonical_paths = {str(fp) for fp in folder_paths}
        folder_file_counts: dict[str, int] = {p: 0 for p in folder_canonical_paths}
        folder_categories: dict[str, list[str]] = {p: [] for p in folder_canonical_paths}
        for file_entity, file_path in file_entities_with_paths:
            parent = str(file_path.parent)
            if parent in folder_file_counts:
                folder_file_counts[parent] += 1
                cat = _guess_category(file_entity.filename, file_entity.extension or "")
                if cat not in folder_categories[parent]:
                    folder_categories[parent].append(cat)

        folder_payloads = []
        for folder in folder_entities:
            payload = _folder_payload(folder)
            payload["file_count"] = folder_file_counts.get(folder.canonical_path, 0)
            payload["categories_present"] = folder_categories.get(folder.canonical_path, [])
            folder_payloads.append(payload)

        return {
            "files": [_file_payload(fe, fp) for fe, fp in file_entities_with_paths],
            "folders": folder_payloads,
            "summary": f"Scanned {len(file_entities_with_paths)} files across {len(folder_entities)} folders.",
        }
