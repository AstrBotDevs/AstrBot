import json

import pytest

from astrbot.cli.commands import cmd_init
from astrbot.core.utils.auth_password import verify_dashboard_password


@pytest.mark.asyncio
async def test_init_without_initial_password_env_does_not_create_config(
    monkeypatch,
    tmp_path,
):
    async def fake_check_dashboard(_data_path):
        return None

    monkeypatch.delenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, raising=False)
    monkeypatch.setattr(cmd_init, "check_dashboard", fake_check_dashboard)
    (tmp_path / ".astrbot").touch()

    await cmd_init.initialize_astrbot(tmp_path)

    assert not (tmp_path / "data" / "cmd_config.json").exists()


@pytest.mark.asyncio
async def test_init_uses_initial_password_env_to_create_config(
    monkeypatch,
    tmp_path,
):
    async def fake_check_dashboard(_data_path):
        return None

    initial_password = "AstrBotInitialPassword123"
    monkeypatch.setenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, initial_password)
    monkeypatch.setattr(cmd_init, "check_dashboard", fake_check_dashboard)
    (tmp_path / ".astrbot").touch()

    await cmd_init.initialize_astrbot(tmp_path)

    config_path = tmp_path / "data" / "cmd_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    dashboard_config = config["dashboard"]

    assert verify_dashboard_password(
        dashboard_config["pbkdf2_password"],
        initial_password,
    )
    assert verify_dashboard_password(
        dashboard_config["password"],
        initial_password,
    )
    assert dashboard_config["password_change_required"] is True
    assert dashboard_config["password_storage_upgraded"] is True
