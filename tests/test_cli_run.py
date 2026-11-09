import os
import sys

from click.testing import CliRunner

from astrbot.cli.commands import cmd_run


def test_run_reset_password_sets_startup_env(monkeypatch, tmp_path):
    (tmp_path / ".astrbot").touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(cmd_run.DASHBOARD_RESET_PASSWORD_ENV, raising=False)
    original_env = {
        "ASTRBOT_CLI": os.environ.get("ASTRBOT_CLI"),
        "ASTRBOT_ROOT": os.environ.get("ASTRBOT_ROOT"),
        cmd_run.DASHBOARD_RESET_PASSWORD_ENV: os.environ.get(
            cmd_run.DASHBOARD_RESET_PASSWORD_ENV
        ),
    }
    original_sys_path = list(sys.path)

    called = False

    async def fake_run_astrbot(astrbot_root):
        nonlocal called
        called = True
        assert astrbot_root == tmp_path
        assert os.environ[cmd_run.DASHBOARD_RESET_PASSWORD_ENV] == "1"

    monkeypatch.setattr(cmd_run, "run_astrbot", fake_run_astrbot)

    try:
        result = CliRunner().invoke(cmd_run.run, ["--reset-password"])
    finally:
        for key, value in original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        sys.path[:] = original_sys_path

    assert result.exit_code == 0, result.output
    assert called is True
