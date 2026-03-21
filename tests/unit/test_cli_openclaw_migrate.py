from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from astrbot.cli.utils.openclaw_migrate import run_openclaw_migration
from astrbot.cli.utils.openclaw_toml import json_to_toml


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


def _read_migrated_memory_entries(target_dir: Path) -> list[dict[str, str | None]]:
    memory_jsonl = target_dir / "memory_entries.jsonl"
    entries: list[dict[str, str | None]] = []
    for line in memory_jsonl.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        entries.append(payload)
    return entries


def test_migration_supports_legacy_sqlite_columns(tmp_path: Path) -> None:
    source_root = tmp_path / ".openclaw"
    workspace = source_root / "workspace"
    db_dir = workspace / "memory"
    db_dir.mkdir(parents=True)
    (workspace / "notes").mkdir(parents=True, exist_ok=True)
    (workspace / "MEMORY.md").write_text("", encoding="utf-8")

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

    astrbot_root = tmp_path / "astrbot"
    astrbot_root.mkdir(parents=True)
    _prepare_astrbot_root(astrbot_root)

    report = run_openclaw_migration(
        source_root=source_root,
        astrbot_root=astrbot_root,
        dry_run=False,
        target_dir=Path("data/migrations/openclaw/test-legacy-sqlite"),
    )

    assert report.target_dir is not None
    entries = _read_migrated_memory_entries(Path(report.target_dir))
    assert len(entries) == 1
    assert entries[0].get("key") == "legacy_key"
    assert entries[0].get("content") == "legacy_value"
    assert entries[0].get("category") == "daily"
    assert entries[0].get("timestamp") is not None


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
    assert '"model" = ' in toml_text
    assert '["memory"]' in toml_text
    assert '[["skills"]]' in toml_text


def test_markdown_parsing_structured_and_plain_lines(tmp_path: Path) -> None:
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
        target_dir=Path("data/migrations/openclaw/test-markdown"),
    )
    assert report.target_dir is not None
    entries = _read_migrated_memory_entries(Path(report.target_dir))

    memory_md_entries = [
        entry
        for entry in entries
        if str(entry.get("source", "")).endswith("workspace/MEMORY.md")
    ]
    style_entries = [entry for entry in memory_md_entries if entry.get("key") == "style"]
    assert len(style_entries) == 1
    assert style_entries[0].get("content") == "concise"

    plain_entries = [
        entry for entry in memory_md_entries if entry.get("content") == "keep logs"
    ]
    assert len(plain_entries) == 1
    assert str(plain_entries[0].get("key", "")).startswith("openclaw_core_")


def test_deduplication_between_sqlite_and_markdown_preserves_order(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / ".openclaw"
    source_root.mkdir(parents=True)
    _prepare_openclaw_source(source_root)

    memory_md = source_root / "workspace" / "MEMORY.md"
    memory_md.write_text(
        memory_md.read_text(encoding="utf-8") + "- likes rust\n",
        encoding="utf-8",
    )

    astrbot_root = tmp_path / "astrbot"
    astrbot_root.mkdir(parents=True)
    _prepare_astrbot_root(astrbot_root)

    report = run_openclaw_migration(
        source_root=source_root,
        astrbot_root=astrbot_root,
        dry_run=False,
        target_dir=Path("data/migrations/openclaw/test-dedup"),
    )
    assert report.target_dir is not None
    entries = _read_migrated_memory_entries(Path(report.target_dir))
    contents = [str(entry.get("content", "")) for entry in entries]

    assert contents.count("likes rust") == 1
    assert contents.index("likes rust") < contents.index("keep logs")


def test_run_openclaw_migration_invalid_config_json_raises_click_exception(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / ".openclaw"
    source_root.mkdir(parents=True)
    _prepare_openclaw_source(source_root)
    (source_root / "config.json").write_text("{ invalid json", encoding="utf-8")

    astrbot_root = tmp_path / "astrbot"
    astrbot_root.mkdir(parents=True)
    _prepare_astrbot_root(astrbot_root)

    import click
    import pytest

    with pytest.raises(click.ClickException) as exc_info:
        run_openclaw_migration(
            source_root=source_root,
            astrbot_root=astrbot_root,
            dry_run=False,
            target_dir=Path("data/migrations/openclaw/test-invalid-config"),
        )

    assert "Failed to parse OpenClaw config JSON" in str(exc_info.value)


def test_run_openclaw_migration_invalid_sqlite_raises_click_exception(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / ".openclaw"
    source_root.mkdir(parents=True)
    workspace = source_root / "workspace"
    (workspace / "memory").mkdir(parents=True, exist_ok=True)
    (workspace / "notes").mkdir(parents=True, exist_ok=True)
    (workspace / "MEMORY.md").write_text("", encoding="utf-8")
    (workspace / "memory" / "brain.db").write_text(
        "not a sqlite database",
        encoding="utf-8",
    )

    astrbot_root = tmp_path / "astrbot"
    astrbot_root.mkdir(parents=True)
    _prepare_astrbot_root(astrbot_root)

    import click
    import pytest

    with pytest.raises(click.ClickException) as exc_info:
        run_openclaw_migration(
            source_root=source_root,
            astrbot_root=astrbot_root,
            dry_run=True,
        )

    err_text = str(exc_info.value)
    assert "Failed to read OpenClaw sqlite at" in err_text
    assert "brain.db" in err_text


def test_json_to_toml_quotes_special_keys() -> None:
    payload = {
        "normal key": "ok",
        "nested.obj": {"x y": 1},
        "list": [{"dot.key": True}],
    }
    toml_text = json_to_toml(payload)

    assert '"normal key" = "ok"' in toml_text
    assert '["nested.obj"]' in toml_text
    assert '"x y" = 1' in toml_text
    assert '[["list"]]' in toml_text
    assert '"dot.key" = true' in toml_text


def test_json_to_toml_rejects_non_finite_float() -> None:
    import pytest

    with pytest.raises(ValueError):
        json_to_toml({"invalid": float("nan")})
