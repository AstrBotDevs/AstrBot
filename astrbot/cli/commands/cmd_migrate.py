from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import click

from ..utils import check_astrbot_root, get_astrbot_root

SQLITE_KEY_CANDIDATES = ("key", "id", "name")
SQLITE_CONTENT_CANDIDATES = ("content", "value", "text", "memory")
SQLITE_CATEGORY_CANDIDATES = ("category", "kind", "type")
SQLITE_TS_CANDIDATES = ("updated_at", "created_at", "timestamp", "ts", "time")


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


def _pick_existing_column(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _normalize_timestamp(raw: Any) -> str | None:
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        ts = float(raw)
        if ts > 1e12:
            ts = ts / 1000.0
        try:
            return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()
        except Exception:
            return str(raw)

    text = str(raw).strip()
    if not text:
        return None

    if text.isdigit():
        return _normalize_timestamp(int(text))

    maybe_iso = text.replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(maybe_iso)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.isoformat()
    except Exception:
        return text


def _normalize_key(raw: Any, fallback_idx: int) -> str:
    text = str(raw).strip() if raw is not None else ""
    if text:
        return text
    return f"openclaw_{fallback_idx}"


def _parse_structured_line(line: str) -> tuple[str, str] | None:
    if not line.startswith("**"):
        return None
    rest = line[2:]
    marker = "**:"
    marker_idx = rest.find(marker)
    if marker_idx <= 0:
        return None
    key = rest[:marker_idx].strip()
    value = rest[marker_idx + len(marker) :].strip()
    if not key or not value:
        return None
    return key, value


def _read_openclaw_sqlite_entries(db_path: Path) -> list[MemoryEntry]:
    if not db_path.exists():
        return []

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cursor = conn.cursor()
        table_exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories' LIMIT 1"
        ).fetchone()
        if table_exists is None:
            return []

        columns = {
            str(row[1]).strip().lower()
            for row in cursor.execute("PRAGMA table_info(memories)").fetchall()
        }

        key_col = _pick_existing_column(columns, SQLITE_KEY_CANDIDATES) or "rowid"
        content_col = _pick_existing_column(columns, SQLITE_CONTENT_CANDIDATES)
        if content_col is None:
            raise click.ClickException(
                f"OpenClaw sqlite exists at {db_path}, but no content-like column found"
            )
        category_col = _pick_existing_column(columns, SQLITE_CATEGORY_CANDIDATES)
        ts_col = _pick_existing_column(columns, SQLITE_TS_CANDIDATES)

        selected_cols = [key_col, content_col]
        if category_col is not None:
            selected_cols.append(category_col)
        if ts_col is not None and ts_col not in selected_cols:
            selected_cols.append(ts_col)

        sql = "SELECT " + ", ".join(selected_cols) + " FROM memories"
        rows = cursor.execute(sql).fetchall()

        entries: list[MemoryEntry] = []
        for idx, row in enumerate(rows):
            row_values = list(row)
            key_raw = row_values[0] if row_values else None
            content_raw = row_values[1] if len(row_values) > 1 else ""
            category_raw = row_values[2] if category_col is not None and len(row_values) > 2 else "core"
            ts_index = len(row_values) - 1 if ts_col is not None else -1
            ts_raw = row_values[ts_index] if ts_col is not None and row_values else None

            content = str(content_raw).strip()
            if not content:
                continue

            entries.append(
                MemoryEntry(
                    key=_normalize_key(key_raw, idx),
                    content=content,
                    category=str(category_raw or "core").strip().lower() or "core",
                    timestamp=_normalize_timestamp(ts_raw),
                    source=f"sqlite:{db_path}",
                    order=idx,
                )
            )

        return entries
    finally:
        conn.close()


def _parse_markdown_file(
    path: Path, default_category: str, stem: str, order_offset: int
) -> list[MemoryEntry]:
    content = path.read_text(encoding="utf-8", errors="ignore")
    mtime = _normalize_timestamp(path.stat().st_mtime)
    entries: list[MemoryEntry] = []
    line_no = 0
    for raw_line in content.splitlines():
        line_no += 1
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        line = stripped[2:] if stripped.startswith("- ") else stripped
        parsed = _parse_structured_line(line)
        if parsed is not None:
            key, text = parsed
            key = _normalize_key(key, line_no)
            body = text.strip()
        else:
            key = f"openclaw_{stem}_{line_no}"
            body = line.strip()

        if not body:
            continue

        entries.append(
            MemoryEntry(
                key=key,
                content=body,
                category=default_category,
                timestamp=mtime,
                source=f"markdown:{path}",
                order=order_offset + len(entries),
            )
        )
    return entries


def _read_openclaw_markdown_entries(workspace_dir: Path) -> list[MemoryEntry]:
    entries: list[MemoryEntry] = []

    core_path = workspace_dir / "MEMORY.md"
    if core_path.exists():
        entries.extend(
            _parse_markdown_file(
                core_path,
                default_category="core",
                stem="core",
                order_offset=len(entries),
            )
        )

    daily_dir = workspace_dir / "memory"
    if daily_dir.exists():
        for md_path in sorted(daily_dir.glob("*.md")):
            stem = md_path.stem or "daily"
            entries.extend(
                _parse_markdown_file(
                    md_path,
                    default_category="daily",
                    stem=stem,
                    order_offset=len(entries),
                )
            )

    return entries


def _dedup_entries(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    seen: set[str] = set()
    deduped: list[MemoryEntry] = []
    for item in entries:
        signature = "\x00".join(
            [
                item.key.strip(),
                item.content.strip(),
                item.category.strip(),
                item.timestamp or "",
            ]
        )
        if signature in seen:
            continue
        seen.add(signature)
        deduped.append(item)
    return deduped


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


def _collect_workspace_files(workspace_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in workspace_dir.rglob("*"):
        if path.is_file() and not path.is_symlink():
            files.append(path)
    return sorted(files)


def _toml_escape(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    escaped = escaped.replace("\n", "\\n")
    return f'"{escaped}"'


def _toml_literal(value: Any) -> str:
    if value is None:
        return '"__NULL__"'
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _toml_escape(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_literal(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{ " + ", ".join(f"{k} = {_toml_literal(v)}" for k, v in value.items()) + " }"
    return _toml_escape(str(value))


def _json_to_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []

    def emit_table(obj: dict[str, Any], path: list[str]) -> None:
        scalar_items: list[tuple[str, Any]] = []
        nested_dicts: list[tuple[str, dict[str, Any]]] = []
        array_tables: list[tuple[str, list[dict[str, Any]]]] = []

        for key, value in obj.items():
            if isinstance(value, dict):
                nested_dicts.append((key, value))
            elif isinstance(value, list) and value and all(
                isinstance(item, dict) for item in value
            ):
                array_tables.append((key, value))
            else:
                scalar_items.append((key, value))

        if path:
            lines.append(f"[{'.'.join(path)}]")
        for key, value in scalar_items:
            lines.append(f"{key} = {_toml_literal(value)}")
        if scalar_items and (nested_dicts or array_tables):
            lines.append("")

        for idx, (key, value) in enumerate(nested_dicts):
            emit_table(value, [*path, key])
            if idx != len(nested_dicts) - 1 or array_tables:
                lines.append("")

        for t_idx, (key, items) in enumerate(array_tables):
            for item in items:
                lines.append(f"[[{'.'.join([*path, key])}]]")
                for sub_key, sub_value in item.items():
                    lines.append(f"{sub_key} = {_toml_literal(sub_value)}")
                lines.append("")
            if t_idx == len(array_tables) - 1 and lines and lines[-1] == "":
                lines.pop()

    emit_table(data, [])
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"


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
    ordered = sorted(
        entries,
        key=lambda e: (
            e.timestamp or "",
            e.order,
        ),
    )

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
        lines.append(f"- [{ts}] ({entry.category}) `{entry.key}`: {snippet}")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


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
    sqlite_entries = _read_openclaw_sqlite_entries(workspace_dir / "memory" / "brain.db")
    markdown_entries = _read_openclaw_markdown_entries(workspace_dir)
    memory_entries = _dedup_entries([*sqlite_entries, *markdown_entries])

    workspace_files = _collect_workspace_files(workspace_dir)
    workspace_total_bytes = sum(path.stat().st_size for path in workspace_files)

    config_json_path = _find_openclaw_config_json(source_root, workspace_dir)
    config_obj: dict[str, Any] | None = None
    if config_json_path is not None:
        config_obj = json.loads(config_json_path.read_text(encoding="utf-8"))

    resolved_target: Path | None = None
    if target_dir is not None:
        resolved_target = (
            target_dir if target_dir.is_absolute() else (astrbot_root / target_dir)
        )
    elif not dry_run:
        run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        resolved_target = (
            astrbot_root / "data" / "migrations" / "openclaw" / f"run-{run_id}"
        )

    copied_workspace_files = 0
    copied_memory_entries = 0
    wrote_timeline = False
    wrote_config_toml = False

    if not dry_run and resolved_target is not None:
        resolved_target.mkdir(parents=True, exist_ok=True)
        workspace_target = resolved_target / "workspace"
        workspace_target.mkdir(parents=True, exist_ok=True)

        for src_file in workspace_files:
            rel_path = src_file.relative_to(workspace_dir)
            dst_file = workspace_target / rel_path
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied_workspace_files += 1

        if memory_entries:
            _write_jsonl(resolved_target / "memory_entries.jsonl", memory_entries)
            copied_memory_entries = len(memory_entries)
            _write_timeline(
                resolved_target / "time_brief_history.md",
                memory_entries,
                source_root,
            )
            wrote_timeline = True

        if config_obj is not None:
            (resolved_target / "config.original.json").write_text(
                json.dumps(config_obj, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (resolved_target / "config.migrated.toml").write_text(
                _json_to_toml(config_obj),
                encoding="utf-8",
            )
            wrote_config_toml = True

        summary = MigrationReport(
            source_root=str(source_root),
            source_workspace=str(workspace_dir),
            target_dir=str(resolved_target),
            dry_run=dry_run,
            memory_entries_total=len(memory_entries),
            memory_entries_from_sqlite=len(sqlite_entries),
            memory_entries_from_markdown=len(markdown_entries),
            workspace_files_total=len(workspace_files),
            workspace_bytes_total=workspace_total_bytes,
            config_found=config_obj is not None,
            copied_workspace_files=copied_workspace_files,
            copied_memory_entries=copied_memory_entries,
            wrote_timeline=wrote_timeline,
            wrote_config_toml=wrote_config_toml,
        )
        (resolved_target / "migration_summary.json").write_text(
            json.dumps(asdict(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return summary

    return MigrationReport(
        source_root=str(source_root),
        source_workspace=str(workspace_dir),
        target_dir=str(resolved_target) if resolved_target else None,
        dry_run=dry_run,
        memory_entries_total=len(memory_entries),
        memory_entries_from_sqlite=len(sqlite_entries),
        memory_entries_from_markdown=len(markdown_entries),
        workspace_files_total=len(workspace_files),
        workspace_bytes_total=workspace_total_bytes,
        config_found=config_obj is not None,
        copied_workspace_files=0,
        copied_memory_entries=0,
        wrote_timeline=False,
        wrote_config_toml=False,
    )


@click.group(name="migrate")
def migrate() -> None:
    """Data migration utilities for external runtimes."""


@migrate.command(name="openclaw")
@click.option(
    "--source",
    "source_path",
    type=click.Path(path_type=Path, file_okay=False, resolve_path=True),
    default=None,
    help="Path to OpenClaw root directory (default: ~/.openclaw).",
)
@click.option(
    "--target",
    "target_path",
    type=click.Path(path_type=Path, file_okay=False, resolve_path=True),
    default=None,
    help=(
        "Custom output directory. If omitted, writes to "
        "data/migrations/openclaw/run-<timestamp>."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview migration candidates without writing files.",
)
def migrate_openclaw(
    source_path: Path | None,
    target_path: Path | None,
    dry_run: bool,
) -> None:
    """Migrate OpenClaw workspace snapshots into AstrBot migration artifacts."""

    astrbot_root = get_astrbot_root()
    source_root = source_path or (Path.home() / ".openclaw")

    report = run_openclaw_migration(
        source_root=source_root,
        astrbot_root=astrbot_root,
        dry_run=dry_run,
        target_dir=target_path,
    )

    click.echo("OpenClaw migration report:")
    click.echo(f"  Source root:        {report.source_root}")
    click.echo(f"  Source workspace:   {report.source_workspace}")
    click.echo(f"  Dry run:            {report.dry_run}")
    click.echo(f"  Memory entries:     {report.memory_entries_total}")
    click.echo(f"    - sqlite:         {report.memory_entries_from_sqlite}")
    click.echo(f"    - markdown:       {report.memory_entries_from_markdown}")
    click.echo(f"  Workspace files:    {report.workspace_files_total}")
    click.echo(f"  Workspace size:     {report.workspace_bytes_total} bytes")
    click.echo(f"  Config found:       {report.config_found}")

    if dry_run:
        click.echo("")
        click.echo("Dry-run mode: no files were written.")
        click.echo("Run without --dry-run to perform migration.")
        return

    click.echo("")
    click.echo(f"Migration output:     {report.target_dir}")
    click.echo(f"  Copied files:       {report.copied_workspace_files}")
    click.echo(f"  Imported memories:  {report.copied_memory_entries}")
    click.echo(f"  Timeline written:   {report.wrote_timeline}")
    click.echo(f"  Config TOML written:{report.wrote_config_toml}")
    click.echo("Done.")


__all__ = [
    "MigrationReport",
    "MemoryEntry",
    "_json_to_toml",
    "_read_openclaw_sqlite_entries",
    "migrate",
    "run_openclaw_migration",
]

