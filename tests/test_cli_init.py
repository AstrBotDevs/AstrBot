import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from astrbot.cli.commands import cmd_init
from astrbot.core.utils.auth_password import verify_dashboard_password


@pytest.mark.asyncio
async def test_init_without_initial_password_env_does_not_create_config(
    monkeypatch,
    tmp_path,
):
    async def fake_check_dashboard(_data_path):
        return None

    monkeypatch.delenv("ASTRBOT_ROOT", raising=False)
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
    monkeypatch.setenv("ASTRBOT_ROOT", str(tmp_path))
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


def test_cli_main_import_does_not_create_cwd_data(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    env = os.environ.copy()
    env.pop("ASTRBOT_ROOT", None)
    env["HOME"] = str(tmp_path / "home")
    env["PYTHONPATH"] = (
        str(repo_root)
        if not env.get("PYTHONPATH")
        else f"{repo_root}{os.pathsep}{env['PYTHONPATH']}"
    )

    result = subprocess.run(
        [sys.executable, "-c", "import astrbot.cli.__main__"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "data").exists()


def test_init_defaults_to_user_runtime(monkeypatch, tmp_path):
    async def fake_check_dashboard(_data_path):
        return None

    home = tmp_path / "home"
    workdir = tmp_path / "workdir"
    home.mkdir()
    workdir.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ASTRBOT_ROOT", raising=False)
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(cmd_init, "check_dashboard", fake_check_dashboard)

    result = CliRunner().invoke(cmd_init.init, input="\n", env={"ASTRBOT_ROOT": ""})

    assert result.exit_code == 0, result.output
    assert (home / ".astrbot" / ".astrbot").exists()
    assert (home / ".astrbot" / "data" / "config").is_dir()
    assert not (workdir / "data").exists()


def test_init_can_install_to_current_directory(monkeypatch, tmp_path):
    async def fake_check_dashboard(_data_path):
        return None

    home = tmp_path / "home"
    workdir = tmp_path / "workdir"
    home.mkdir()
    workdir.mkdir()

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("ASTRBOT_ROOT", raising=False)
    monkeypatch.chdir(workdir)
    monkeypatch.setattr(cmd_init, "check_dashboard", fake_check_dashboard)

    result = CliRunner().invoke(cmd_init.init, input="2\n", env={"ASTRBOT_ROOT": ""})

    assert result.exit_code == 0, result.output
    assert (workdir / ".astrbot").exists()
    assert (workdir / "data" / "config").is_dir()
    assert not (home / ".astrbot").exists()
