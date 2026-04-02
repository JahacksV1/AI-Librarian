from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import mimetypes

from config import settings


class SandboxPathError(ValueError):
    """Raised when a path escapes the configured sandbox root."""


@dataclass(frozen=True)
class PathMetadata:
    canonical_path: str
    filename: str
    extension: str | None
    mime_type: str | None
    size_bytes: int | None
    modified_at: datetime | None
    created_at_fs: datetime | None
    exists: bool
    is_dir: bool


class SandboxService:
    """Centralizes all sandbox path validation and filesystem helpers."""

    def __init__(self, sandbox_root: str) -> None:
        self.root = Path(sandbox_root).resolve()

    def resolve_path(self, raw_path: str) -> Path:
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            raise SandboxPathError("Path must be absolute.")

        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise SandboxPathError("Path must stay within SANDBOX_ROOT.") from exc

        return resolved

    def resolve_directory(self, raw_path: str) -> Path:
        directory = self.resolve_path(raw_path)
        if not directory.exists():
            raise FileNotFoundError(f"Directory does not exist: {directory}")
        if not directory.is_dir():
            raise NotADirectoryError(f"Path is not a directory: {directory}")
        return directory

    def resolve_file(self, raw_path: str) -> Path:
        file_path = self.resolve_path(raw_path)
        if not file_path.exists():
            raise FileNotFoundError(f"File does not exist: {file_path}")
        if not file_path.is_file():
            raise IsADirectoryError(f"Path is not a file: {file_path}")
        return file_path

    def ensure_parent_exists(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def create_folder(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

    def move_path(self, source: Path, destination: Path) -> None:
        self.ensure_parent_exists(destination)
        source.rename(destination)

    def archive_destination(self, source: Path) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        relative_parent = source.parent.relative_to(self.root)
        archive_root = self.root / ".aijah_archive" / relative_parent
        archived_name = f"{source.stem}_{timestamp}{source.suffix}"
        return archive_root / archived_name

    def scan_paths(self, directory: Path, recursive: bool) -> tuple[list[Path], list[Path]]:
        if recursive:
            entries = [path for path in directory.rglob("*")]
        else:
            entries = [path for path in directory.iterdir()]

        files = [path for path in entries if path.is_file()]
        folders = [path for path in entries if path.is_dir()]

        # Include the scanned directory itself as a known folder entity.
        return files, [directory, *folders]

    def metadata_for_path(self, path: Path) -> PathMetadata:
        exists = path.exists()
        if not exists:
            return PathMetadata(
                canonical_path=str(path),
                filename=path.name,
                extension=path.suffix.lstrip(".") or None,
                mime_type=None,
                size_bytes=None,
                modified_at=None,
                created_at_fs=None,
                exists=False,
                is_dir=False,
            )

        stat = path.stat()
        mime_type, _ = mimetypes.guess_type(str(path))
        extension = None if path.is_dir() else (path.suffix.lstrip(".") or None)

        return PathMetadata(
            canonical_path=str(path),
            filename=path.name,
            extension=extension,
            mime_type=mime_type,
            size_bytes=None if path.is_dir() else stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            created_at_fs=datetime.fromtimestamp(stat.st_ctime, tz=timezone.utc),
            exists=True,
            is_dir=path.is_dir(),
        )


def walk_filesystem(
    directory: Path,
    recursive: bool,
    max_files: int,
) -> tuple[list[Path], list[Path], bool]:
    """Blocking filesystem walk suitable for use with asyncio.to_thread.

    Returns (files, folders, truncated).  Stops collecting files once
    max_files is reached and sets truncated=True so callers can inform
    the user that the result is partial.  Uses os.scandir for efficient
    batched syscalls and handles permission errors gracefully.
    """
    files: list[Path] = []
    folders: list[Path] = [directory]
    truncated = False

    if recursive:
        stack: list[Path] = [directory]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                p = Path(entry.path)
                                folders.append(p)
                                stack.append(p)
                            elif entry.is_file(follow_symlinks=False):
                                if len(files) >= max_files:
                                    truncated = True
                                    return files, folders, truncated
                                files.append(Path(entry.path))
                        except (PermissionError, OSError):
                            continue
            except (PermissionError, OSError):
                continue
    else:
        try:
            with os.scandir(directory) as it:
                for entry in it:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            folders.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            if len(files) >= max_files:
                                truncated = True
                                break
                            files.append(Path(entry.path))
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass

    return files, folders, truncated


sandbox_service = SandboxService(settings.sandbox_root)
