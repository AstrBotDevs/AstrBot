import os

from click.testing import CliRunner

from astrbot.cli.commands import cmd_run


def test_run_reset_password_sets_startup_env(monkeypatch, tmp_path):
    (tmp_path / ".astrbot").touch()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(cmd_run.DASHBOARD_RESET_PASSWORD_ENV, raising=False)

    called = False

    async def fake_run_astrbot(astrbot_root):
        nonlocal called
        called = True
        assert astrbot_root == tmp_path
        assert os.environ[cmd_run.DASHBOARD_RESET_PASSWORD_ENV] == "1"

    monkeypatch.setattr(cmd_run, "run_astrbot", fake_run_astrbot)

    result = CliRunner().invoke(cmd_run.run, ["--reset-password"])

    assert result.exit_code == 0, result.output
    assert called is True
