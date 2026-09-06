import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from astrbot.cli.commands import cmd_init
from astrbot.core.utils.auth_password import verify_dashboard_password


def test_init_yes_skips_install_confirmation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def fail_confirm(*_args: object, **_kwargs: object) -> None:
        pytest.fail("-y should skip the installation confirmation")

    monkeypatch.delenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, raising=False)
    monkeypatch.setattr(cmd_init.click, "confirm", fail_confirm)

    result = CliRunner().invoke(
        cmd_init.init, ["-y", "--backend-only", "--root", str(tmp_path)]
    )

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".astrbot").exists()
    for directory in ("config", "plugins", "temp", "skills"):
        assert (tmp_path / "data" / directory).is_dir()
    assert (tmp_path / "data" / "cmd_config.json").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("initial_password", [None, "AstrBotInitialPassword123"])
async def test_init_creates_config_with_optional_initial_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    initial_password: str | None,
) -> None:
    if initial_password is None:
        monkeypatch.delenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, raising=False)
    else:
        monkeypatch.setenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, initial_password)

    await cmd_init.initialize_astrbot(
        tmp_path,
        yes=True,
        backend_only=True,
        admin_username=None,
        admin_password=None,
    )

    config_path = tmp_path / "data" / "cmd_config.json"
    dashboard_config = json.loads(config_path.read_text(encoding="utf-8-sig"))[
        "dashboard"
    ]
    if initial_password is None:
        assert dashboard_config["password"] == ""
        assert dashboard_config["pbkdf2_password"] == ""
    else:
        for key in ("password", "pbkdf2_password"):
            assert verify_dashboard_password(dashboard_config[key], initial_password)
        assert dashboard_config["password_change_required"] is True
        assert dashboard_config["password_storage_upgraded"] is True
