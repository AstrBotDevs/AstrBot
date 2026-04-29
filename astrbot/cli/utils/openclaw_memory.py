from __future__ import annotations

import datetime as dt
import sqlite3
from pathlib import Path
from typing import Any

import click

from .openclaw_models import MemoryEntry

SQLITE_KEY_CANDIDATES = ("key", "id", "name")
SQLITE_CONTENT_CANDIDATES = ("content", "value", "text", "memory")
SQLITE_CATEGORY_CANDIDATES = ("category", "kind", "type")
SQLITE_TS_CANDIDATES = ("updated_at", "created_at", "timestamp", "ts", "time")


def _pick_existing_column(columns: set[str], candidates: tuple[str, ...]) -> str | None:
    for candidate in candidates:
        if candidate in columns:
            return candidate
    return None


def _timestamp_from_epoch(raw: float | int | str) -> str | None:
    try:
        ts = float(raw)
        if ts > 1e12:
            ts /= 1000.0
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
    table_info_rows = cursor.execute("PRAGMA table_info(memories)").fetchall()
    columns_in_order = [
        str(row[1]).strip().lower() for row in table_info_rows if str(row[1]).strip()
    ]
    columns = set(columns_in_order)

    key_col = _pick_existing_column(columns, SQLITE_KEY_CANDIDATES)
    if key_col is None:
        pk_columns = sorted(
            (
                (int(row[5]), str(row[1]).strip().lower())
                for row in table_info_rows
                if int(row[5]) > 0 and str(row[1]).strip()
            ),
            key=lambda item: item[0],
        )
        if pk_columns:
            key_col = pk_columns[0][1]
    if key_col is None:
        try:
            cursor.execute("SELECT rowid FROM memories LIMIT 1").fetchone()
            key_col = "rowid"
        except sqlite3.Error:
            key_col = columns_in_order[0] if columns_in_order else None

    content_col = _pick_existing_column(columns, SQLITE_CONTENT_CANDIDATES)
    if content_col is None:
        raise click.ClickException(
            f"OpenClaw sqlite exists at {db_path}, but no content-like column found"
        )
    if key_col is None:
        raise click.ClickException(
            f"OpenClaw sqlite exists at {db_path}, but no key-like or usable fallback column found"
        )
    category_col = _pick_existing_column(columns, SQLITE_CATEGORY_CANDIDATES)
    ts_col = _pick_existing_column(columns, SQLITE_TS_CANDIDATES)
    return key_col, content_col, category_col, ts_col


def _read_openclaw_sqlite_entries(db_path: Path) -> list[MemoryEntry]:
    if not db_path.exists():
        return []

    conn: sqlite3.Connection | None = None
    try:
        db_uri = f"{db_path.resolve().as_uri()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True)
        conn.row_factory = sqlite3.Row
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
            f"{ts_col} AS __timestamp__"
            if ts_col is not None
            else "NULL AS __timestamp__",
        ]
        order_by_clause = (
            " ORDER BY __timestamp__ ASC, __key__ ASC"
            if ts_col is not None
            else " ORDER BY __key__ ASC"
        )
        rows = cursor.execute(
            "SELECT " + ", ".join(select_clauses) + " FROM memories" + order_by_clause
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
    except sqlite3.Error as exc:
        raise click.ClickException(
            f"Failed to read OpenClaw sqlite at {db_path}: {exc}"
        ) from exc
    finally:
        if conn is not None:
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


def _dedup_entries(entries: list[MemoryEntry]) -> list[MemoryEntry]:
    seen_exact: set[tuple[str, str, str, str]] = set()
    seen_semantic: set[tuple[str, str]] = set()
    deduped: list[MemoryEntry] = []

    for item in entries:
        exact_key = (
            item.key.strip(),
            item.content.strip(),
            item.category.strip(),
            item.timestamp or "",
        )
        semantic_key = (item.content.strip(), item.category.strip())
        if exact_key in seen_exact or semantic_key in seen_semantic:
            continue
        seen_exact.add(exact_key)
        seen_semantic.add(semantic_key)
        deduped.append(item)

    return deduped


def collect_memory_entries(workspace_dir: Path) -> tuple[list[MemoryEntry], int, int]:
    sqlite_entries = _read_openclaw_sqlite_entries(
        workspace_dir / "memory" / "brain.db"
    )
    markdown_entries = _read_openclaw_markdown_entries(workspace_dir)
    memory_entries = _dedup_entries([*sqlite_entries, *markdown_entries])
    return memory_entries, len(sqlite_entries), len(markdown_entries)


__all__ = ["collect_memory_entries"]
