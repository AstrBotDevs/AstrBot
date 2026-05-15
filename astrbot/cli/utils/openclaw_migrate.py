from __future__ import annotations

import datetime as dt
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from .basic import check_astrbot_root
from .openclaw_artifacts import (
    collect_workspace_files,
    workspace_total_size,
    write_migration_artifacts,
)
from .openclaw_memory import collect_memory_entries
from .openclaw_models import MemoryEntry, MigrationReport


def _find_source_workspace(source_root: Path) -> Path:
    candidate = source_root / "workspace"
    if candidate.exists() and candidate.is_dir():
        return candidate
    return source_root


def _find_openclaw_config_json(source_root: Path, workspace_dir: Path) -> Path | None:
    candidates = [
        source_root / "config.json",
        source_root / "settings.json",
        workspace_dir / "config.json",
        workspace_dir / "settings.json",
    ]
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _load_json_or_raise(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"Failed to parse OpenClaw config JSON at {path}: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc


def _resolve_explicit_target_dir(
    astrbot_root: Path, target_dir: Path | None
) -> Path | None:
    if target_dir is None:
        return None
    return target_dir if target_dir.is_absolute() else (astrbot_root / target_dir)


def _resolve_output_target_dir(
    astrbot_root: Path, target_dir: Path | None, dry_run: bool
) -> Path | None:
    if dry_run:
        return None
    explicit_target = _resolve_explicit_target_dir(astrbot_root, target_dir)
    if explicit_target is not None:
        return explicit_target
    run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    return astrbot_root / "data" / "migrations" / "openclaw" / f"run-{run_id}"


def run_openclaw_migration(
    *,
    source_root: Path,
    astrbot_root: Path,
    dry_run: bool = False,
    target_dir: Path | None = None,
) -> MigrationReport:
    if not source_root.exists() or not source_root.is_dir():
        raise click.ClickException(f"OpenClaw source not found: {source_root}")

    if not check_astrbot_root(astrbot_root):
        raise click.ClickException(
            f"{astrbot_root} is not a valid AstrBot root. Run from initialized AstrBot root."
        )

    workspace_dir = _find_source_workspace(source_root)
    memory_entries, from_sqlite, from_markdown = collect_memory_entries(workspace_dir)

    explicit_target_dir = _resolve_explicit_target_dir(astrbot_root, target_dir)
    workspace_files = collect_workspace_files(
        workspace_dir,
        exclude_dir=explicit_target_dir,
    )
    workspace_total_bytes = workspace_total_size(workspace_files)

    config_json_path = _find_openclaw_config_json(source_root, workspace_dir)
    config_obj: dict[str, Any] | None = None
    if config_json_path is not None:
        config_obj = _load_json_or_raise(config_json_path)

    resolved_target = _resolve_output_target_dir(astrbot_root, target_dir, dry_run)

    copied_workspace_files = 0
    copied_memory_entries = 0
    wrote_timeline = False
    wrote_config_toml = False

    if not dry_run and resolved_target is not None:
        resolved_target.mkdir(parents=True, exist_ok=True)
        (
            copied_workspace_files,
            copied_memory_entries,
            wrote_timeline,
            wrote_config_toml,
        ) = write_migration_artifacts(
            workspace_dir=workspace_dir,
            workspace_files=workspace_files,
            resolved_target=resolved_target,
            source_root=source_root,
            memory_entries=memory_entries,
            config_obj=config_obj,
            config_json_path=config_json_path,
        )

    report = MigrationReport(
        source_root=str(source_root),
        source_workspace=str(workspace_dir),
        target_dir=str(resolved_target) if resolved_target else None,
        dry_run=dry_run,
        memory_entries_total=len(memory_entries),
        memory_entries_from_sqlite=from_sqlite,
        memory_entries_from_markdown=from_markdown,
        workspace_files_total=len(workspace_files),
        workspace_bytes_total=workspace_total_bytes,
        config_found=config_obj is not None,
        copied_workspace_files=copied_workspace_files,
        copied_memory_entries=copied_memory_entries,
        wrote_timeline=wrote_timeline,
        wrote_config_toml=wrote_config_toml,
    )

    if not dry_run and resolved_target is not None:
        (resolved_target / "migration_summary.json").write_text(
            json.dumps(asdict(report), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    return report


__all__ = [
    "MemoryEntry",
    "MigrationReport",
    "run_openclaw_migration",
]
