"""Safe management of files below the active AstrBot ``data`` directory."""

from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
import re
import stat as stat_module
import tempfile
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.datastructures import UploadFile

from astrbot.core.utils.astrbot_path import get_astrbot_data_path

DATA_TEXT_MAX_BYTES = 1024 * 1024
DATA_UPLOAD_MAX_BYTES = 32 * 1024 * 1024
DATA_UPLOAD_REQUEST_MAX_BYTES = 64 * 1024 * 1024
DATA_TREE_MAX_ENTRIES = 200
DATA_SEARCH_MAX_RESULTS = 100
DATA_SEARCH_INODE_BUDGET = 5000
DATA_SEARCH_TIMEOUT_SECONDS = 3.0
_TEMP_PREFIX = ".astrbot-data-tmp-"
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WINDOWS_RESERVED = re.compile(
    r"^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?$", re.IGNORECASE
)
_TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".mjs",
    ".cjs",
    ".md",
    ".markdown",
    ".py",
    ".sh",
    ".bash",
    ".sql",
    ".scss",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
    ".ps1",
}
_LANGUAGES = {
    ".css": "css",
    ".html": "html",
    ".ini": "ini",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".py": "python",
    ".sh": "shell",
    ".bash": "shell",
    ".sql": "sql",
    ".scss": "css",
    ".toml": "ini",
    ".ts": "typescript",
    ".txt": "plaintext",
    ".xml": "xml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".ps1": "powershell",
}
_SPECIAL_LANGUAGES = {"dockerfile": "dockerfile", "makefile": "plaintext"}
_DATABASE_NAMES = {"data.db", "data_v4.db"}
_DATABASE_SUFFIXES = (
    ".db",
    ".db-wal",
    ".db-shm",
    ".sqlite",
    ".sqlite3",
    ".sqlite-wal",
    ".sqlite-shm",
)
_SENSITIVE_ROOT_FILES = {
    "cmd_config.json",
    "mcp_server.json",
    "shared_preferences.json",
    "mcp_auth.json",
    ".installation_id",
}
_SENSITIVE_DIRS = {"config", "backups", "webchat"}
_TEMPORARY_DIRS = {"temp", "attachments", "logs"}
_HARD_READONLY_DIRS = {"dist", "site-packages"}


def _decode_utf8(data: bytes) -> str | None:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


class DataFileServiceError(Exception):
    """A safe, user-facing data-file operation failure."""

    def __init__(self, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class DataFileOpen:
    fd: int
    entry: dict[str, Any]
    content_type: str


class DataFileService:
    """Perform all filesystem operations relative to the runtime data root."""

    def __init__(
        self,
        *,
        data_root: str | Path | None = None,
        demo_mode: bool = False,
        managed_config_saver: Callable[[str, dict[str, Any]], Awaitable[None]]
        | None = None,
    ):
        raw_root = (
            Path(data_root) if data_root is not None else Path(get_astrbot_data_path())
        )
        try:
            self.root = raw_root.resolve(strict=True)
        except OSError as exc:
            raise DataFileServiceError(
                "Data directory is unavailable", status_code=503
            ) from exc
        if not self.root.is_dir():
            raise DataFileServiceError("Data directory is unavailable", status_code=503)
        self.demo_mode = demo_mode
        self._managed_config_saver = managed_config_saver

    @staticmethod
    def normalize_relative_path(value: str | None, *, allow_empty: bool = True) -> str:
        raw = "" if value is None else str(value)
        raw = raw.replace("\\", "/")
        if not raw:
            if allow_empty:
                return ""
            raise DataFileServiceError("Path is required")
        if raw.startswith("/") or re.match(r"^[A-Za-z]:", raw):
            raise DataFileServiceError("Invalid data path")
        if _CONTROL_CHARS.search(raw):
            raise DataFileServiceError("Invalid data path")
        parts = raw.split("/")
        if any(not part or part in {".", ".."} for part in parts):
            raise DataFileServiceError("Invalid data path")
        if any(
            _WINDOWS_RESERVED.fullmatch(part) or part.rstrip(" .") != part
            for part in parts
        ):
            raise DataFileServiceError("Invalid data path")
        return "/".join(parts)

    def _resolve(
        self, relative_path: str | None, *, allow_empty: bool = True
    ) -> tuple[Path, str]:
        normalized = self.normalize_relative_path(
            relative_path, allow_empty=allow_empty
        )
        candidate = (
            self.root if not normalized else self.root.joinpath(*normalized.split("/"))
        )
        try:
            resolved = candidate.resolve(strict=False)
        except OSError as exc:
            raise DataFileServiceError("Invalid data path") from exc
        final_symlink = bool(normalized) and candidate.is_symlink()
        if not resolved.is_relative_to(self.root) and not final_symlink:
            raise DataFileServiceError("Invalid data path")
        # A symlink is metadata-only.  Do not traverse a symlink component.
        current = self.root
        parts = normalized.split("/") if normalized else []
        for index, part in enumerate(parts):
            current /= part
            try:
                is_link = current.is_symlink()
            except OSError as exc:
                raise DataFileServiceError(
                    "Data path is unavailable", status_code=404
                ) from exc
            if is_link and index < len(parts) - 1:
                raise DataFileServiceError(
                    "Symlink traversal is not allowed", status_code=403
                )
        return candidate, normalized

    def _lstat(self, path: Path) -> os.stat_result:
        try:
            return path.lstat()
        except FileNotFoundError as exc:
            raise DataFileServiceError("Entry not found", status_code=404) from exc
        except OSError as exc:
            raise DataFileServiceError("Entry is unavailable", status_code=404) from exc

    def _iterdir_safe(self, path: Path) -> list[Path]:
        """List one directory without following a swapped directory symlink."""
        before = self._lstat(path)
        if not stat_module.S_ISDIR(before.st_mode):
            raise DataFileServiceError("Directory not found", status_code=400)
        directory_fd: int | None = None
        try:
            if hasattr(os, "O_NOFOLLOW"):
                flags = os.O_RDONLY | os.O_NOFOLLOW
                if hasattr(os, "O_DIRECTORY"):
                    flags |= os.O_DIRECTORY
                directory_fd = os.open(path, flags)
                opened = os.fstat(directory_fd)
                if opened.st_ino != before.st_ino or opened.st_dev != before.st_dev:
                    raise DataFileServiceError(
                        "Directory changed while reading", status_code=409
                    )
                names = os.listdir(directory_fd)
            else:
                names = [child.name for child in path.iterdir()]
            after = self._lstat(path)
            if after.st_ino != before.st_ino or after.st_dev != before.st_dev:
                raise DataFileServiceError(
                    "Directory changed while reading", status_code=409
                )
            return [path / name for name in names]
        except DataFileServiceError:
            raise
        except OSError as exc:
            raise DataFileServiceError(
                "Directory is unavailable", status_code=404
            ) from exc
        finally:
            if directory_fd is not None:
                os.close(directory_fd)

    @staticmethod
    def _etag_from_bytes(data: bytes) -> str:
        return "sha256:" + hashlib.sha256(data).hexdigest()

    def _etag(self, path: Path, info: os.stat_result) -> str:
        if not stat_module.S_ISREG(info.st_mode):
            return f"stat:{info.st_mtime_ns}:{info.st_size}"
        try:
            with self._safe_open(path, os.O_RDONLY) as handle:
                digest = hashlib.sha256()
                while chunk := os.read(handle.fileno(), 1024 * 1024):
                    digest.update(chunk)
                return "sha256:" + digest.hexdigest()
        except OSError as exc:
            raise DataFileServiceError("Entry is unavailable", status_code=404) from exc

    @staticmethod
    def _safe_open(path: Path, flags: int, mode: int = 0o600):
        if not hasattr(os, "O_NOFOLLOW") and path.is_symlink():
            raise OSError("symlink open refused")
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags, mode)
        return os.fdopen(fd, "r+b" if flags & os.O_RDWR else "rb", closefd=True)

    def _category(
        self, relative_path: str, info: os.stat_result
    ) -> tuple[str, bool, bool]:
        parts = relative_path.split("/") if relative_path else []
        lower_parts = [part.casefold() for part in parts]
        name = lower_parts[-1] if lower_parts else ""
        if stat_module.S_ISLNK(info.st_mode):
            return "system", True, True
        if any(part in _HARD_READONLY_DIRS for part in lower_parts):
            return "system", True, True
        if lower_parts and lower_parts[0] == "plugins":
            return "system", True, False
        if name in _DATABASE_NAMES or name.endswith(_DATABASE_SUFFIXES):
            return "database", True, False
        if lower_parts and lower_parts[0] in _SENSITIVE_DIRS:
            return "system", True, False
        if name in _SENSITIVE_ROOT_FILES or (
            lower_parts and lower_parts[0] in _SENSITIVE_DIRS
        ):
            return "system", True, False
        if lower_parts and lower_parts[0] in _TEMPORARY_DIRS:
            return "temporary", True, False
        if (
            lower_parts
            and lower_parts[0] == "knowledge_base"
            and (
                name.endswith((".faiss", ".index", *_DATABASE_SUFFIXES))
                or "index" in name
            )
        ):
            return "database", True, True
        if stat_module.S_ISDIR(info.st_mode):
            return (
                "system" if name in _HARD_READONLY_DIRS else "text",
                False,
                name in _HARD_READONLY_DIRS,
            )
        return (
            "text"
            if Path(name).suffix.casefold() in _TEXT_SUFFIXES
            or name in _SPECIAL_LANGUAGES
            else "binary",
            False,
            False,
        )

    def path_is_protected(self, relative_path: str) -> bool:
        """Classify a not-yet-existing path without touching the filesystem."""
        normalized = self.normalize_relative_path(relative_path, allow_empty=False)
        parts = [part.casefold() for part in normalized.split("/")]
        name = parts[-1]
        return bool(
            any(part in (_HARD_READONLY_DIRS | {"plugins"}) for part in parts)
            or (parts and parts[0] in _SENSITIVE_DIRS)
            or name in _SENSITIVE_ROOT_FILES
            or name in _DATABASE_NAMES
            or name.endswith(_DATABASE_SUFFIXES)
            or (
                parts
                and parts[0] == "knowledge_base"
                and (name.endswith((".faiss", ".index")) or "index" in name)
            )
        )

    def path_is_hard_restricted(self, relative_path: str) -> bool:
        normalized = self.normalize_relative_path(relative_path, allow_empty=False)
        parts = [part.casefold() for part in normalized.split("/")]
        name = parts[-1]
        return bool(
            any(part in _HARD_READONLY_DIRS for part in parts)
            or name in _DATABASE_NAMES
            or name.endswith(_DATABASE_SUFFIXES)
            or (
                parts
                and parts[0] == "knowledge_base"
                and (name.endswith((".faiss", ".index")) or "index" in name)
            )
        )

    def path_is_sensitive(self, relative_path: str) -> bool:
        normalized = self.normalize_relative_path(relative_path, allow_empty=False)
        parts = [part.casefold() for part in normalized.split("/")]
        name = parts[-1]
        return bool(
            parts
            and (
                parts[0] in _SENSITIVE_DIRS
                or normalized.casefold() in _SENSITIVE_ROOT_FILES
                or parts[0] in _TEMPORARY_DIRS
                or name in _DATABASE_NAMES
                or name.endswith(_DATABASE_SUFFIXES)
                or (
                    parts[0] == "knowledge_base"
                    and (name.endswith((".faiss", ".index")) or "index" in name)
                )
            )
        )

    def is_managed_config_path(self, relative_path: str) -> bool:
        normalized = self.normalize_relative_path(relative_path, allow_empty=False)
        parts = normalized.split("/")
        return normalized.casefold() in {"cmd_config.json", "mcp_server.json"} or (
            len(parts) == 2
            and parts[0].casefold() == "config"
            and parts[1].casefold().endswith(".json")
        )

    def _language(self, name: str, category: str) -> str | None:
        if category not in {"text", "system"}:
            return None
        lowered = name.casefold()
        if lowered in _SPECIAL_LANGUAGES:
            return _SPECIAL_LANGUAGES[lowered]
        return _LANGUAGES.get(Path(name).suffix.casefold(), "plaintext")

    def _is_binary_content(self, path: Path, info: os.stat_result) -> bool:
        if not stat_module.S_ISREG(info.st_mode) or info.st_size == 0:
            return False
        try:
            with self._safe_open(path, os.O_RDONLY) as handle:
                sample = handle.read(min(info.st_size, 8192))
            return b"\x00" in sample or bool(_decode_utf8(sample) is None)
        except OSError:
            return True

    def _entry(
        self,
        path: Path,
        relative_path: str,
        *,
        can_read: bool,
        can_write: bool,
        can_manage: bool,
        is_root: bool,
        include_content_etag: bool = True,
    ) -> dict[str, Any]:
        info = self._lstat(path)
        is_dir = stat_module.S_ISDIR(info.st_mode)
        is_link = stat_module.S_ISLNK(info.st_mode)
        if is_link:
            entry_type = "symlink"
        elif is_dir:
            entry_type = "directory"
        elif stat_module.S_ISREG(info.st_mode):
            entry_type = "file"
        else:
            entry_type = "other"
        category, protected, hard_readonly = self._category(relative_path, info)
        if category == "text" and self._is_binary_content(path, info):
            category = "binary"
        sensitive = protected and (
            category in {"database", "temporary"}
            or (
                (relative_path.split("/", 1)[0] if relative_path else "")
                in _SENSITIVE_DIRS
            )
            or (relative_path.casefold() in _SENSITIVE_ROOT_FILES)
        )
        managed_config = stat_module.S_ISREG(
            info.st_mode
        ) and self.is_managed_config_path(relative_path)
        readable = can_read and (not sensitive or is_root)
        writable = (
            not self.demo_mode
            and can_write
            and not hard_readonly
            and not is_link
            and (is_dir or entry_type == "file")
            and (
                not protected
                or can_manage
                or (sensitive and is_root and managed_config)
            )
            and (not sensitive or is_root)
            and category not in {"database", "temporary"}
        )
        deletable = (
            not self.demo_mode
            and can_write
            and not hard_readonly
            and not is_link
            and (not protected or can_manage)
            and category not in {"database", "temporary"}
        )
        return {
            "name": path.name or "data",
            "path": relative_path,
            "type": entry_type,
            "size": 0 if is_dir else int(info.st_size),
            "modified_at": datetime.fromtimestamp(info.st_mtime, UTC).isoformat(),
            "category": category,
            "language": self._language(path.name, category),
            "readable": readable,
            "writable": writable,
            "deletable": deletable,
            "downloadable": readable and entry_type == "file",
            "protected": protected,
            "etag": (
                self._etag(path, info)
                if readable
                and entry_type == "file"
                and include_content_etag
                and info.st_size <= DATA_TEXT_MAX_BYTES
                else (
                    f"stat:{info.st_mtime_ns}:{info.st_size}"
                    if readable and entry_type == "file"
                    else None
                )
            ),
            "mime_type": mimetypes.guess_type(path.name)[0]
            or "application/octet-stream",
        }

    def metadata(self, relative_path: str | None, **rights: bool) -> dict[str, Any]:
        path, normalized = self._resolve(relative_path)
        return self._entry(path, normalized, **self._rights(rights))

    @staticmethod
    def _rights(rights: dict[str, bool]) -> dict[str, bool]:
        return {
            "can_read": bool(rights.get("can_read", True)),
            "can_write": bool(rights.get("can_write", False)),
            "can_manage": bool(rights.get("can_manage", False)),
            "is_root": bool(rights.get("is_root", False)),
        }

    def tree(self, relative_path: str | None, **rights: bool) -> dict[str, Any]:
        path, normalized = self._resolve(relative_path)
        info = self._lstat(path)
        if not stat_module.S_ISDIR(info.st_mode):
            raise DataFileServiceError("Directory not found", status_code=400)
        entries: list[dict[str, Any]] = []
        children = sorted(
            self._iterdir_safe(path),
            key=lambda item: (not item.is_dir(), item.name.casefold(), item.name),
        )
        for child in children[:DATA_TREE_MAX_ENTRIES]:
            if child.name.startswith(_TEMP_PREFIX):
                continue
            child_rel = f"{normalized}/{child.name}" if normalized else child.name
            try:
                entries.append(
                    self._entry(
                        child,
                        child_rel,
                        include_content_etag=False,
                        **self._rights(rights),
                    )
                )
            except DataFileServiceError:
                continue
        return {
            "path": normalized,
            "entries": entries,
            "truncated": len(children) > DATA_TREE_MAX_ENTRIES,
        }

    def read_text(
        self, relative_path: str | None, *, is_root: bool, **rights: bool
    ) -> dict[str, Any]:
        path, normalized = self._resolve(relative_path, allow_empty=False)
        info = self._lstat(path)
        normalized_rights = self._rights(rights)
        normalized_rights["is_root"] = is_root
        entry = self._entry(path, normalized, **normalized_rights)
        if not entry["readable"]:
            raise DataFileServiceError("File read is not permitted", status_code=403)
        if entry["type"] != "file" or entry["category"] in {
            "binary",
            "database",
            "temporary",
        }:
            raise DataFileServiceError("File is not a text file", status_code=415)
        if info.st_size > DATA_TEXT_MAX_BYTES:
            raise DataFileServiceError("File is too large to edit", status_code=413)
        try:
            with self._safe_open(path, os.O_RDONLY) as handle:
                data = handle.read(DATA_TEXT_MAX_BYTES + 1)
                opened = os.fstat(handle.fileno())
            if opened.st_ino != info.st_ino or opened.st_dev != info.st_dev:
                raise DataFileServiceError(
                    "File changed while reading", status_code=409
                )
            if len(data) > DATA_TEXT_MAX_BYTES:
                raise DataFileServiceError("File is too large to edit", status_code=413)
            content = data.decode("utf-8")
            if "\x00" in content:
                raise UnicodeDecodeError("utf-8", data, 0, 1, "binary content")
        except UnicodeDecodeError as exc:
            raise DataFileServiceError(
                "File is binary or not valid UTF-8", status_code=415
            ) from exc
        return {
            "path": normalized,
            "content": content,
            "size": len(data),
            "encoding": "utf-8",
            "language": entry["language"],
            "etag": self._etag_from_bytes(data),
            "writable": entry["writable"],
            "protected": entry["protected"],
            "runtime_reload": "not_guaranteed",
        }

    def _check_write(
        self,
        path: Path,
        relative_path: str,
        *,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> dict[str, Any]:
        entry = self._entry(
            path,
            relative_path,
            can_read=True,
            can_write=can_write,
            can_manage=can_manage,
            is_root=is_root,
        )
        if not entry["writable"]:
            raise DataFileServiceError("File write is not permitted", status_code=403)
        return entry

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            directory_fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError:
            pass

    def _atomic_write(self, path: Path, data: bytes) -> None:
        parent = path.parent
        parent.mkdir(parents=False, exist_ok=True)
        temp_path: Path | None = None
        try:
            fd, name = tempfile.mkstemp(prefix=_TEMP_PREFIX, dir=parent)
            temp_path = Path(name)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            temp_path = None
            self._fsync_directory(parent)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass

    def write_text(
        self,
        relative_path: str,
        content: str,
        *,
        expected_etag: str | None,
        can_read: bool = True,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> dict[str, Any]:
        if self.demo_mode:
            raise DataFileServiceError("Demo mode is read-only", status_code=403)
        if not isinstance(content, str):
            raise DataFileServiceError("Text content is required")
        data = content.encode("utf-8")
        if len(data) > DATA_TEXT_MAX_BYTES:
            raise DataFileServiceError("File is too large to edit", status_code=413)
        path, normalized = self._resolve(relative_path, allow_empty=False)
        if self.path_is_hard_restricted(normalized):
            raise DataFileServiceError(
                "This path is permanently read-only", status_code=403
            )
        if self.is_managed_config_path(normalized):
            raise DataFileServiceError(
                "This managed file must be saved through its configuration service",
                status_code=403,
            )
        info = self._lstat(path)
        entry = self._check_write(
            path,
            normalized,
            is_root=is_root,
            can_write=can_write,
            can_manage=can_manage,
        )
        if entry["type"] != "file":
            raise DataFileServiceError(
                "Only regular files can be edited", status_code=400
            )
        if expected_etag is None:
            raise DataFileServiceError("An expected ETag is required", status_code=428)
        current = self._etag(path, info)
        if expected_etag is not None and expected_etag != current:
            raise DataFileServiceError(
                "File changed since it was loaded", status_code=409
            )
        self._atomic_write(path, data)
        new_info = self._lstat(path)
        return {
            "path": normalized,
            "etag": self._etag(path, new_info),
            "size": len(data),
            "writable": entry["writable"],
            "runtime_reload": "not_guaranteed",
        }

    async def write_managed_text(
        self,
        relative_path: str,
        content: str,
        *,
        expected_etag: str | None,
        can_read: bool = True,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> dict[str, Any]:
        """Commit core configuration through its validator and reload path."""
        normalized = self.normalize_relative_path(relative_path, allow_empty=False)
        if (
            not self.is_managed_config_path(normalized)
            or self._managed_config_saver is None
        ):
            raise DataFileServiceError(
                "This managed file must be edited through its configuration service",
                status_code=403,
            )
        path, _ = self._resolve(normalized, allow_empty=False)
        info = self._lstat(path)
        self._check_write(
            path,
            normalized,
            is_root=is_root,
            can_write=can_write,
            can_manage=can_manage,
        )
        if stat_module.S_ISDIR(info.st_mode):
            raise DataFileServiceError(
                "Only regular files can be edited", status_code=400
            )
        if expected_etag is None:
            raise DataFileServiceError("An expected ETag is required", status_code=428)
        current = self._etag(path, info)
        if expected_etag is not None and expected_etag != current:
            raise DataFileServiceError(
                "File changed since it was loaded", status_code=409
            )
        if len(content.encode("utf-8")) > DATA_TEXT_MAX_BYTES:
            raise DataFileServiceError("File is too large to edit", status_code=413)
        try:
            # AstrBot's managed JSON files may use UTF-8 with a BOM, matching
            # ``AstrBotConfig``'s utf-8-sig loader. Keep that encoding valid
            # when an editor round-trips the original text.
            parsed = json.loads(content.removeprefix("\ufeff"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise DataFileServiceError(
                "Configuration JSON is invalid", status_code=422
            ) from exc
        if not isinstance(parsed, dict):
            raise DataFileServiceError(
                "Configuration must be a JSON object", status_code=422
            )
        try:
            await self._managed_config_saver(normalized, parsed)
        except DataFileServiceError:
            raise
        except Exception as exc:
            raise DataFileServiceError(
                "Configuration was not saved", status_code=422
            ) from exc
        new_info = self._lstat(path)
        return {
            "path": normalized,
            "etag": self._etag(path, new_info),
            "size": new_info.st_size,
            "writable": True,
            "runtime_reload": "reloaded",
        }

    def create(
        self,
        relative_path: str,
        entry_type: str,
        *,
        content: str = "",
        can_read: bool = True,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> dict[str, Any]:
        if self.demo_mode:
            raise DataFileServiceError("Demo mode is read-only", status_code=403)
        path, normalized = self._resolve(relative_path, allow_empty=False)
        if self.path_is_hard_restricted(normalized):
            raise DataFileServiceError(
                "This path is permanently read-only", status_code=403
            )
        if self.is_managed_config_path(normalized):
            raise DataFileServiceError(
                "This managed file must be changed through its configuration service",
                status_code=403,
            )
        if path.exists() or path.is_symlink():
            raise DataFileServiceError("Entry already exists", status_code=409)
        parent = path.parent
        if not parent.is_dir():
            raise DataFileServiceError("Parent directory not found", status_code=404)
        parent_rel = normalized.rsplit("/", 1)[0] if "/" in normalized else ""
        self._check_write(
            parent,
            parent_rel,
            is_root=is_root,
            can_write=can_write,
            can_manage=can_manage,
        )
        if entry_type == "directory":
            path.mkdir()
        elif entry_type == "file":
            data = content.encode("utf-8")
            if len(data) > DATA_TEXT_MAX_BYTES:
                raise DataFileServiceError("File is too large to edit", status_code=413)
            self._atomic_write(path, data)
        else:
            raise DataFileServiceError("Invalid entry type")
        return self._entry(
            path,
            normalized,
            can_read=True,
            can_write=can_write,
            can_manage=can_manage,
            is_root=is_root,
        )

    def move(
        self,
        source_path: str,
        target_path: str,
        *,
        can_read: bool = True,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> dict[str, Any]:
        if self.demo_mode:
            raise DataFileServiceError("Demo mode is read-only", status_code=403)
        source, source_rel = self._resolve(source_path, allow_empty=False)
        target, target_rel = self._resolve(target_path, allow_empty=False)
        if self.is_managed_config_path(source_rel) or self.is_managed_config_path(
            target_rel
        ):
            raise DataFileServiceError(
                "This managed file must be changed through its configuration service",
                status_code=403,
            )
        if self.path_is_hard_restricted(target_rel):
            raise DataFileServiceError(
                "Move target is permanently read-only", status_code=403
            )
        source_info = self._lstat(source)
        if self.path_is_hard_restricted(source_rel):
            raise DataFileServiceError(
                "This path is permanently read-only", status_code=403
            )
        source_entry = self._entry(
            source,
            source_rel,
            can_read=True,
            can_write=can_write,
            can_manage=can_manage,
            is_root=is_root,
        )
        if not source_entry["deletable"]:
            raise DataFileServiceError("Move is not permitted", status_code=403)
        if target.exists() or target.is_symlink():
            raise DataFileServiceError("Target already exists", status_code=409)
        target_parent = target.parent
        target_parent_rel = target_rel.rsplit("/", 1)[0] if "/" in target_rel else ""
        self._check_write(
            target_parent,
            target_parent_rel,
            is_root=is_root,
            can_write=can_write,
            can_manage=can_manage,
        )
        # Reclassify the destination before changing anything (no permission washing).
        target_category, target_protected, target_hard = self._category(
            target_rel, source_info
        )
        if target_hard or (target_protected and not can_manage):
            raise DataFileServiceError("Move target is protected", status_code=403)
        try:
            source.rename(target)
        except OSError as exc:
            raise DataFileServiceError("Move failed", status_code=409) from exc
        return self._entry(
            target,
            target_rel,
            can_read=True,
            can_write=can_write,
            can_manage=can_manage,
            is_root=is_root,
        )

    def delete(
        self,
        relative_path: str,
        *,
        recursive: bool,
        can_read: bool = True,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> None:
        if self.demo_mode:
            raise DataFileServiceError("Demo mode is read-only", status_code=403)
        path, normalized = self._resolve(relative_path, allow_empty=False)
        if self.path_is_hard_restricted(normalized):
            raise DataFileServiceError(
                "This path is permanently read-only", status_code=403
            )
        if self.is_managed_config_path(normalized):
            raise DataFileServiceError(
                "This managed file must be changed through its configuration service",
                status_code=403,
            )
        info = self._lstat(path)
        entry = self._entry(
            path,
            normalized,
            can_read=True,
            can_write=can_write,
            can_manage=can_manage,
            is_root=is_root,
        )
        if not entry["deletable"]:
            raise DataFileServiceError("Delete is not permitted", status_code=403)
        if stat_module.S_ISDIR(info.st_mode):
            if recursive:
                self._validate_recursive_delete(
                    path,
                    normalized,
                    is_root=is_root,
                    can_write=can_write,
                    can_manage=can_manage,
                )
            if not recursive:
                try:
                    path.rmdir()
                except OSError as exc:
                    raise DataFileServiceError(
                        "Directory is not empty", status_code=409
                    ) from exc
            else:
                self._delete_tree(
                    path,
                    normalized,
                    is_root=is_root,
                    can_write=can_write,
                    can_manage=can_manage,
                )
        else:
            path.unlink()

    def _validate_recursive_delete(
        self,
        path: Path,
        relative_path: str,
        *,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> None:
        """Preflight every descendant before allowing recursive deletion."""
        for child in self._iterdir_safe(path):
            child_rel = f"{relative_path}/{child.name}"
            info = self._lstat(child)
            entry = self._entry(
                child,
                child_rel,
                can_read=True,
                can_write=can_write,
                can_manage=can_manage,
                is_root=is_root,
                include_content_etag=False,
            )
            if not entry["deletable"]:
                raise DataFileServiceError(
                    "Directory contains an entry that cannot be deleted",
                    status_code=403,
                )
            if stat_module.S_ISDIR(info.st_mode):
                self._validate_recursive_delete(
                    child,
                    child_rel,
                    is_root=is_root,
                    can_write=can_write,
                    can_manage=can_manage,
                )

    def _delete_tree(
        self,
        path: Path,
        relative_path: str,
        *,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> None:
        """Delete a preflighted tree while rechecking each entry at removal."""
        for child in self._iterdir_safe(path):
            child_rel = f"{relative_path}/{child.name}"
            info = self._lstat(child)
            entry = self._entry(
                child,
                child_rel,
                can_read=True,
                can_write=can_write,
                can_manage=can_manage,
                is_root=is_root,
                include_content_etag=False,
            )
            if not entry["deletable"]:
                raise DataFileServiceError(
                    "Directory contains an entry that cannot be deleted",
                    status_code=403,
                )
            if stat_module.S_ISDIR(info.st_mode):
                self._delete_tree(
                    child,
                    child_rel,
                    is_root=is_root,
                    can_write=can_write,
                    can_manage=can_manage,
                )
                try:
                    child.rmdir()
                except OSError as exc:
                    raise DataFileServiceError(
                        "Directory changed while deleting", status_code=409
                    ) from exc
            else:
                try:
                    child.unlink()
                except OSError as exc:
                    raise DataFileServiceError(
                        "Entry changed while deleting", status_code=409
                    ) from exc
        try:
            path.rmdir()
        except OSError as exc:
            raise DataFileServiceError(
                "Directory changed while deleting", status_code=409
            ) from exc

    async def upload(
        self,
        relative_path: str,
        upload: UploadFile,
        *,
        can_read: bool = True,
        is_root: bool,
        can_write: bool,
        can_manage: bool,
    ) -> dict[str, Any]:
        if self.demo_mode:
            raise DataFileServiceError("Demo mode is read-only", status_code=403)
        filename = str(getattr(upload, "filename", "") or "")
        if (
            not filename
            or "/" in filename
            or "\\" in filename
            or _CONTROL_CHARS.search(filename)
        ):
            raise DataFileServiceError("Invalid upload filename")
        path, normalized = self._resolve(relative_path, allow_empty=False)
        if self.path_is_hard_restricted(normalized):
            raise DataFileServiceError(
                "This path is permanently read-only", status_code=403
            )
        if self.is_managed_config_path(normalized):
            raise DataFileServiceError(
                "This managed file must be changed through its configuration service",
                status_code=403,
            )
        if path.exists() or path.is_symlink():
            raise DataFileServiceError("Entry already exists", status_code=409)
        parent = path.parent
        parent_rel = normalized.rsplit("/", 1)[0] if "/" in normalized else ""
        self._check_write(
            parent,
            parent_rel,
            is_root=is_root,
            can_write=can_write,
            can_manage=can_manage,
        )
        temp_path: Path | None = None
        total = 0
        try:
            fd, name = tempfile.mkstemp(prefix=_TEMP_PREFIX, dir=parent)
            temp_path = Path(name)
            with os.fdopen(fd, "wb") as output:
                await upload.seek(0)
                while chunk := await upload.read(1024 * 1024):
                    total += len(chunk)
                    if total > DATA_UPLOAD_MAX_BYTES:
                        raise DataFileServiceError(
                            "Uploaded file is too large", status_code=413
                        )
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temp_path, path)
            temp_path = None
            self._fsync_directory(parent)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except FileNotFoundError:
                    pass
        return self._entry(
            path,
            normalized,
            can_read=True,
            can_write=can_write,
            can_manage=can_manage,
            is_root=is_root,
        )

    def open_download(
        self, relative_path: str, *, is_root: bool, can_read: bool, can_manage: bool
    ) -> DataFileOpen:
        path, normalized = self._resolve(relative_path, allow_empty=False)
        info = self._lstat(path)
        entry = self._entry(
            path,
            normalized,
            can_read=can_read,
            can_write=False,
            can_manage=can_manage,
            is_root=is_root,
        )
        if not entry["downloadable"]:
            raise DataFileServiceError("Download is not permitted", status_code=403)
        if not stat_module.S_ISREG(info.st_mode):
            raise DataFileServiceError("File is unavailable", status_code=404)
        flags = os.O_RDONLY | (os.O_NOFOLLOW if hasattr(os, "O_NOFOLLOW") else 0)
        try:
            fd = os.open(path, flags)
            opened = os.fstat(fd)
            if opened.st_ino != info.st_ino or opened.st_dev != info.st_dev:
                os.close(fd)
                raise DataFileServiceError(
                    "File changed while opening", status_code=409
                )
        except DataFileServiceError:
            raise
        except OSError as exc:
            raise DataFileServiceError("File is unavailable", status_code=404) from exc
        return DataFileOpen(fd=fd, entry=entry, content_type=entry["mime_type"])

    async def search(
        self, query: str, relative_path: str | None, *, is_root: bool, can_read: bool
    ) -> dict[str, Any]:
        text = str(query or "").strip().casefold()
        if not text:
            raise DataFileServiceError("Search query is required")
        start, normalized = self._resolve(relative_path)
        start_info = self._lstat(start)
        if stat_module.S_ISLNK(start_info.st_mode):
            raise DataFileServiceError(
                "Symlink traversal is not allowed", status_code=403
            )
        if not stat_module.S_ISDIR(start_info.st_mode):
            raise DataFileServiceError("Directory not found", status_code=400)
        deadline = time.monotonic() + DATA_SEARCH_TIMEOUT_SECONDS

        def walk() -> dict[str, Any]:
            results: list[dict[str, Any]] = []
            visited = 0
            truncated = False
            stack = [start]
            while stack:
                if time.monotonic() >= deadline or visited >= DATA_SEARCH_INODE_BUDGET:
                    truncated = True
                    break
                current = stack.pop()
                try:
                    children = self._iterdir_safe(current)
                except DataFileServiceError:
                    continue
                for child in children:
                    visited += 1
                    if child.name.startswith(_TEMP_PREFIX):
                        continue
                    rel = child.relative_to(self.root).as_posix()
                    try:
                        if child.is_dir() and not child.is_symlink():
                            stack.append(child)
                        if (
                            text not in child.name.casefold()
                            and text not in rel.casefold()
                        ):
                            continue
                        entry = self._entry(
                            child,
                            rel,
                            can_read=can_read,
                            can_write=False,
                            can_manage=False,
                            is_root=is_root,
                        )
                        if entry["readable"]:
                            results.append(entry)
                            if len(results) >= DATA_SEARCH_MAX_RESULTS:
                                return {
                                    "path": normalized,
                                    "results": results,
                                    "truncated": True,
                                }
                    except DataFileServiceError:
                        continue
                    if (
                        time.monotonic() >= deadline
                        or visited >= DATA_SEARCH_INODE_BUDGET
                    ):
                        truncated = True
                        break
                if truncated:
                    break
            return {"path": normalized, "results": results, "truncated": truncated}

        return await asyncio.to_thread(walk)
