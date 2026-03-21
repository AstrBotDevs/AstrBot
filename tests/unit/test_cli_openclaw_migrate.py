from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from astrbot.cli.commands.cmd_migrate import (
    _read_openclaw_sqlite_entries,
    run_openclaw_migration,
)


def _prepare_astrbot_root(root: Path) -> None:
    (root / ".astrbot").touch()
    (root / "data").mkdir(parents=True, exist_ok=True)


def _prepare_openclaw_source(source_root: Path) -> None:
    workspace = source_root / "workspace"
    (workspace / "memory").mkdir(parents=True, exist_ok=True)
    (workspace / "notes").mkdir(parents=True, exist_ok=True)

    db_path = workspace / "memory" / "brain.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE memories (id TEXT, value TEXT, type TEXT, updated_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO memories (id, value, type, updated_at) VALUES (?, ?, ?, ?)",
            ("user_pref", "likes rust", "core", 1700000000),
        )
        conn.commit()
    finally:
        conn.close()

    (workspace / "MEMORY.md").write_text(
        "# Memory\n- **style**: concise\n- keep logs\n",
        encoding="utf-8",
    )
    (workspace / "memory" / "2026-03-20.md").write_text(
        "- **todo**: migrate artifacts\n",
        encoding="utf-8",
    )
    (workspace / "notes" / "readme.txt").write_text(
        "workspace artifact",
        encoding="utf-8",
    )
    (source_root / "config.json").write_text(
        json.dumps(
            {
                "model": "gpt-4.1-mini",
                "memory": {"enabled": True, "limit": 4096},
                "skills": [{"name": "planner", "enabled": True}],
            }
        ),
        encoding="utf-8",
    )


def test_read_openclaw_sqlite_entries_supports_legacy_columns(tmp_path: Path) -> None:
    db_dir = tmp_path / "memory"
    db_dir.mkdir(parents=True)
    db_path = db_dir / "brain.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE memories (id TEXT, value TEXT, type TEXT, updated_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO memories (id, value, type, updated_at) VALUES (?, ?, ?, ?)",
            ("legacy_key", "legacy_value", "daily", 1700000000),
        )
        conn.commit()
    finally:
        conn.close()

    entries = _read_openclaw_sqlite_entries(db_path)
    assert len(entries) == 1
    assert entries[0].key == "legacy_key"
    assert entries[0].content == "legacy_value"
    assert entries[0].category == "daily"
    assert entries[0].timestamp is not None


def test_run_openclaw_migration_dry_run(tmp_path: Path) -> None:
    source_root = tmp_path / ".openclaw"
    source_root.mkdir(parents=True)
    _prepare_openclaw_source(source_root)

    astrbot_root = tmp_path / "astrbot"
    astrbot_root.mkdir(parents=True)
    _prepare_astrbot_root(astrbot_root)

    report = run_openclaw_migration(
        source_root=source_root,
        astrbot_root=astrbot_root,
        dry_run=True,
    )

    assert report.dry_run is True
    assert report.memory_entries_total >= 3
    assert report.workspace_files_total >= 3
    assert report.config_found is True
    assert report.target_dir is None
    assert not (astrbot_root / "data" / "migrations" / "openclaw").exists()


def test_run_openclaw_migration_writes_artifacts(tmp_path: Path) -> None:
    source_root = tmp_path / ".openclaw"
    source_root.mkdir(parents=True)
    _prepare_openclaw_source(source_root)

    astrbot_root = tmp_path / "astrbot"
    astrbot_root.mkdir(parents=True)
    _prepare_astrbot_root(astrbot_root)

    report = run_openclaw_migration(
        source_root=source_root,
        astrbot_root=astrbot_root,
        dry_run=False,
        target_dir=Path("data/migrations/openclaw/test-run"),
    )

    assert report.dry_run is False
    assert report.target_dir is not None
    target = Path(report.target_dir)
    assert target.exists()

    assert (target / "migration_summary.json").exists()
    assert (target / "memory_entries.jsonl").exists()
    assert (target / "time_brief_history.md").exists()
    assert (target / "config.original.json").exists()
    assert (target / "config.migrated.toml").exists()
    assert (target / "workspace" / "notes" / "readme.txt").exists()

    timeline = (target / "time_brief_history.md").read_text(encoding="utf-8")
    assert "Time Brief History" in timeline
    assert "时间简史" in timeline

    toml_text = (target / "config.migrated.toml").read_text(encoding="utf-8")
    assert "model = " in toml_text
    assert "[memory]" in toml_text
    assert "[[skills]]" in toml_text

