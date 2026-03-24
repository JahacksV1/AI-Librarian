from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from db.connection import db_manager
from db.enums import ScanDepth, ScanStatus
from db.models import Device, FileEntity, FolderEntity, Scan, Session
from safety.sandbox import sandbox_service

# ---------------------------------------------------------------------------
# File intelligence helpers
# ---------------------------------------------------------------------------

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

_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    ".txt", ".md", ".markdown", ".csv", ".log", ".rst",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".py", ".js", ".ts", ".html", ".css", ".xml",
    ".sh", ".bat", ".ps1",
})

_PREVIEW_MAX_BYTES = 512
_PREVIEW_CHARS = 200


def _guess_category(filename: str, extension: str) -> str:
    needle = filename.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in needle:
                return category

    ext_map = {
        ".pdf": "document", ".doc": "document", ".docx": "document",
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


def _file_payload(file_entity: FileEntity) -> dict:
    return {
        "id": str(file_entity.id),
        "canonical_path": file_entity.canonical_path,
        "filename": file_entity.filename,
        "extension": file_entity.extension or "",
        "size_bytes": file_entity.size_bytes,
        "modified_at": _to_iso(file_entity.modified_at),
        "guessed_category": file_entity.guessed_category,
        "content_preview": file_entity.content_preview,
    }


def _count_immediate_children(folder_path: Path) -> int:
    """Count direct children of a folder without recursing — fast for ROOT scan."""
    try:
        return sum(1 for _ in folder_path.iterdir())
    except (PermissionError, OSError):
        return 0


# ---------------------------------------------------------------------------
# Three scan depth modes
#
# ROOT    — immediate children only. Returns folder tree at one level.
#           No content reading. Fast — used for orientation and discovery.
#           "What is at the top of this path?"
#
# DEEP    — full recursive walk, metadata only (name, size, date, category
#           guessed from filename). No content reading. The full inventory.
#           "Give me everything that exists here, structured."
#
# CONTENT — full recursive walk + text previews for supported file types.
#           Slower. Used when the model needs to understand what's inside files.
#           Always targeted to a specific path, not the whole filesystem.
# ---------------------------------------------------------------------------


async def scan_folder(
    path: str,
    recursive: bool = True,
    session_id: str = "",
    scan_depth: str = "DEEP",
) -> dict:
    session_uuid = uuid.UUID(session_id)
    directory = sandbox_service.resolve_directory(path)
    seen_at = datetime.now(timezone.utc)
    scan_root = str(directory)

    try:
        depth = ScanDepth(scan_depth.upper())
    except ValueError:
        depth = ScanDepth.DEEP

    # ROOT always walks only the immediate level regardless of the recursive flag.
    use_recursive = False if depth == ScanDepth.ROOT else recursive

    file_paths, folder_paths = sandbox_service.scan_paths(directory, recursive=use_recursive)

    async with db_manager.session() as db:
        session_row = await db.get(Session, session_uuid)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")
        if session_row.device_id is None:
            raise ValueError("Session has no device_id; scan_folder requires a device-bound session.")

        device = await db.get(Device, session_row.device_id)
        if device is None:
            raise ValueError("Session device_id is set, but device row does not exist.")

        scan_record = Scan(
            session_id=session_uuid,
            device_id=device.id,
            root_path=scan_root,
            scan_depth=depth,
            recursive=use_recursive,
            status=ScanStatus.RUNNING,
            started_at=seen_at,
        )
        db.add(scan_record)
        await db.flush()
        scan_id = scan_record.id

        try:
            seen_folder_paths: set[str] = set()
            seen_file_paths: set[str] = set()
            new_file_count = 0
            category_counter: Counter[str] = Counter()

            # --- Upsert folders ---
            folder_entities: list[FolderEntity] = []
            for folder_path in folder_paths:
                canonical = str(folder_path)
                seen_folder_paths.add(canonical)

                existing = await db.scalar(
                    select(FolderEntity).where(
                        FolderEntity.device_id == device.id,
                        FolderEntity.canonical_path == canonical,
                    )
                )
                if existing is None:
                    existing = FolderEntity(
                        device_id=device.id,
                        canonical_path=canonical,
                        folder_name=folder_path.name or folder_path.anchor,
                        parent_path=str(folder_path.parent) if folder_path != sandbox_service.root else None,
                        first_seen_at=seen_at,
                        last_seen_at=seen_at,
                        exists_now=True,
                        metadata_json={"scanned_via": "scan_folder", "scan_depth": depth.value},
                    )
                    db.add(existing)
                else:
                    existing.folder_name = folder_path.name or folder_path.anchor
                    existing.parent_path = (
                        str(folder_path.parent) if folder_path != sandbox_service.root else None
                    )
                    existing.last_seen_at = seen_at
                    existing.exists_now = True
                    existing.metadata_json = {"scanned_via": "scan_folder", "scan_depth": depth.value}

                folder_entities.append(existing)

            # --- Upsert files ---
            # DEEP: metadata only, no content reading
            # CONTENT: metadata + content preview
            # ROOT: files at the immediate level only (already limited by use_recursive=False)
            read_content = (depth == ScanDepth.CONTENT)

            file_entities: list[FileEntity] = []
            for file_path in file_paths:
                canonical = str(file_path)
                seen_file_paths.add(canonical)
                metadata = sandbox_service.metadata_for_path(file_path)
                extension = metadata.extension or ""
                category = _guess_category(file_path.name, extension)
                preview = _read_content_preview(file_path, extension) if read_content else None
                category_counter[category] += 1

                existing = await db.scalar(
                    select(FileEntity).where(
                        FileEntity.device_id == device.id,
                        FileEntity.canonical_path == canonical,
                    )
                )
                is_new = existing is None
                if is_new:
                    new_file_count += 1
                    existing = FileEntity(
                        device_id=device.id,
                        canonical_path=canonical,
                        filename=file_path.name,
                        extension=extension,
                        mime_type=metadata.mime_type,
                        size_bytes=metadata.size_bytes,
                        content_hash=None,
                        modified_at=metadata.modified_at,
                        created_at_fs=metadata.created_at_fs,
                        first_seen_at=seen_at,
                        last_seen_at=seen_at,
                        exists_now=True,
                        metadata_json={"scanned_via": "scan_folder", "scan_depth": depth.value},
                        guessed_category=category,
                        content_preview=preview,
                        last_scan_id=scan_id,
                    )
                    db.add(existing)
                else:
                    existing.filename = file_path.name
                    existing.extension = extension
                    existing.mime_type = metadata.mime_type
                    existing.size_bytes = metadata.size_bytes
                    existing.modified_at = metadata.modified_at
                    existing.created_at_fs = metadata.created_at_fs
                    existing.last_seen_at = seen_at
                    existing.exists_now = True
                    existing.metadata_json = {"scanned_via": "scan_folder", "scan_depth": depth.value}
                    existing.guessed_category = category
                    # Only overwrite content_preview if we're doing a CONTENT scan.
                    # DEEP scan does not clear an existing preview set by a past CONTENT scan.
                    if read_content:
                        existing.content_preview = preview
                    existing.last_scan_id = scan_id

                file_entities.append(existing)

            await db.flush()

            # --- Change detection: mark missing files/folders ---
            prefix_filter = f"{scan_root}%" if not scan_root.endswith("/") else f"{scan_root}%"

            # Change detection only makes sense for DEEP/CONTENT where we see everything.
            # ROOT scan covers only one level so we cannot infer deletions below that level.
            deleted_file_count = 0
            if depth != ScanDepth.ROOT:
                previously_known_files = list(
                    await db.scalars(
                        select(FileEntity).where(
                            FileEntity.device_id == device.id,
                            FileEntity.canonical_path.like(prefix_filter),
                            FileEntity.exists_now.is_(True),
                        )
                    )
                )
                for fe in previously_known_files:
                    if fe.canonical_path not in seen_file_paths:
                        fe.exists_now = False
                        deleted_file_count += 1

                previously_known_folders = list(
                    await db.scalars(
                        select(FolderEntity).where(
                            FolderEntity.device_id == device.id,
                            FolderEntity.canonical_path.like(prefix_filter),
                            FolderEntity.exists_now.is_(True),
                        )
                    )
                )
                for fo in previously_known_folders:
                    if fo.canonical_path not in seen_folder_paths:
                        fo.exists_now = False

            # --- Build folder summaries (for ROOT: immediate child counts; for DEEP/CONTENT: file counts) ---
            if depth == ScanDepth.ROOT:
                # For ROOT, count each subfolder's immediate children — fast one-level look.
                folder_child_counts: dict[str, int] = {}
                for fe in folder_entities:
                    fp = Path(fe.canonical_path)
                    if fp != directory:
                        folder_child_counts[fe.canonical_path] = _count_immediate_children(fp)
            else:
                folder_child_counts = {}

            # Finalize scan record
            scan_record.file_count = len(file_entities)
            scan_record.folder_count = len(folder_entities)
            scan_record.new_files = new_file_count
            scan_record.deleted_files = deleted_file_count
            scan_record.modified_files = 0
            scan_record.status = ScanStatus.COMPLETED
            scan_record.completed_at = datetime.now(timezone.utc)

            if depth == ScanDepth.ROOT:
                subfolders_sorted = sorted(
                    [fe for fe in folder_entities if Path(fe.canonical_path) != directory],
                    key=lambda f: folder_child_counts.get(f.canonical_path, 0),
                    reverse=True,
                )
                scan_record.summary_json = {
                    "categories": dict(category_counter.most_common()),
                    "top_folders": [fe.canonical_path for fe in subfolders_sorted],
                    "folder_child_counts": folder_child_counts,
                }
            else:
                scan_record.summary_json = {
                    "categories": dict(category_counter.most_common()),
                    "top_folders": [
                        fe.canonical_path for fe in sorted(
                            folder_entities,
                            key=lambda f: sum(
                                1 for fi in file_entities
                                if str(Path(fi.canonical_path).parent) == f.canonical_path
                            ),
                            reverse=True,
                        )[:5]
                    ],
                }

            await db.commit()

        except Exception:
            scan_record.status = ScanStatus.FAILED
            scan_record.completed_at = datetime.now(timezone.utc)
            await db.commit()
            raise

        # --- Build return payload ---
        if depth == ScanDepth.ROOT:
            # Return folder summaries with child counts — the discovery view.
            subfolder_payloads = []
            for folder in folder_entities:
                if Path(folder.canonical_path) == directory:
                    continue
                payload = _folder_payload(folder)
                payload["child_count"] = folder_child_counts.get(folder.canonical_path, 0)
                subfolder_payloads.append(payload)
            subfolder_payloads.sort(key=lambda f: f["child_count"], reverse=True)

            return {
                "scan_id": str(scan_id),
                "scan_depth": depth.value,
                "files": [_file_payload(fe) for fe in file_entities],
                "folders": subfolder_payloads,
                "summary": (
                    f"Root scan of {scan_root}: found {len(subfolder_payloads)} subfolders"
                    + (f" and {len(file_entities)} files at this level." if file_entities else ".")
                ),
                "changes": {
                    "new_files": new_file_count,
                    "deleted_files": 0,
                },
                "categories": dict(category_counter.most_common()),
            }

        # DEEP / CONTENT — full folder + file list with per-folder counts
        folder_file_counts: dict[str, int] = {fe.canonical_path: 0 for fe in folder_entities}
        folder_categories: dict[str, list[str]] = {fe.canonical_path: [] for fe in folder_entities}
        for file_entity in file_entities:
            parent = str(Path(file_entity.canonical_path).parent)
            if parent in folder_file_counts:
                folder_file_counts[parent] += 1
                cat = file_entity.guessed_category or "unknown"
                if cat not in folder_categories[parent]:
                    folder_categories[parent].append(cat)

        folder_payloads = []
        for folder in folder_entities:
            payload = _folder_payload(folder)
            payload["file_count"] = folder_file_counts.get(folder.canonical_path, 0)
            payload["categories_present"] = folder_categories.get(folder.canonical_path, [])
            folder_payloads.append(payload)

        return {
            "scan_id": str(scan_id),
            "scan_depth": depth.value,
            "files": [_file_payload(fe) for fe in file_entities],
            "folders": folder_payloads,
            "summary": f"Scanned {len(file_entities)} files across {len(folder_entities)} folders.",
            "changes": {
                "new_files": new_file_count,
                "deleted_files": deleted_file_count,
            },
            "categories": dict(category_counter.most_common()),
        }
