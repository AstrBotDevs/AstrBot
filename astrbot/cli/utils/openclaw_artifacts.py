from __future__ import annotations

import datetime as dt
import json
import os
import shutil
from pathlib import Path
from typing import Any

import click

from .openclaw_models import MemoryEntry
from .openclaw_toml import json_to_toml


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def collect_workspace_files(
    workspace_dir: Path, *, exclude_dir: Path | None = None
) -> list[Path]:
    files: list[Path] = []
    exclude_resolved = exclude_dir.resolve() if exclude_dir is not None else None

    for root, dirnames, filenames in os.walk(
        workspace_dir, topdown=True, followlinks=False
    ):
        root_path = Path(root)

        pruned_dirs: list[str] = []
        for dirname in dirnames:
            dir_path = root_path / dirname
            if dir_path.is_symlink():
                continue
            if exclude_resolved is not None and _is_within(dir_path, exclude_resolved):
                continue
            pruned_dirs.append(dirname)
        dirnames[:] = pruned_dirs

        for filename in filenames:
            path = root_path / filename
            if path.is_symlink() or not path.is_file():
                continue
            if exclude_resolved is not None and _is_within(path, exclude_resolved):
                continue
            files.append(path)

    return sorted(files)


def workspace_total_size(files: list[Path]) -> int:
    total_bytes = 0
    for path in files:
        try:
            total_bytes += path.stat().st_size
        except OSError:
            # Best-effort accounting: files may disappear or become unreadable
            # during migration scans.
            continue
    return total_bytes


def _write_jsonl(path: Path, entries: list[MemoryEntry]) -> None:
    with path.open("w", encoding="utf-8") as fp:
        for entry in entries:
            fp.write(
                json.dumps(
                    {
                        "key": entry.key,
                        "content": entry.content,
                        "category": entry.category,
                        "timestamp": entry.timestamp,
                        "source": entry.source,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )


def _write_timeline(path: Path, entries: list[MemoryEntry], source_root: Path) -> None:
    ordered = sorted(entries, key=lambda e: (e.timestamp or "", e.order))

    lines: list[str] = []
    lines.append("# OpenClaw Migration - Time Brief History")
    lines.append("")
    lines.append("> 时间简史（初步方案）：按时间汇总可迁移记忆条目。")
    lines.append("")
    lines.append(f"- Generated at: {dt.datetime.now(dt.timezone.utc).isoformat()}")
    lines.append(f"- Source: `{source_root}`")
    lines.append(f"- Total entries: {len(ordered)}")
    lines.append("")
    lines.append("## Timeline")
    lines.append("")

    for entry in ordered:
        ts = entry.timestamp or "unknown"
        snippet = entry.content.replace("\n", " ").strip()
        if len(snippet) > 160:
            snippet = snippet[:157] + "..."
        safe_key = (entry.key or "").replace("`", "\\`")
        safe_snippet = snippet.replace("`", "\\`")
        lines.append(f"- [{ts}] ({entry.category}) `{safe_key}`: {safe_snippet}")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def write_migration_artifacts(
    *,
    workspace_dir: Path,
    workspace_files: list[Path],
    resolved_target: Path,
    source_root: Path,
    memory_entries: list[MemoryEntry],
    config_obj: dict[str, Any] | None,
    config_json_path: Path | None,
) -> tuple[int, int, bool, bool]:
    workspace_target = resolved_target / "workspace"
    workspace_target.mkdir(parents=True, exist_ok=True)

    copied_workspace_files = 0
    for src_file in workspace_files:
        rel_path = src_file.relative_to(workspace_dir)
        dst_file = workspace_target / rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dst_file)
        copied_workspace_files += 1

    copied_memory_entries = 0
    wrote_timeline = False
    if memory_entries:
        _write_jsonl(resolved_target / "memory_entries.jsonl", memory_entries)
        copied_memory_entries = len(memory_entries)
        _write_timeline(
            resolved_target / "time_brief_history.md",
            memory_entries,
            source_root,
        )
        wrote_timeline = True

    wrote_config_toml = False
    if config_obj is not None:
        (resolved_target / "config.original.json").write_text(
            json.dumps(config_obj, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            converted_toml = json_to_toml(config_obj)
        except ValueError as exc:
            source_hint = str(config_json_path) if config_json_path else "config JSON"
            raise click.ClickException(
                f"Failed to convert {source_hint} to TOML: {exc}"
            ) from exc
        (resolved_target / "config.migrated.toml").write_text(
            converted_toml,
            encoding="utf-8",
        )
        wrote_config_toml = True

    return copied_workspace_files, copied_memory_entries, wrote_timeline, wrote_config_toml


__all__ = ["collect_workspace_files", "workspace_total_size", "write_migration_artifacts"]
