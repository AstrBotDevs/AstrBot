"""
File edit history and rollback engine for AstrBot.

Provides transparent backup-before-edit and point-in-time rollback for
FileEditTool.  Each backup is stored as a timestamped ``.bak`` file under
``get_astrbot_temp_path()/file_edit/{path_hash}/``.

Storage layout::

    {temp_path}/file_edit/
        {sha256_16}/
            meta.json                  # original path + backup index
            YYYYMMDDTHHmmss_uuuuuu.bak # individual backup snapshots

Design decisions:
- Backups are always stored **locally** (even for sandbox-edited files)
  so that rollback survives sandbox restarts.
- ``WeakValueDictionary``-style cleanup is unnecessary here; instead we
  enforce a per-file cap (``max_backups``) with FIFO eviction.
- Thread-safety: all public methods are ``async``-safe because they only
  touch the filesystem (no shared mutable state beyond file I/O).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from astrbot.api import logger

# AstrBot CST timezone offset
_CST = timezone(timedelta(hours=8))

# Default limits
_DEFAULT_MAX_BACKUPS = 20  # per file
_DEFAULT_MAX_AGE_DAYS = 30  # for cleanup sweep


def _get_history_base_dir() -> Path:
    """Lazily import to avoid circular imports at module level."""
    from astrbot.core.utils.astrbot_path import get_astrbot_temp_path

    base = Path(get_astrbot_temp_path()) / "file_edit"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _path_hash(original_path: str) -> str:
    """Deterministic 16-char hex hash for a file path."""
    return hashlib.sha256(original_path.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Backup entry dataclass
# ---------------------------------------------------------------------------


@dataclass
class BackupEntry:
    """Metadata for a single backup snapshot."""

    id: str  # e.g. "20260604T221500_123456"
    timestamp: str  # ISO-8601 with timezone
    filename: str  # e.g. "20260604T221500_123456.bak"
    size: int  # bytes
    diff_preview: str = ""  # first N lines of unified diff (optional)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "filename": self.filename,
            "size": self.size,
            "diff_preview": self.diff_preview,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BackupEntry:
        return cls(
            id=data["id"],
            timestamp=data["timestamp"],
            filename=data["filename"],
            size=data.get("size", 0),
            diff_preview=data.get("diff_preview", ""),
        )


# ---------------------------------------------------------------------------
# File-level metadata
# ---------------------------------------------------------------------------


@dataclass
class FileHistory:
    """Metadata for all backups of a single file."""

    original_path: str
    runtime: str = "local"  # "local" or "sandbox"
    backups: list[BackupEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_path": self.original_path,
            "runtime": self.runtime,
            "backups": [b.to_dict() for b in self.backups],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FileHistory:
        return cls(
            original_path=data["original_path"],
            runtime=data.get("runtime", "local"),
            backups=[BackupEntry.from_dict(b) for b in data.get("backups", [])],
        )


# ---------------------------------------------------------------------------
# Core manager
# ---------------------------------------------------------------------------


class EditHistoryManager:
    """Manages file edit backups and rollback.

    All public methods are synchronous (filesystem I/O).  Callers that need
    async should wrap calls with ``asyncio.to_thread()``.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        if self._base_dir is None:
            self._base_dir = _get_history_base_dir()
        return self._base_dir

    # -- internal helpers ---------------------------------------------------

    def _file_dir(self, original_path: str) -> Path:
        """Get (and create) the backup directory for a specific file."""
        dir_path = self.base_dir / _path_hash(original_path)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def _load_history(self, original_path: str) -> FileHistory:
        """Load metadata from disk, or return a fresh empty history."""
        meta_path = self._file_dir(original_path) / "meta.json"
        if meta_path.exists():
            try:
                data = json.loads(meta_path.read_text("utf-8"))
                return FileHistory.from_dict(data)
            except (json.JSONDecodeError, KeyError) as exc:
                logger.warning(
                    f"Corrupted edit history meta for {original_path}, resetting: {exc}"
                )
        return FileHistory(original_path=original_path)

    def _save_history(self, history: FileHistory) -> None:
        """Persist metadata to disk (atomic-ish via write-then-rename)."""
        file_dir = self._file_dir(history.original_path)
        meta_path = file_dir / "meta.json"
        tmp_path = meta_path.with_suffix(".json.tmp")
        tmp_path.write_text(
            json.dumps(history.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp_path.replace(meta_path)

    # -- public API ---------------------------------------------------------

    def save_backup(
        self,
        original_path: str,
        content: bytes,
        *,
        runtime: str = "local",
        diff_preview: str = "",
        max_backups: int = _DEFAULT_MAX_BACKUPS,
    ) -> BackupEntry:
        """Save a pre-edit backup snapshot.

        Args:
            original_path: The resolved absolute path of the file being edited.
            content: The raw file bytes **before** the edit.
            runtime: ``"local"`` or ``"sandbox"`` — informational.
            diff_preview: Optional first few lines of the upcoming diff.
            max_backups: Maximum number of backups to retain per file.

        Returns:
            The newly created :class:`BackupEntry`.
        """
        now = datetime.now(_CST)
        backup_id = now.strftime("%Y%m%dT%H%M%S") + f"_{now.microsecond:06d}"
        filename = f"{backup_id}.bak"

        file_dir = self._file_dir(original_path)

        # Write backup content
        backup_path = file_dir / filename
        backup_path.write_bytes(content)

        # Update metadata
        history = self._load_history(original_path)
        history.runtime = runtime

        entry = BackupEntry(
            id=backup_id,
            timestamp=now.isoformat(),
            filename=filename,
            size=len(content),
            diff_preview=diff_preview[:500],  # cap preview size
        )
        history.backups.append(entry)

        # FIFO eviction of oldest backups
        evicted = 0
        while len(history.backups) > max_backups:
            oldest = history.backups.pop(0)
            old_file = file_dir / oldest.filename
            try:
                old_file.unlink(missing_ok=True)
            except OSError:
                pass
            evicted += 1

        self._save_history(history)

        if evicted:
            logger.debug(
                f"Edit history: evicted {evicted} old backup(s) for {original_path}"
            )

        return entry

    def list_backups(self, original_path: str) -> list[BackupEntry]:
        """List all backups for a file, **newest first**.

        Returns an empty list if no backups exist.
        """
        history = self._load_history(original_path)
        return list(reversed(history.backups))

    def get_backup(
        self,
        original_path: str,
        backup_id: str | None = None,
    ) -> BackupEntry:
        """Look up a specific backup entry.

        Args:
            original_path: The resolved absolute path of the original file.
            backup_id: The backup ID to find.  If ``None``, returns the
                **most recent** backup.

        Raises:
            ValueError: If no backups exist or the specified ID is not found.
        """
        history = self._load_history(original_path)
        if not history.backups:
            raise ValueError(f"No edit history found for: {original_path}")

        if backup_id is None:
            return history.backups[-1]

        for entry in history.backups:
            if entry.id == backup_id:
                return entry

        available = [b.id for b in history.backups]
        raise ValueError(
            f"Backup '{backup_id}' not found for {original_path}. "
            f"Available IDs: {available}"
        )

    def read_backup(
        self,
        original_path: str,
        backup_id: str | None = None,
    ) -> tuple[BackupEntry, bytes]:
        """Read a backup's content.

        Returns:
            A tuple of (entry, raw_bytes).

        Raises:
            ValueError: If the backup ID is not found.
            FileNotFoundError: If the ``.bak`` file is missing on disk.
        """
        entry = self.get_backup(original_path, backup_id)
        file_dir = self._file_dir(original_path)
        backup_path = file_dir / entry.filename
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file missing on disk: {backup_path}")
        return entry, backup_path.read_bytes()

    def delete_backup(
        self,
        original_path: str,
        backup_id: str,
    ) -> bool:
        """Delete a specific backup. Returns True if found and deleted."""
        history = self._load_history(original_path)
        file_dir = self._file_dir(original_path)

        for i, entry in enumerate(history.backups):
            if entry.id == backup_id:
                backup_path = file_dir / entry.filename
                try:
                    backup_path.unlink(missing_ok=True)
                except OSError:
                    pass
                history.backups.pop(i)
                self._save_history(history)
                return True
        return False

    def cleanup(
        self,
        max_age_days: int = _DEFAULT_MAX_AGE_DAYS,
    ) -> int:
        """Remove backups older than *max_age_days* across all files.

        Returns the total number of backups removed.
        """
        cutoff = datetime.now(_CST) - timedelta(days=max_age_days)
        total_removed = 0

        if not self.base_dir.exists():
            return 0

        for file_dir in self.base_dir.iterdir():
            if not file_dir.is_dir():
                continue
            meta_path = file_dir / "meta.json"
            if not meta_path.exists():
                continue

            try:
                data = json.loads(meta_path.read_text("utf-8"))
                history = FileHistory.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                continue

            original_count = len(history.backups)
            surviving: list[BackupEntry] = []
            for entry in history.backups:
                try:
                    ts = datetime.fromisoformat(entry.timestamp)
                except ValueError:
                    # Can't parse timestamp → keep it (conservative)
                    surviving.append(entry)
                    continue
                if ts >= cutoff:
                    surviving.append(entry)
                else:
                    backup_path = file_dir / entry.filename
                    try:
                        backup_path.unlink(missing_ok=True)
                    except OSError:
                        pass

            removed = original_count - len(surviving)
            if removed > 0:
                history.backups = surviving
                self._save_history(history)
                total_removed += removed

            # Clean up empty directories
            if not surviving:
                try:
                    # Remove all remaining .bak files if any
                    for bak in file_dir.glob("*.bak"):
                        bak.unlink(missing_ok=True)
                    meta_path.unlink(missing_ok=True)
                    file_dir.rmdir()
                except OSError:
                    pass

        return total_removed


# ---------------------------------------------------------------------------
# Module-level convenience instance
# ---------------------------------------------------------------------------

_manager: EditHistoryManager | None = None


def get_history_manager() -> EditHistoryManager:
    """Get or create the singleton EditHistoryManager."""
    global _manager
    if _manager is None:
        _manager = EditHistoryManager()
    return _manager
