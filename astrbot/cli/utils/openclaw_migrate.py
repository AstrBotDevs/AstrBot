from __future__ import annotations

import datetime as dt
import json
import shutil
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import click

from .basic import check_astrbot_root
from .openclaw_toml import json_to_toml

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


def _timestamp_from_epoch(raw: float | int | str) -> str | None:
    ts = float(raw)
    if ts > 1e12:
        ts /= 1000.0
    try:
        return dt.datetime.fromtimestamp(ts, tz=dt.timezone.utc).isoformat()
    except Exception:
        return None


def _normalize_timestamp(raw: Any) -> str | None:
    if raw is None:
        return None

    if isinstance(raw, (int, float)):
        normalized = _timestamp_from_epoch(raw)
        return normalized if normalized is not None else str(raw)

    text = str(raw).strip()
    if not text:
        return None

    if text.isdigit():
        normalized = _timestamp_from_epoch(text)
        return normalized if normalized is not None else text

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


def _discover_memory_columns(
    cursor: sqlite3.Cursor, db_path: Path
) -> tuple[str, str, str | None, str | None]:
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
    return key_col, content_col, category_col, ts_col


def _read_openclaw_sqlite_entries(db_path: Path) -> list[MemoryEntry]:
    if not db_path.exists():
        return []

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.cursor()
        table_exists = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='memories' LIMIT 1"
        ).fetchone()
        if table_exists is None:
            return []

        key_col, content_col, category_col, ts_col = _discover_memory_columns(
            cursor, db_path
        )

        select_clauses = [
            f"{key_col} AS __key__",
            f"{content_col} AS __content__",
            (
                f"{category_col} AS __category__"
                if category_col is not None
                else "'core' AS __category__"
            ),
            f"{ts_col} AS __timestamp__" if ts_col is not None else "NULL AS __timestamp__",
        ]
        rows = cursor.execute(
            "SELECT " + ", ".join(select_clauses) + " FROM memories"
        ).fetchall()

        entries: list[MemoryEntry] = []
        for idx, row in enumerate(rows):
            content = str(row["__content__"] or "").strip()
            if not content:
                continue

            entries.append(
                MemoryEntry(
                    key=_normalize_key(row["__key__"], idx),
                    content=content,
                    category=str(row["__category__"] or "core").strip().lower()
                    or "core",
                    timestamp=_normalize_timestamp(row["__timestamp__"]),
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
    content = path.read_text(encoding="utf-8", errors="replace")
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


def _entry_signature(entry: MemoryEntry, *, semantic: bool) -> str:
    if semantic:
        parts = [entry.content.strip(), entry.category.strip()]
    else:
        parts = [
            entry.key.strip(),
            entry.content.strip(),
            entry.category.strip(),
            entry.timestamp or "",
        ]
    return "\x00".join(parts)


def _dedup_entries(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    seen_exact: set[str] = set()
    seen_semantic: set[str] = set()
    deduped: list[MemoryEntry] = []
    for item in entries:
        exact_signature = _entry_signature(item, semantic=False)
        semantic_signature = _entry_signature(item, semantic=True)
        if exact_signature in seen_exact or semantic_signature in seen_semantic:
            continue
        seen_exact.add(exact_signature)
        seen_semantic.add(semantic_signature)
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
        lines.append(f"- [{ts}] ({entry.category}) `{entry.key}`: {snippet}")

    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _load_json_or_raise(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise click.ClickException(
            f"Failed to parse OpenClaw config JSON at {path}: {exc.msg} "
            f"(line {exc.lineno}, column {exc.colno})"
        ) from exc


def _build_report(
    *,
    source_root: Path,
    workspace_dir: Path,
    target_dir: Path | None,
    dry_run: bool,
    sqlite_entries: list[MemoryEntry],
    markdown_entries: list[MemoryEntry],
    memory_entries: list[MemoryEntry],
    workspace_files: list[Path],
    workspace_bytes_total: int,
    config_found: bool,
    copied_workspace_files: int,
    copied_memory_entries: int,
    wrote_timeline: bool,
    wrote_config_toml: bool,
) -> MigrationReport:
    return MigrationReport(
        source_root=str(source_root),
        source_workspace=str(workspace_dir),
        target_dir=str(target_dir) if target_dir else None,
        dry_run=dry_run,
        memory_entries_total=len(memory_entries),
        memory_entries_from_sqlite=len(sqlite_entries),
        memory_entries_from_markdown=len(markdown_entries),
        workspace_files_total=len(workspace_files),
        workspace_bytes_total=workspace_bytes_total,
        config_found=config_found,
        copied_workspace_files=copied_workspace_files,
        copied_memory_entries=copied_memory_entries,
        wrote_timeline=wrote_timeline,
        wrote_config_toml=wrote_config_toml,
    )


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
        config_obj = _load_json_or_raise(config_json_path)

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

    report = _build_report(
        source_root=source_root,
        workspace_dir=workspace_dir,
        target_dir=resolved_target,
        dry_run=dry_run,
        sqlite_entries=sqlite_entries,
        markdown_entries=markdown_entries,
        memory_entries=memory_entries,
        workspace_files=workspace_files,
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
