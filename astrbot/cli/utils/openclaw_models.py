from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MemoryEntry:
    key: str
    content: str
    category: str
    timestamp: str | None
    source: str
    order: int


@dataclass(slots=True)
class MigrationReport:
    source_root: str
    source_workspace: str
    target_dir: str | None
    dry_run: bool
    memory_entries_total: int
    memory_entries_from_sqlite: int
    memory_entries_from_markdown: int
    workspace_files_total: int
    workspace_bytes_total: int
    config_found: bool
    copied_workspace_files: int
    copied_memory_entries: int
    wrote_timeline: bool
    wrote_config_toml: bool


__all__ = ["MemoryEntry", "MigrationReport"]
