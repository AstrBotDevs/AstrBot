import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from click.testing import CliRunner

from astrbot.cli.__main__ import cli
from astrbot.cli.commands import cmd_service
from astrbot.cli.commands.cmd_service import (
    ServiceState,
    WebUIStatus,
    _build_launchd_plist,
    _build_systemd_unit,
    _check_webui,
    _get_app_log_config,
    _health_label,
    _load_dashboard_port,
    _load_or_init_config,
    service,
)


class _HealthyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_args):
        return


def test_service_command_is_registered():
    result = CliRunner().invoke(cli, ["help", "service"])

    assert result.exit_code == 0
    assert "install" in result.output
    assert "logs" in result.output
    assert "restart" in result.output
    assert "status" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "uninstall" in result.output


def test_service_logs_group_exposes_log_file_controls():
    result = CliRunner().invoke(service, ["logs", "--help"])

    assert result.exit_code == 0
    assert "enable" in result.output
    assert "disable" in result.output
    assert "status" in result.output


def test_service_install_requires_initialized_root(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(service, ["install", "--executable", "astrbot"])

    assert result.exit_code == 1
    assert "Use 'astrbot init' before installing the service" in result.output


def test_systemd_unit_uses_astrbot_executable_and_working_directory():
    unit = _build_systemd_unit(
        "astrbot",
        Path("/home/astrbot/.local/bin/astrbot"),
        Path("/home/astrbot/AstrBot Root"),
    )

    assert 'WorkingDirectory="/home/astrbot/AstrBot Root"' in unit
    assert "ExecStart=/home/astrbot/.local/bin/astrbot run" in unit
    assert "Environment=PYTHONUNBUFFERED=1" in unit


def test_launchd_plist_uses_astrbot_executable_and_working_directory():
    plist = _build_launchd_plist(
        "astrbot",
        Path("/Users/astrbot/.local/bin/astrbot"),
        Path("/Users/astrbot/AstrBot"),
        Path("/Users/astrbot/Library/Logs/AstrBot"),
    )

    assert plist["Label"] == "app.astrbot.astrbot"
    assert plist["ProgramArguments"] == ["/Users/astrbot/.local/bin/astrbot", "run"]
    assert plist["WorkingDirectory"] == "/Users/astrbot/AstrBot"
    assert plist["EnvironmentVariables"] == {"PYTHONUNBUFFERED": "1"}


def test_launch_agent_start_waits_until_loaded_before_kickstart(monkeypatch, tmp_path):
    plist_path = tmp_path / "app.astrbot.astrbot.plist"
    plist_path.touch()
    events = []
    loaded_states = [False, False, True]

    monkeypatch.setattr(cmd_service.shutil, "which", lambda name: "/bin/launchctl")
    monkeypatch.setattr(cmd_service, "_launch_agent_path", lambda _name: plist_path)
    monkeypatch.setattr(cmd_service.time, "sleep", lambda _seconds: None)

    def fake_run_capture(command):
        if command[1] == "print":
            events.append("print")
            loaded = loaded_states.pop(0) if loaded_states else True
            return cmd_service.subprocess.CompletedProcess(
                command,
                0 if loaded else 113,
                stdout="",
                stderr="not loaded",
            )
        if command[1] == "kickstart":
            events.append("kickstart")
            return cmd_service.subprocess.CompletedProcess(command, 0)
        raise AssertionError(f"Unexpected capture command: {command}")

    def fake_run_checked(command, _failure_message):
        events.append(command[1])

    monkeypatch.setattr(cmd_service, "_run_capture", fake_run_capture)
    monkeypatch.setattr(cmd_service, "_run_checked", fake_run_checked)

    cmd_service._start_launch_agent("astrbot")

    assert "bootstrap" in events
    assert "enable" in events
    assert "kickstart" in events
    assert events.index("bootstrap") < events.index("kickstart")


def test_service_command_rejects_windows(monkeypatch):
    monkeypatch.setattr(cmd_service.platform, "system", lambda: "Windows")

    result = CliRunner().invoke(service, ["start"])

    assert result.exit_code == 1
    assert "not supported on Windows yet" in result.output


def test_load_dashboard_port_reads_cmd_config(tmp_path):
    config_path = tmp_path / "data" / "cmd_config.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps({"dashboard": {"port": 7788}}),
        encoding="utf-8-sig",
    )

    dashboard_port = _load_dashboard_port(tmp_path)

    assert dashboard_port.port == 7788
    assert dashboard_port.detail is None


def test_check_webui_reports_accessible_http_response():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthyHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        webui_status = _check_webui(server.server_port, timeout=1.0)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=1)

    assert webui_status.accessible is True
    assert webui_status.status_code == 200


def test_health_label_requires_service_and_webui():
    active = ServiceState(manager="systemd --user", installed=True, state="active")
    inactive = ServiceState(manager="systemd --user", installed=True, state="inactive")
    reachable = WebUIStatus(url="http://127.0.0.1:6185/", accessible=True)
    unreachable = WebUIStatus(url="http://127.0.0.1:6185/", accessible=False)

    assert _health_label(active, reachable) == "healthy"
    assert _health_label(active, unreachable) == "degraded"
    assert _health_label(inactive, reachable) == "degraded"
    assert _health_label(inactive, unreachable) == "unhealthy"


def test_service_status_reports_port_and_webui_health(monkeypatch, tmp_path):
    (tmp_path / ".astrbot").touch()
    config_path = tmp_path / "data" / "cmd_config.json"
    config_path.parent.mkdir()
    config_path.write_text(
        json.dumps({"dashboard": {"port": 7788}}),
        encoding="utf-8-sig",
    )

    monkeypatch.setattr(
        cmd_service,
        "_get_service_state",
        lambda _name: ServiceState(
            manager="systemd --user",
            installed=True,
            state="active",
        ),
    )
    monkeypatch.setattr(
        cmd_service,
        "_check_webui",
        lambda port, _timeout: WebUIStatus(
            url=f"http://127.0.0.1:{port}/",
            accessible=True,
            status_code=200,
            detail="HTTP 200",
        ),
    )

    result = CliRunner().invoke(service, ["status", "--workdir", str(tmp_path)])

    assert result.exit_code == 0
    assert "Health: healthy" in result.output
    assert "Dashboard port: 7788" in result.output
    assert "WebUI accessible: yes" in result.output
    assert "WebUI HTTP status: 200" in result.output


def test_service_start_dispatches_to_platform_control(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cmd_service,
        "_control_service",
        lambda name, action: calls.append((name, action)),
    )

    result = CliRunner().invoke(service, ["start", "--name", "astrbot-test"])

    assert result.exit_code == 0
    assert calls == [("astrbot-test", "start")]
    assert "Started service: astrbot-test" in result.output


def test_service_uninstall_requires_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cmd_service,
        "_uninstall_service",
        lambda name: calls.append(name) or name,
    )

    result = CliRunner().invoke(service, ["uninstall"], input="n\n")

    assert result.exit_code == 1
    assert calls == []


def test_service_logs_source_app_reads_application_log(monkeypatch, tmp_path):
    (tmp_path / ".astrbot").touch()
    log_path = tmp_path / "data" / "logs" / "astrbot.log"
    log_path.parent.mkdir(parents=True)
    log_path.write_text("first\nsecond\nthird\n", encoding="utf-8")

    result = CliRunner().invoke(
        service,
        ["logs", "--source", "app", "--workdir", str(tmp_path), "--lines", "2"],
    )

    assert result.exit_code == 0
    assert "first" not in result.output
    assert "second" in result.output
    assert "third" in result.output


def test_service_logs_hides_stderr_by_default(monkeypatch, tmp_path):
    out_log = tmp_path / "astrbot.out.log"
    err_log = tmp_path / "astrbot.err.log"
    out_log.write_text("normal output\n", encoding="utf-8")
    err_log.write_text("stderr output\n", encoding="utf-8")

    monkeypatch.setattr(cmd_service.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(
        cmd_service,
        "_service_log_paths",
        lambda _name: (out_log, err_log),
    )

    default_result = CliRunner().invoke(service, ["logs", "--lines", "10"])
    stderr_result = CliRunner().invoke(
        service,
        ["logs", "--lines", "10", "--include-stderr"],
    )

    assert default_result.exit_code == 0
    assert "normal output" in default_result.output
    assert "stderr output" not in default_result.output
    assert stderr_result.exit_code == 0
    assert "normal output" in stderr_result.output
    assert "stderr output" in stderr_result.output


def test_service_app_log_enable_updates_config(tmp_path):
    (tmp_path / ".astrbot").touch()

    result = CliRunner().invoke(
        service,
        [
            "logs",
            "enable",
            "--workdir",
            str(tmp_path),
            "--path",
            "logs/custom.log",
        ],
    )

    assert result.exit_code == 0
    config = _load_or_init_config(tmp_path)
    log_config = _get_app_log_config(tmp_path, config)
    assert log_config.enabled is True
    assert log_config.configured_path == "logs/custom.log"
    assert log_config.path == tmp_path / "data" / "logs" / "custom.log"
