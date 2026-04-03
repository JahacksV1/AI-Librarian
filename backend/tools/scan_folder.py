from __future__ import annotations

import asyncio
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from db.connection import db_manager
from db.enums import ScanDepth, ScanStatus
from db.models import Device, FileEntity, FolderEntity, Scan, Session
from safety.sandbox import sandbox_service, walk_filesystem
from services.scan_intelligence import (
    build_file_payload,
    build_folder_payload,
    guess_category,
    read_content_preview,
)

# ---------------------------------------------------------------------------
# Limits — prevent hanging on large directories
# ---------------------------------------------------------------------------

MAX_FILES_ROOT = 5_000       # ROOT scan: immediate level only, generous limit
MAX_FILES_DEEP = 3_000       # DEEP: metadata walk — cap at 3k files
MAX_FILES_CONTENT = 500      # CONTENT: reads file text — much smaller cap

# Model-facing payload caps — how many items the scan tool returns to the model.
# The full indexed data remains queryable via query_indexed_files at any time.
_FILE_SAMPLE_LIMIT = 20      # max file entries returned in any scan payload
_FOLDER_SAMPLE_LIMIT = 50    # max folder entries returned in any scan payload

# ---------------------------------------------------------------------------
# Main tool
# ---------------------------------------------------------------------------


def _count_immediate_children(folder_path: Path) -> int:
    """Count direct children of a folder without recursing — fast for ROOT scan."""
    try:
        return sum(1 for _ in folder_path.iterdir())
    except (PermissionError, OSError):
        return 0


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

    # Choose file limit based on depth.
    max_files = {
        ScanDepth.ROOT: MAX_FILES_ROOT,
        ScanDepth.DEEP: MAX_FILES_DEEP,
        ScanDepth.CONTENT: MAX_FILES_CONTENT,
    }[depth]

    # Run the blocking filesystem walk in a thread pool so we never freeze the
    # async event loop.  This is the fix for the "gets stuck" hang on large dirs.
    file_paths, folder_paths, truncated = await asyncio.to_thread(
        walk_filesystem,
        directory,
        use_recursive,
        max_files,
    )

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
            # ── Bulk-fetch all known entities for this device under this path ──
            # Two queries total instead of one per file/folder (N+1 fix).
            #
            # PostgreSQL treats '\' as the LIKE escape character, so Windows
            # backslash path separators must be doubled before appending '%'.
            # e.g. 'C:\Users\jaham' → 'C:\\Users\\jaham%'
            # Without this, LIKE 'C:\Users\jaham%' is interpreted as
            # 'C:Usersjaham%' (backslashes consumed as escape chars), which
            # matches nothing and causes UniqueViolationError on re-insert.
            escaped_root = scan_root.replace("\\", "\\\\")
            prefix = f"{escaped_root}%"

            existing_folders_map: dict[str, FolderEntity] = {
                fe.canonical_path: fe
                for fe in await db.scalars(
                    select(FolderEntity).where(
                        FolderEntity.device_id == device.id,
                        FolderEntity.canonical_path.like(prefix),
                    )
                )
            }
            existing_files_map: dict[str, FileEntity] = {
                fe.canonical_path: fe
                for fe in await db.scalars(
                    select(FileEntity).where(
                        FileEntity.device_id == device.id,
                        FileEntity.canonical_path.like(prefix),
                    )
                )
            }

            seen_folder_paths: set[str] = set()
            seen_file_paths: set[str] = set()
            new_file_count = 0
            category_counter: Counter[str] = Counter()

            # ── Upsert folders ────────────────────────────────────────────────
            folder_entities: list[FolderEntity] = []
            for folder_path in folder_paths:
                canonical = str(folder_path)
                seen_folder_paths.add(canonical)

                existing = existing_folders_map.get(canonical)
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
                    existing_folders_map[canonical] = existing
                else:
                    existing.folder_name = folder_path.name or folder_path.anchor
                    existing.parent_path = (
                        str(folder_path.parent) if folder_path != sandbox_service.root else None
                    )
                    existing.last_seen_at = seen_at
                    existing.exists_now = True
                    existing.metadata_json = {"scanned_via": "scan_folder", "scan_depth": depth.value}

                folder_entities.append(existing)

            # ── Upsert files ──────────────────────────────────────────────────
            read_content = (depth == ScanDepth.CONTENT)

            file_entities: list[FileEntity] = []
            for file_path in file_paths:
                canonical = str(file_path)
                seen_file_paths.add(canonical)
                metadata = sandbox_service.metadata_for_path(file_path)
                extension = metadata.extension or ""
                category = guess_category(file_path.name, extension)
                preview = read_content_preview(file_path, extension) if read_content else None
                category_counter[category] += 1

                existing = existing_files_map.get(canonical)
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
                    existing_files_map[canonical] = existing
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
                    if read_content:
                        existing.content_preview = preview
                    existing.last_scan_id = scan_id

                file_entities.append(existing)

            await db.flush()

            # ── Change detection ──────────────────────────────────────────────
            deleted_file_count = 0
            if depth != ScanDepth.ROOT and not truncated:
                # Only mark deletions if we actually walked the full subtree.
                for fe in existing_files_map.values():
                    if fe.canonical_path not in seen_file_paths and fe.exists_now:
                        fe.exists_now = False
                        deleted_file_count += 1
                for fo in existing_folders_map.values():
                    if fo.canonical_path not in seen_folder_paths and fo.exists_now:
                        fo.exists_now = False

            # ── Folder child counts (ROOT) / file counts (DEEP/CONTENT) ──────
            if depth == ScanDepth.ROOT:
                folder_child_counts: dict[str, int] = {}
                for fe in folder_entities:
                    fp = Path(fe.canonical_path)
                    if fp != directory:
                        folder_child_counts[fe.canonical_path] = _count_immediate_children(fp)
            else:
                folder_child_counts = {}

            # ── Finalize scan record ──────────────────────────────────────────
            scan_record.file_count = len(file_entities)
            scan_record.folder_count = len(folder_entities)
            scan_record.new_files = new_file_count
            scan_record.deleted_files = deleted_file_count
            scan_record.modified_files = 0
            scan_record.status = ScanStatus.COMPLETED
            scan_record.completed_at = datetime.now(timezone.utc)

            truncation_note = (
                f" (scan stopped at {max_files} files — use a more targeted path to see more)"
                if truncated else ""
            )

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
                    "truncated": truncated,
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

        # ── Build return payload ──────────────────────────────────────────────
        if depth == ScanDepth.ROOT:
            subfolder_payloads = []
            for folder in folder_entities:
                if Path(folder.canonical_path) == directory:
                    continue
                payload = build_folder_payload(
                    folder,
                    child_count=folder_child_counts.get(folder.canonical_path, 0),
                )
                subfolder_payloads.append(payload)
            subfolder_payloads.sort(key=lambda f: f["child_count"], reverse=True)

            # Cap file list — full data is in file_entities / query_indexed_files
            file_sample = [build_file_payload(fe) for fe in file_entities[:_FILE_SAMPLE_LIMIT]]
            file_sample_note = (
                f" (showing {_FILE_SAMPLE_LIMIT} of {len(file_entities)} — use query_indexed_files for more)"
                if len(file_entities) > _FILE_SAMPLE_LIMIT else ""
            )

            # Cap folder list — full data is in folder_entities / query_indexed_files
            folders_truncated = len(subfolder_payloads) > _FOLDER_SAMPLE_LIMIT
            folder_sample = subfolder_payloads[:_FOLDER_SAMPLE_LIMIT]
            folder_sample_note = (
                f" (showing {_FOLDER_SAMPLE_LIMIT} of {len(subfolder_payloads)} — use query_indexed_files for more)"
                if folders_truncated else ""
            )

            return {
                "scan_id": str(scan_id),
                "scan_depth": depth.value,
                "file_count": len(file_entities),
                "folder_count": len(subfolder_payloads),
                "file_sample": file_sample,
                "folders": folder_sample,
                "summary": (
                    f"Root scan of {scan_root}: found {len(subfolder_payloads)} subfolders"
                    + (f" and {len(file_entities)} files at this level." if file_entities else ".")
                    + truncation_note
                    + file_sample_note
                    + folder_sample_note
                ),
                "changes": {"new_files": new_file_count, "deleted_files": 0},
                "categories": dict(category_counter.most_common()),
            }

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
            folder_payloads.append(build_folder_payload(
                folder,
                file_count=folder_file_counts.get(folder.canonical_path, 0),
                categories_present=folder_categories.get(folder.canonical_path, []),
            ))

        # Sort folders by file count descending — most active folders first.
        folder_payloads.sort(key=lambda f: f["file_count"], reverse=True)

        # DEEP / CONTENT scans can return thousands of files. Sending the raw
        # file list to the model inflates the context to 200k+ tokens, hitting
        # API limits and degrading quality. Instead we return only:
        #   - folder-level summaries (capped, already computed above)
        #   - a small representative sample of files (up to _FILE_SAMPLE_LIMIT)
        #   - aggregate stats and categories
        # The full detail is stored in file_entities / folder_entities in the DB
        # and can be retrieved via query_indexed_files when the model needs specifics.
        file_sample = [build_file_payload(fe) for fe in file_entities[:_FILE_SAMPLE_LIMIT]]
        file_sample_note = (
            f" (showing {_FILE_SAMPLE_LIMIT} of {len(file_entities)} — use query_indexed_files for more)"
            if len(file_entities) > _FILE_SAMPLE_LIMIT else ""
        )

        # Cap folder list too — large directory trees can produce hundreds of folder payloads.
        folders_truncated = len(folder_payloads) > _FOLDER_SAMPLE_LIMIT
        folder_sample = folder_payloads[:_FOLDER_SAMPLE_LIMIT]
        folder_sample_note = (
            f" (showing {_FOLDER_SAMPLE_LIMIT} of {len(folder_payloads)} folders — use query_indexed_files for more)"
            if folders_truncated else ""
        )

        return {
            "scan_id": str(scan_id),
            "scan_depth": depth.value,
            "file_count": len(file_entities),
            "folder_count": len(folder_payloads),
            "file_sample": file_sample,
            "folders": folder_sample,
            "summary": (
                f"Scanned {len(file_entities)} files across {len(folder_payloads)} folders."
                + truncation_note
                + file_sample_note
                + folder_sample_note
            ),
            "changes": {"new_files": new_file_count, "deleted_files": deleted_file_count},
            "categories": dict(category_counter.most_common()),
        }
