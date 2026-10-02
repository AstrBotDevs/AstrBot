import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from astrbot.cli.commands import cmd_init
from astrbot.core.utils.auth_password import verify_dashboard_password


def test_init_yes_skips_install_confirmation(monkeypatch, tmp_path):
    def fail_confirm(*_args, **_kwargs):
        pytest.fail("-y should skip the installation confirmation")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASTRBOT_DASHBOARD_INITIAL_PASSWORD", raising=False)
    monkeypatch.setattr(cmd_init.click, "confirm", fail_confirm)

    result = CliRunner().invoke(cmd_init.init, ["-y"])

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".astrbot").exists()
    assert (tmp_path / "data" / "config").is_dir()
    assert (tmp_path / "data" / "plugins").is_dir()
    assert (tmp_path / "data" / "temp").is_dir()
    assert (tmp_path / "data" / "cmd_config.json").exists()


@pytest.mark.asyncio
async def test_init_preserves_existing_dashboard_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(
        "ASTRBOT_DASHBOARD_INITIAL_PASSWORD", "IgnoredInitialPassword123"
    )
    config_path = tmp_path / "data" / "cmd_config.json"
    config_path.parent.mkdir(parents=True)
    config = {"dashboard": {"username": "existing", "password": "existing-hash"}}
    config_path.write_text(json.dumps(config), encoding="utf-8-sig")

    await cmd_init.initialize_astrbot(
        tmp_path,
        yes=True,
        backend_only=True,
        admin_username=None,
        admin_password=None,
    )

    dashboard = json.loads(config_path.read_text(encoding="utf-8-sig"))["dashboard"]
    assert dashboard["username"] == "existing"
    assert dashboard["password"] == "existing-hash"


def test_init_rejects_admin_password(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cmd_init.init,
        [
            "-y",
            "--backend-only",
            "--root",
            str(tmp_path),
            "--admin-password",
            "test-password",
        ],
    )

    assert result.exit_code != 0
    assert "--admin-password is no longer supported during init" in result.output


@pytest.mark.asyncio
async def test_init_uses_initial_password_for_new_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    initial_password = "AstrBotInitialPassword123"
    monkeypatch.setenv("ASTRBOT_DASHBOARD_INITIAL_PASSWORD", initial_password)

    await cmd_init.initialize_astrbot(
        tmp_path,
        yes=True,
        backend_only=True,
        admin_username=None,
        admin_password=None,
    )

    config_path = tmp_path / "data" / "cmd_config.json"
    dashboard = json.loads(config_path.read_text(encoding="utf-8-sig"))["dashboard"]
    for key in ("password", "pbkdf2_password"):
        assert verify_dashboard_password(dashboard[key], initial_password)
    assert dashboard["password_change_required"] is True
    assert dashboard["password_storage_upgraded"] is True
