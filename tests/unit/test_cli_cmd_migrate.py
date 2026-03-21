from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from astrbot.cli.commands import cmd_migrate
from astrbot.cli.utils.openclaw_migrate import MigrationReport


def test_migrate_openclaw_reports_config_toml_field_and_relative_target(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source_root = tmp_path / ".openclaw"
    source_root.mkdir(parents=True)
    astrbot_root = tmp_path / "astrbot"
    astrbot_root.mkdir(parents=True)

    captured: dict[str, object] = {}

    def _fake_run_openclaw_migration(**kwargs: object) -> MigrationReport:
        captured.update(kwargs)
        return MigrationReport(
            source_root=str(source_root),
            source_workspace=str(source_root / "workspace"),
            target_dir=str(astrbot_root / "data" / "migrations" / "openclaw" / "run-test"),
            dry_run=False,
            memory_entries_total=3,
            memory_entries_from_sqlite=2,
            memory_entries_from_markdown=1,
            workspace_files_total=5,
            workspace_bytes_total=1024,
            config_found=True,
            copied_workspace_files=5,
            copied_memory_entries=3,
            wrote_timeline=False,
            wrote_config_toml=True,
        )

    monkeypatch.setattr(cmd_migrate, "get_astrbot_root", lambda: astrbot_root)
    monkeypatch.setattr(cmd_migrate, "run_openclaw_migration", _fake_run_openclaw_migration)

    runner = CliRunner()
    result = runner.invoke(
        cmd_migrate.migrate,
        ["openclaw", "--source", str(source_root), "--target", "data/migrations/custom"],
    )

    assert result.exit_code == 0, result.output
    assert captured["target_dir"] == Path("data/migrations/custom")
    assert "Timeline written:   False" in result.output
    assert "Config TOML written: True" in result.output

