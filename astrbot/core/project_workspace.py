"""Secure, server-derived workspaces for ChatUI projects."""

from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import unquote

from astrbot.core.utils.astrbot_path import get_astrbot_workspaces_path

WORKSPACE_ENTRY_LIMIT = 1000
WORKSPACE_PREVIEW_MAX_BYTES = 512 * 1024


class ProjectWorkspaceError(ValueError):
    """Raised when a project workspace path is invalid or inaccessible."""


class ProjectWorkspaceResolver:
    """Resolve project paths without accepting client-controlled roots."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.base_root = Path(root or get_astrbot_workspaces_path()).resolve(
            strict=False
        )

    @staticmethod
    def _creator_segment(creator: str) -> str:
        segment = re.sub(r"[^A-Za-z0-9._-]+", "_", str(creator).strip())
        return segment or "unknown"

    @staticmethod
    def _project_segment(project_id: str) -> str:
        try:
            return str(uuid.UUID(str(project_id)))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ProjectWorkspaceError("Invalid project identifier") from exc

    def root_for(self, creator: str, project_id: str) -> Path:
        """Return the derived root ``workspaces/projects/<creator>/<uuid>``."""
        root = (
            self.base_root
            / "projects"
            / self._creator_segment(creator)
            / self._project_segment(project_id)
        ).resolve(strict=False)
        if not root.is_relative_to(self.base_root):
            raise ProjectWorkspaceError("Invalid project workspace root")
        return root

    @staticmethod
    def _parts(relative_path: str, *, allow_empty: bool) -> tuple[str, ...]:
        raw = str(relative_path or "")
        if not allow_empty and not raw.strip():
            raise ProjectWorkspaceError("Workspace path is required")
        decoded = raw
        for _ in range(3):
            next_value = unquote(decoded)
            if next_value == decoded:
                break
            decoded = next_value
        normalized = decoded.replace("\\", "/")
        if "\x00" in normalized or normalized.startswith("/"):
            raise ProjectWorkspaceError("Invalid workspace path")
        parts = tuple(part for part in normalized.split("/") if part not in {"", "."})
        if any(part in {"..", "~"} or "/" in part or "\\" in part for part in parts):
            raise ProjectWorkspaceError("Invalid workspace path")
        if any(part.startswith("/") or Path(part).is_absolute() for part in parts):
            raise ProjectWorkspaceError("Invalid workspace path")
        return parts

    def _walk(self, root: Path, parts: tuple[str, ...]) -> Path:
        current = root
        for part in parts:
            try:
                candidate = next(
                    entry for entry in current.iterdir() if entry.name == part
                )
            except (FileNotFoundError, StopIteration, OSError) as exc:
                raise ProjectWorkspaceError("Workspace path not found") from exc
            try:
                info = candidate.lstat()
            except OSError as exc:
                raise ProjectWorkspaceError("Workspace path cannot be read") from exc
            if os.path.islink(candidate) or not candidate.is_relative_to(root):
                raise ProjectWorkspaceError("Workspace path escapes project directory")
            if info.st_nlink > 1 and candidate.is_file():
                raise ProjectWorkspaceError("Hard-linked workspace files are denied")
            current = candidate
        return current

    def resolve_directory(
        self, creator: str, project_id: str, relative_path: str = ""
    ) -> tuple[Path, Path]:
        root = self.root_for(creator, project_id)
        target = (
            self._walk(root, self._parts(relative_path, allow_empty=True))
            if root.exists()
            else root
        )
        if not target.exists() or not target.is_dir():
            raise ProjectWorkspaceError("Workspace directory not found")
        return root, target

    def resolve_file(
        self, creator: str, project_id: str, relative_path: str
    ) -> tuple[Path, Path]:
        root = self.root_for(creator, project_id)
        target = self._walk(root, self._parts(relative_path, allow_empty=False))
        if not target.is_file():
            raise ProjectWorkspaceError("Workspace file not found")
        return root, target

    def iter_entries(self, directory: Path) -> Iterator[Path]:
        try:
            entries = sorted(
                directory.iterdir(),
                key=lambda entry: (not entry.is_dir(), entry.name.casefold()),
            )
        except OSError as exc:
            raise ProjectWorkspaceError("Workspace directory cannot be read") from exc
        if len(entries) > WORKSPACE_ENTRY_LIMIT:
            raise ProjectWorkspaceError("Workspace directory contains too many entries")
        return iter(entries)

    @staticmethod
    def open_for_read(path: Path):
        """Open a validated file without following a final symlink."""
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            return os.fdopen(os.open(path, flags), "rb")
        except OSError as exc:
            raise ProjectWorkspaceError("Workspace file cannot be opened") from exc
