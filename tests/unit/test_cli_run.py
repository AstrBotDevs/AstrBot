import os
import subprocess
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

    calls: list[str] = []

    def fake_bootstrap() -> None:
        calls.append("bootstrap")

    async def fake_run_application():
        nonlocal called
        called = True
        calls.append("application")
        assert os.environ[cmd_run.DASHBOARD_RESET_PASSWORD_ENV] == "1"

    monkeypatch.setattr(cmd_run, "_initialize_runtime_bootstrap", fake_bootstrap)
    monkeypatch.setattr(cmd_run, "_run_application", fake_run_application)

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
    assert calls == ["bootstrap", "application"]


def test_run_redacts_sensitive_runtime_traceback(monkeypatch, tmp_path):
    """CLI startup diagnostics must not echo a provider credential."""
    (tmp_path / ".astrbot").touch()
    monkeypatch.chdir(tmp_path)

    def fake_bootstrap() -> None:
        return None

    async def failing_run_application() -> None:
        raise RuntimeError("api_key=super-secret-token")

    monkeypatch.setattr(cmd_run, "_initialize_runtime_bootstrap", fake_bootstrap)
    monkeypatch.setattr(cmd_run, "_run_application", failing_run_application)

    result = CliRunner().invoke(cmd_run.run)

    assert result.exit_code != 0
    assert "super-secret-token" not in result.output
    assert "Runtime failed. See AstrBot logs for details." in result.output


def test_cli_entry_bootstraps_without_importing_core() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import astrbot.cli.__main__; "
            "assert 'astrbot.core' not in sys.modules",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
