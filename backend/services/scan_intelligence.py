"""scan_intelligence.py — file and folder intelligence helpers for scan_folder.

Extracted from scan_folder.py so the indexing logic (DB writes) and the
model-facing intelligence logic (category guessing, preview extraction,
duplicate heuristics) live in separate, testable units.

scan_folder.py remains the authoritative MCP tool entry point.
These helpers are called by it and can be imported independently for testing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from db.models import FileEntity, FolderEntity

# ---------------------------------------------------------------------------
# Category guessing
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

_EXT_CATEGORY_MAP: dict[str, str] = {
    "pdf": "document", "doc": "document", "docx": "document",
    "xls": "spreadsheet", "xlsx": "spreadsheet",
    "ppt": "presentation", "pptx": "presentation",
    "jpg": "photo", "jpeg": "photo", "png": "photo",
    "gif": "photo", "webp": "photo", "heic": "photo",
    "mp4": "video", "mov": "video", "avi": "video",
    "mp3": "audio", "wav": "audio", "m4a": "audio",
    "zip": "archive", "tar": "archive", "gz": "archive", "7z": "archive",
}


def guess_category(filename: str, extension: str) -> str:
    """Infer a human-readable category from filename and extension."""
    needle = filename.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        for kw in keywords:
            if kw in needle:
                return category
    return _EXT_CATEGORY_MAP.get(extension, "unknown")


# ---------------------------------------------------------------------------
# Content preview extraction
# ---------------------------------------------------------------------------

_TEXT_EXTENSIONS: frozenset[str] = frozenset({
    "txt", "md", "markdown", "csv", "log", "rst",
    "json", "yaml", "yml", "toml", "ini", "cfg",
    "py", "js", "ts", "html", "css", "xml",
    "sh", "bat", "ps1",
})

_PREVIEW_MAX_BYTES = 512
_PREVIEW_CHARS = 200


def read_content_preview(file_path: Path, extension: str) -> str | None:
    """Return a short text preview for supported extensions, or None."""
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


# ---------------------------------------------------------------------------
# Duplicate candidate detection
# ---------------------------------------------------------------------------

def find_duplicate_candidates(
    file_entities: list[FileEntity],
) -> list[dict[str, Any]]:
    """Return groups of files that are likely duplicates based on name and size.

    This is a heuristic — it matches by (filename, size_bytes).  True content
    deduplication requires content_hash, which is not yet populated by scans.
    Results should always be presented to users as "potential duplicates".
    """
    from collections import defaultdict

    groups: dict[tuple[str, int | None], list[FileEntity]] = defaultdict(list)
    for fe in file_entities:
        if fe.exists_now:
            key = (fe.filename.lower(), fe.size_bytes)
            groups[key].append(fe)

    candidates = []
    for (name, size), members in groups.items():
        if len(members) > 1:
            candidates.append({
                "filename": name,
                "size_bytes": size,
                "count": len(members),
                "paths": [m.canonical_path for m in members],
                "detection": "name+size heuristic (not content-verified)",
            })

    # Sort by count descending so largest duplicate groups surface first
    candidates.sort(key=lambda c: c["count"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Summary payload builders
# ---------------------------------------------------------------------------

def build_folder_payload(
    folder: FolderEntity,
    child_count: int = 0,
    file_count: int = 0,
    categories_present: list[str] | None = None,
) -> dict[str, Any]:
    """Build a compact folder summary dict for model-facing payloads."""
    return {
        "id": str(folder.id),
        "canonical_path": folder.canonical_path,
        "folder_name": folder.folder_name,
        "parent_path": folder.parent_path,
        "child_count": child_count,
        "file_count": file_count,
        "categories_present": categories_present or [],
    }


def build_file_payload(file_entity: FileEntity) -> dict[str, Any]:
    """Build a compact file summary dict for model-facing payloads."""
    return {
        "id": str(file_entity.id),
        "canonical_path": file_entity.canonical_path,
        "filename": file_entity.filename,
        "extension": file_entity.extension or "",
        "size_bytes": file_entity.size_bytes,
        "modified_at": file_entity.modified_at.isoformat() if file_entity.modified_at else None,
        "guessed_category": file_entity.guessed_category,
        "content_preview": file_entity.content_preview,
    }
