import json

import pytest

from astrbot.cli.commands import cmd_init
from astrbot.core.utils.auth_password import verify_dashboard_password


@pytest.mark.asyncio
async def test_init_without_initial_password_env_creates_default_config(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, raising=False)
    (tmp_path / ".astrbot").touch()

    await cmd_init.initialize_astrbot(
        tmp_path,
        yes=True,
        backend_only=True,
        admin_username=None,
        admin_password=None,
    )

    assert (tmp_path / "data" / "cmd_config.json").exists()
    assert (tmp_path / "data" / "skills").is_dir()


@pytest.mark.asyncio
async def test_init_uses_initial_password_env_to_create_config(
    monkeypatch,
    tmp_path,
):
    initial_password = "AstrBotInitialPassword123"
    monkeypatch.setenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, initial_password)
    (tmp_path / ".astrbot").touch()

    await cmd_init.initialize_astrbot(
        tmp_path,
        yes=True,
        backend_only=True,
        admin_username=None,
        admin_password=None,
    )

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


@pytest.mark.asyncio
async def test_init_sets_dashboard_username(
    monkeypatch,
    tmp_path,
):
    monkeypatch.delenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, raising=False)
    (tmp_path / ".astrbot").touch()

    await cmd_init.initialize_astrbot(
        tmp_path,
        yes=True,
        backend_only=True,
        admin_username="alice",
        admin_password=None,
    )

    config_path = tmp_path / "data" / "cmd_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8-sig"))

    assert config["dashboard"]["username"] == "alice"
