import os

from click.testing import CliRunner

from astrbot.cli.commands import cmd_run


def test_run_reset_password_sets_startup_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv(cmd_run.DASHBOARD_RESET_PASSWORD_ENV, raising=False)
    (tmp_path / ".astrbot").touch()
    observed_reset_flags = []

    async def fake_run_astrbot(_astrbot_root):
        observed_reset_flags.append(os.environ.get(cmd_run.DASHBOARD_RESET_PASSWORD_ENV))

    monkeypatch.setattr(cmd_run, "run_astrbot", fake_run_astrbot)

    result = CliRunner().invoke(cmd_run.run, ["--reset-password"])

    assert result.exit_code == 0
    assert observed_reset_flags == ["1"]
