import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

from astrbot.cli.commands import cmd_init
from astrbot.core.utils.auth_password import verify_dashboard_password


@pytest.mark.parametrize("yes_option", ["-y", "--yes"])
@pytest.mark.parametrize("backend_only", [False, True])
def test_init_yes_skips_install_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    yes_option: str,
    backend_only: bool,
) -> None:
    """Initialize the selected root without prompting or downloading assets."""

    def fail_confirm(*_args: object, **_kwargs: object) -> None:
        pytest.fail("-y should skip the installation confirmation")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
    monkeypatch.delenv(cmd_init.DASHBOARD_INITIAL_PASSWORD_ENV, raising=False)
    monkeypatch.delenv("ASTRBOT_SYSTEMD", raising=False)
    monkeypatch.setattr(cmd_init.click, "confirm", fail_confirm)
    install_dashboard = AsyncMock()
    monkeypatch.setattr(
        cmd_init.DashboardManager, "ensure_installed", install_dashboard
    )

    arguments = [yes_option, "--backend-only"] if backend_only else [yes_option]
    result = CliRunner().invoke(cmd_init.init, arguments)

    assert result.exit_code == 0, result.output
    assert (tmp_path / ".astrbot").exists()
    assert (tmp_path / "data" / "config").is_dir()
    assert (tmp_path / "data" / "plugins").is_dir()
    assert (tmp_path / "data" / "temp").is_dir()
    assert (tmp_path / "data" / "cmd_config.json").is_file()
    if backend_only:
        install_dashboard.assert_not_awaited()
    else:
        install_dashboard.assert_awaited_once_with(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "initial_password",
    [None, "AstrBotInitialPassword123"],
    ids=["default", "environment"],
)
async def test_init_creates_config_with_optional_initial_password(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    initial_password: str | None,
) -> None:
    """Persist defaults or password hashes without exposing the initial secret."""
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
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
    serialized_config = config_path.read_text(encoding="utf-8-sig")
    config = json.loads(serialized_config)
    dashboard_config = config["dashboard"]
    output = capsys.readouterr()

    if initial_password is None:
        assert dashboard_config["password"] == ""
        assert dashboard_config["pbkdf2_password"] == ""
        assert dashboard_config["password_change_required"] is False
        assert dashboard_config["password_storage_upgraded"] is False
    else:
        assert verify_dashboard_password(
            dashboard_config["pbkdf2_password"], initial_password
        )
        assert verify_dashboard_password(dashboard_config["password"], initial_password)
        assert dashboard_config["password_change_required"] is True
        assert dashboard_config["password_storage_upgraded"] is True
        assert initial_password not in serialized_config
        assert initial_password not in output.out
        assert initial_password not in output.err
