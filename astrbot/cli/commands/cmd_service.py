import copy
import getpass
import json
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import click

from astrbot.core.utils.astrbot_path import astrbot_paths

DEFAULT_SERVICE_NAME = "astrbot"
DEFAULT_DASHBOARD_PORT = 6185
DEFAULT_STATUS_TIMEOUT_SECONDS = 2.0
DEFAULT_LOG_LINES = 200
MACOS_LABEL_PREFIX = "app.astrbot"


@dataclass(frozen=True)
class ServiceState:
    manager: str
    installed: bool
    state: str
    path: Path | None = None
    enabled: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class DashboardPort:
    port: int
    detail: str | None = None


@dataclass(frozen=True)
class WebUIStatus:
    url: str
    accessible: bool
    status_code: int | None = None
    detail: str | None = None


@dataclass(frozen=True)
class AppLogConfig:
    enabled: bool
    path: Path
    configured_path: str | None = None


@click.group(name="service")
def service() -> None:
    """Install and manage AstrBot as a background service."""


def _validate_service_name(name: str) -> str:
    allowed_chars = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-"
    )
    if not name or any(char not in allowed_chars for char in name):
        raise click.ClickException(
            "Service name can only contain letters, numbers, dots, underscores, and hyphens"
        )
    return name


def _get_astrbot_root() -> Path:
    return astrbot_paths.root


def _is_astrbot_root(path: Path) -> bool:
    return path.exists() and path.is_dir() and (path / ".astrbot").exists()


def _resolve_workdir(workdir: Path | None) -> Path:
    astrbot_root = (workdir or _get_astrbot_root()).expanduser().resolve()
    if not _is_astrbot_root(astrbot_root):
        raise click.ClickException(
            f"{astrbot_root} is not a valid AstrBot root directory. "
            "Use 'astrbot init' before installing the service"
        )
    return astrbot_root


def _resolve_astrbot_executable(executable: str | None) -> Path:
    if executable:
        discovered = shutil.which(executable)
        if discovered:
            return Path(discovered).expanduser().absolute()

        explicit_path = Path(executable).expanduser()
        if explicit_path.exists():
            return explicit_path.absolute()

        raise click.ClickException(f"AstrBot executable not found: {executable}")

    discovered = shutil.which("astrbot")
    if discovered:
        return Path(discovered).expanduser().absolute()

    current_argv = Path(sys.argv[0]).expanduser()
    if current_argv.name.startswith("astrbot") and current_argv.exists():
        return current_argv.absolute()

    raise click.ClickException(
        "Cannot find the astrbot executable. Install AstrBot with "
        "'uv tool install astrbot --python 3.12', or pass --executable"
    )


def _run_checked(command: list[str], failure_message: str) -> None:
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError as e:
        raise click.ClickException(f"Command not found: {command[0]}") from e
    except subprocess.CalledProcessError as e:
        raise click.ClickException(f"{failure_message}: {e}") from e


def _run_capture(command: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None


def _quote_systemd_value(value: Path | str) -> str:
    raw = str(value)
    escaped = raw.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")
    if any(char.isspace() for char in raw) or any(
        char in raw for char in ['"', "\\", "%", ";"]
    ):
        return f'"{escaped}"'
    return escaped


def _build_systemd_unit(
    service_name: str,
    executable: Path,
    workdir: Path,
) -> str:
    return dedent(
        f"""\
        [Unit]
        Description=AstrBot Service
        Documentation=https://docs.astrbot.app
        After=network-online.target
        Wants=network-online.target

        [Service]
        Type=simple
        WorkingDirectory={_quote_systemd_value(workdir)}
        ExecStart={_quote_systemd_value(executable)} run
        Restart=on-failure
        RestartSec=5
        StandardOutput=journal
        StandardError=journal
        SyslogIdentifier={service_name}
        Environment=PYTHONUNBUFFERED=1

        [Install]
        WantedBy=default.target
        """
    )


def _systemd_unit_path(service_name: str) -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{service_name}.service"


def _systemd_unit_name(service_name: str) -> str:
    return f"{service_name}.service"


def _install_systemd_user_service(
    service_name: str,
    executable: Path,
    workdir: Path,
    *,
    force: bool,
    now: bool,
) -> Path:
    if platform.system() != "Linux":
        raise click.ClickException(
            "systemd service installation is only available on Linux"
        )
    if shutil.which("systemctl") is None:
        raise click.ClickException("systemctl was not found")

    unit_path = _systemd_unit_path(service_name)
    if unit_path.exists() and not force:
        raise click.ClickException(
            f"{unit_path} already exists. Use --force to overwrite"
        )

    unit_path.parent.mkdir(parents=True, exist_ok=True)
    unit_path.write_text(
        _build_systemd_unit(service_name, executable, workdir),
        encoding="utf-8",
    )

    _run_checked(
        ["systemctl", "--user", "daemon-reload"],
        "Failed to reload the systemd user daemon",
    )
    _run_checked(
        ["systemctl", "--user", "enable", unit_path.name],
        "Failed to enable the systemd user service",
    )
    if now:
        _run_checked(
            ["systemctl", "--user", "restart", unit_path.name],
            "Failed to start the systemd user service",
        )

    return unit_path


def _macos_label(service_name: str) -> str:
    return f"{MACOS_LABEL_PREFIX}.{service_name}"


def _launch_agent_path(service_name: str) -> Path:
    return (
        Path.home() / "Library" / "LaunchAgents" / f"{_macos_label(service_name)}.plist"
    )


def _macos_log_dir() -> Path:
    return Path.home() / "Library" / "Logs" / "AstrBot"


def _service_log_paths(service_name: str) -> tuple[Path, Path]:
    system = platform.system()
    if system == "Darwin":
        log_dir = _macos_log_dir()
    else:
        log_dir = _get_astrbot_root() / "data" / "logs"
    return log_dir / f"{service_name}.out.log", log_dir / f"{service_name}.err.log"


def _build_launchd_plist(
    service_name: str,
    executable: Path,
    workdir: Path,
    log_dir: Path,
) -> dict:
    label = _macos_label(service_name)
    return {
        "Label": label,
        "ProgramArguments": [str(executable), "run"],
        "WorkingDirectory": str(workdir),
        "RunAtLoad": True,
        "KeepAlive": {"SuccessfulExit": False},
        "StandardOutPath": str(log_dir / f"{service_name}.out.log"),
        "StandardErrorPath": str(log_dir / f"{service_name}.err.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
    }


def _install_launch_agent(
    service_name: str,
    executable: Path,
    workdir: Path,
    *,
    force: bool,
    now: bool,
) -> Path:
    if platform.system() != "Darwin":
        raise click.ClickException(
            "launchd service installation is only available on macOS"
        )
    if shutil.which("launchctl") is None:
        raise click.ClickException("launchctl was not found")

    plist_path = _launch_agent_path(service_name)
    if plist_path.exists() and not force:
        raise click.ClickException(
            f"{plist_path} already exists. Use --force to overwrite"
        )

    log_dir = _macos_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as f:
        plistlib.dump(
            _build_launchd_plist(service_name, executable, workdir, log_dir),
            f,
            sort_keys=False,
        )

    if now:
        if force:
            _stop_launch_agent(service_name, allow_missing=True)
        _start_launch_agent(service_name)

    return plist_path


def _first_output_line(result: subprocess.CompletedProcess[str]) -> str | None:
    text = (result.stdout or result.stderr).strip()
    if not text:
        return None
    return text.splitlines()[0].strip()


def _get_systemd_state(service_name: str) -> ServiceState:
    unit_path = _systemd_unit_path(service_name)
    installed = unit_path.exists()
    if shutil.which("systemctl") is None:
        return ServiceState(
            manager="systemd --user",
            installed=installed,
            state="unknown",
            path=unit_path,
            detail="systemctl was not found",
        )

    unit_name = _systemd_unit_name(service_name)
    active_result = _run_capture(["systemctl", "--user", "is-active", unit_name])
    enabled_result = _run_capture(["systemctl", "--user", "is-enabled", unit_name])
    if active_result is None:
        return ServiceState(
            manager="systemd --user",
            installed=installed,
            state="unknown",
            path=unit_path,
            detail="systemctl was not found",
        )

    state = (active_result.stdout or "").strip() or "unknown"
    detail = (
        None if active_result.returncode == 0 else _first_output_line(active_result)
    )
    enabled = None
    if enabled_result is not None:
        enabled = (enabled_result.stdout or "").strip() or None

    if not installed and state in {"inactive", "unknown"}:
        state = "not-installed"

    return ServiceState(
        manager="systemd --user",
        installed=installed,
        state=state,
        path=unit_path,
        enabled=enabled,
        detail=detail,
    )


def _get_launchd_state(service_name: str) -> ServiceState:
    plist_path = _launch_agent_path(service_name)
    installed = plist_path.exists()
    if shutil.which("launchctl") is None:
        return ServiceState(
            manager="launchd",
            installed=installed,
            state="unknown",
            path=plist_path,
            detail="launchctl was not found",
        )

    label = _macos_label(service_name)
    target = f"gui/{os.getuid()}/{label}"
    result = _run_capture(["launchctl", "print", target])
    if result is None:
        return ServiceState(
            manager="launchd",
            installed=installed,
            state="unknown",
            path=plist_path,
            detail="launchctl was not found",
        )

    if result.returncode != 0:
        return ServiceState(
            manager="launchd",
            installed=installed,
            state="not-loaded" if installed else "not-installed",
            path=plist_path,
            detail=_first_output_line(result),
        )

    output = result.stdout or ""
    state = "loaded"
    detail = None
    for line in output.splitlines():
        normalized = line.strip()
        if normalized.startswith("state = "):
            state = normalized.removeprefix("state = ").strip()
        elif normalized.startswith("pid = "):
            detail = normalized

    return ServiceState(
        manager="launchd",
        installed=installed,
        state=state,
        path=plist_path,
        detail=detail,
    )


def _get_service_state(service_name: str) -> ServiceState:
    system = platform.system()
    if system == "Linux":
        return _get_systemd_state(service_name)
    if system == "Darwin":
        return _get_launchd_state(service_name)
    return ServiceState(
        manager="unknown",
        installed=False,
        state="unsupported",
        detail=f"Unsupported platform: {system}",
    )


def _load_dashboard_port(astrbot_root: Path) -> DashboardPort:
    config_path = astrbot_root / "data" / "cmd_config.json"
    if not config_path.exists():
        return DashboardPort(
            DEFAULT_DASHBOARD_PORT,
            f"{config_path} does not exist; using default port",
        )

    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        port = int(config.get("dashboard", {}).get("port", DEFAULT_DASHBOARD_PORT))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as e:
        return DashboardPort(
            DEFAULT_DASHBOARD_PORT,
            f"Failed to read dashboard port from {config_path}: {e}; using default port",
        )

    if port < 1 or port > 65535:
        return DashboardPort(
            DEFAULT_DASHBOARD_PORT,
            f"Invalid dashboard port {port}; using default port",
        )
    return DashboardPort(port)


def _check_webui(port: int, timeout: float) -> WebUIStatus:
    url = f"http://127.0.0.1:{port}/"
    request = Request(url, headers={"User-Agent": "AstrBot CLI health check"})
    try:
        with urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
    except HTTPError as e:
        return WebUIStatus(
            url=url,
            accessible=False,
            status_code=e.code,
            detail=f"HTTP {e.code}",
        )
    except URLError as e:
        return WebUIStatus(url=url, accessible=False, detail=str(e.reason))
    except TimeoutError:
        return WebUIStatus(url=url, accessible=False, detail="request timed out")
    except OSError as e:
        return WebUIStatus(url=url, accessible=False, detail=str(e))

    return WebUIStatus(
        url=url,
        accessible=200 <= status_code < 400,
        status_code=status_code,
        detail=f"HTTP {status_code}",
    )


def _is_service_running(service_state: ServiceState) -> bool:
    return service_state.state.lower() in {"active", "running"}


def _health_label(service_state: ServiceState, webui_status: WebUIStatus) -> str:
    service_running = _is_service_running(service_state)
    if service_running and webui_status.accessible:
        return "healthy"
    if service_running or webui_status.accessible:
        return "degraded"
    return "unhealthy"


def _format_yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _control_systemd_service(service_name: str, action: str) -> None:
    if shutil.which("systemctl") is None:
        raise click.ClickException("systemctl was not found")

    unit_path = _systemd_unit_path(service_name)
    if not unit_path.exists():
        raise click.ClickException(
            f"{unit_path} does not exist. Run 'service install' first"
        )

    _run_checked(
        ["systemctl", "--user", action, _systemd_unit_name(service_name)],
        f"Failed to {action} the systemd user service",
    )


def _launchd_target(service_name: str) -> str:
    return f"gui/{os.getuid()}/{_macos_label(service_name)}"


def _launchd_domain() -> str:
    return f"gui/{os.getuid()}"


def _is_launch_agent_loaded(service_name: str) -> bool:
    result = _run_capture(["launchctl", "print", _launchd_target(service_name)])
    return result is not None and result.returncode == 0


def _wait_for_launch_agent_state(
    service_name: str,
    *,
    loaded: bool,
    timeout: float = 5.0,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _is_launch_agent_loaded(service_name) is loaded:
            return True
        time.sleep(0.1)
    return _is_launch_agent_loaded(service_name) is loaded


def _bootstrap_launch_agent(service_name: str, plist_path: Path) -> None:
    _run_checked(
        ["launchctl", "bootstrap", _launchd_domain(), str(plist_path)],
        f"Failed to load the LaunchAgent from {plist_path}",
    )
    if not _wait_for_launch_agent_state(service_name, loaded=True):
        raise click.ClickException(
            "LaunchAgent was bootstrapped but did not appear in launchd. "
            f"Label: {_macos_label(service_name)}; plist: {plist_path}"
        )


def _enable_launch_agent(service_name: str) -> None:
    _run_checked(
        ["launchctl", "enable", _launchd_target(service_name)],
        f"Failed to enable the LaunchAgent {_macos_label(service_name)}",
    )


def _kickstart_launch_agent(service_name: str) -> None:
    target = _launchd_target(service_name)
    result = _run_capture(["launchctl", "kickstart", "-k", target])
    if result is None:
        raise click.ClickException("launchctl was not found")
    if result.returncode == 0:
        return

    detail = _first_output_line(result)
    message = f"Failed to start the LaunchAgent {target}"
    if detail:
        message = f"{message}: {detail}"
    raise click.ClickException(message)


def _start_launch_agent(service_name: str) -> None:
    if shutil.which("launchctl") is None:
        raise click.ClickException("launchctl was not found")

    plist_path = _launch_agent_path(service_name)
    if not plist_path.exists():
        raise click.ClickException(
            f"{plist_path} does not exist. Run 'service install' first"
        )

    if not _is_launch_agent_loaded(service_name):
        _bootstrap_launch_agent(service_name, plist_path)

    _enable_launch_agent(service_name)
    _kickstart_launch_agent(service_name)


def _stop_launch_agent(service_name: str, *, allow_missing: bool = False) -> None:
    if shutil.which("launchctl") is None:
        raise click.ClickException("launchctl was not found")

    result = _run_capture(["launchctl", "bootout", _launchd_target(service_name)])
    if result is None:
        raise click.ClickException("launchctl was not found")
    if result.returncode != 0 and not allow_missing:
        detail = _first_output_line(result)
        message = "Failed to stop the LaunchAgent"
        if detail:
            message = f"{message}: {detail}"
        raise click.ClickException(message)
    if result.returncode == 0:
        _wait_for_launch_agent_state(service_name, loaded=False)


def _control_service(service_name: str, action: str) -> None:
    system = platform.system()
    if system == "Linux":
        _control_systemd_service(service_name, action)
        return

    if system == "Darwin":
        match action:
            case "start":
                _start_launch_agent(service_name)
            case "stop":
                _stop_launch_agent(service_name)
            case "restart":
                _stop_launch_agent(service_name, allow_missing=True)
                _start_launch_agent(service_name)
            case _:
                raise click.ClickException(f"Unsupported launchd action: {action}")
        return

    raise click.ClickException(f"Unsupported platform: {system}")


def _uninstall_systemd_service(service_name: str) -> Path:
    unit_path = _systemd_unit_path(service_name)
    if not unit_path.exists():
        raise click.ClickException(f"{unit_path} does not exist")

    if shutil.which("systemctl") is not None:
        subprocess.run(
            [
                "systemctl",
                "--user",
                "disable",
                "--now",
                _systemd_unit_name(service_name),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    unit_path.unlink()
    if shutil.which("systemctl") is not None:
        _run_checked(
            ["systemctl", "--user", "daemon-reload"],
            "Failed to reload the systemd user daemon",
        )
    return unit_path


def _uninstall_launch_agent(service_name: str) -> Path:
    plist_path = _launch_agent_path(service_name)
    if not plist_path.exists():
        raise click.ClickException(f"{plist_path} does not exist")

    _stop_launch_agent(service_name, allow_missing=True)
    plist_path.unlink()
    return plist_path


def _uninstall_service(service_name: str) -> Path:
    system = platform.system()
    if system == "Linux":
        return _uninstall_systemd_service(service_name)
    if system == "Darwin":
        return _uninstall_launch_agent(service_name)
    raise click.ClickException(f"Unsupported platform: {system}")


def _resolve_data_path(astrbot_root: Path, configured_path: str | None) -> Path:
    if not configured_path:
        configured_path = "logs/astrbot.log"

    path = Path(configured_path).expanduser()
    if path.is_absolute():
        return path
    return astrbot_root / "data" / path


def _resolve_app_log_path(astrbot_root: Path) -> Path:
    config_path = astrbot_root / "data" / "cmd_config.json"
    if not config_path.exists():
        return _resolve_data_path(astrbot_root, None)

    try:
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return _resolve_data_path(astrbot_root, None)

    if "log_file" in config:
        log_file_config = config.get("log_file") or {}
        return _resolve_data_path(astrbot_root, log_file_config.get("path"))

    return _resolve_data_path(astrbot_root, config.get("log_file_path"))


def _get_config_path(astrbot_root: Path) -> Path:
    return astrbot_root / "data" / "cmd_config.json"


def _load_or_init_config(astrbot_root: Path) -> dict:
    config_path = _get_config_path(astrbot_root)
    if not config_path.exists():
        from astrbot.core.config.default import DEFAULT_CONFIG

        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        return json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"Failed to parse config file: {e}") from e


def _save_config(astrbot_root: Path, config: dict) -> None:
    config_path = _get_config_path(astrbot_root)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8-sig",
    )


def _get_app_log_config(astrbot_root: Path, config: dict) -> AppLogConfig:
    if isinstance(config.get("log_file"), dict):
        log_file_config = config["log_file"]
        configured_path = log_file_config.get("path")
        return AppLogConfig(
            enabled=bool(log_file_config.get("enable", False)),
            path=_resolve_data_path(astrbot_root, configured_path),
            configured_path=configured_path,
        )

    configured_path = config.get("log_file_path")
    return AppLogConfig(
        enabled=bool(config.get("log_file_enable", False)),
        path=_resolve_data_path(astrbot_root, configured_path),
        configured_path=configured_path,
    )


def _set_app_log_config(
    config: dict,
    *,
    enabled: bool,
    path: str | None = None,
) -> None:
    if isinstance(config.get("log_file"), dict):
        config["log_file"]["enable"] = enabled
        if path is not None:
            config["log_file"]["path"] = path
        return

    config["log_file_enable"] = enabled
    if path is not None:
        config["log_file_path"] = path


def _read_last_lines(path: Path, lines: int) -> list[str]:
    with path.open("r", encoding="utf-8", errors="replace") as f:
        return list(deque(f, maxlen=lines))


def _echo_log_line(line: str) -> None:
    click.echo(line.rstrip("\r\n"))


def _show_log_files(paths: list[Path], lines: int, follow: bool) -> None:
    existing_paths = [path for path in paths if path.exists()]
    if not existing_paths:
        joined_paths = ", ".join(str(path) for path in paths)
        raise click.ClickException(f"No log files found: {joined_paths}")

    show_headers = len(existing_paths) > 1
    for index, path in enumerate(existing_paths):
        if show_headers:
            if index:
                click.echo()
            click.echo(f"==> {path} <==")
        for line in _read_last_lines(path, lines):
            _echo_log_line(line)

    if follow:
        _follow_log_files(existing_paths)


def _follow_log_files(paths: list[Path]) -> None:
    positions = {path: path.stat().st_size for path in paths if path.exists()}
    click.echo("Following logs. Press Ctrl+C to stop.")
    try:
        while True:
            for path in paths:
                if not path.exists():
                    continue

                current_size = path.stat().st_size
                previous_position = positions.get(path, 0)
                if current_size < previous_position:
                    previous_position = 0

                with path.open("r", encoding="utf-8", errors="replace") as f:
                    f.seek(previous_position)
                    for line in f:
                        if len(paths) > 1:
                            click.echo(f"[{path.name}] ", nl=False)
                        _echo_log_line(line)
                    positions[path] = f.tell()

            time.sleep(1)
    except KeyboardInterrupt:
        return


def _run_passthrough(command: list[str], failure_message: str) -> None:
    try:
        result = subprocess.run(command, check=False)
    except FileNotFoundError as e:
        raise click.ClickException(f"Command not found: {command[0]}") from e
    except KeyboardInterrupt:
        return

    if result.returncode != 0:
        raise click.ClickException(f"{failure_message}: exit code {result.returncode}")


def _show_journal_logs(service_name: str, lines: int, follow: bool) -> None:
    command = [
        "journalctl",
        "--user",
        "-u",
        _systemd_unit_name(service_name),
        "-n",
        str(lines),
        "--no-pager",
    ]
    if follow:
        command.append("-f")
    _run_passthrough(command, "Failed to read systemd user service logs")


def _show_service_logs(
    service_name: str,
    lines: int,
    follow: bool,
    *,
    include_stderr: bool,
) -> None:
    system = platform.system()
    if system == "Linux":
        _show_journal_logs(service_name, lines, follow)
        return

    if system == "Darwin":
        out_log, err_log = _service_log_paths(service_name)
        paths = [out_log]
        if include_stderr:
            paths.append(err_log)
        _show_log_files(paths, lines, follow)
        return

    raise click.ClickException(f"Unsupported platform: {system}")


@service.command(name="install")
@click.option(
    "--name",
    default=DEFAULT_SERVICE_NAME,
    show_default=True,
    help="Service name to install.",
)
@click.option(
    "--workdir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="AstrBot root directory. Defaults to the current directory.",
)
@click.option(
    "--executable",
    type=str,
    help="Path to the astrbot executable. Defaults to the executable found on PATH.",
)
@click.option("--force", is_flag=True, help="Overwrite an existing service definition.")
@click.option(
    "--now", is_flag=True, help="Start or restart the service after installing it."
)
def install(
    name: str,
    workdir: Path | None,
    executable: str | None,
    force: bool,
    now: bool,
) -> None:
    """Install AstrBot as a user-level background service."""
    service_name = _validate_service_name(name)
    system = platform.system()
    if system not in {"Linux", "Darwin"}:
        raise click.ClickException(f"Unsupported platform: {system}")

    astrbot_root = _resolve_workdir(workdir)
    astrbot_executable = _resolve_astrbot_executable(executable)

    if system == "Linux":
        service_path = _install_systemd_user_service(
            service_name,
            astrbot_executable,
            astrbot_root,
            force=force,
            now=now,
        )
        click.echo(f"Installed systemd user service: {service_path}")
        click.echo(f"Manage it with: systemctl --user status {service_path.name}")
        click.echo(
            "To start it at boot before login, enable lingering with: "
            f"loginctl enable-linger {getpass.getuser()}"
        )
        return

    if system == "Darwin":
        plist_path = _install_launch_agent(
            service_name,
            astrbot_executable,
            astrbot_root,
            force=force,
            now=now,
        )
        click.echo(f"Installed LaunchAgent: {plist_path}")
        click.echo(f"LaunchAgent label: {_macos_label(service_name)}")
        return

    raise click.ClickException(f"Unsupported platform: {system}")


@service.command(name="start")
@click.option(
    "--name",
    default=DEFAULT_SERVICE_NAME,
    show_default=True,
    help="Service name to start.",
)
def start(name: str) -> None:
    """Start the installed background service."""
    service_name = _validate_service_name(name)
    click.echo("Starting service...")
    _control_service(service_name, "start")
    click.echo(f"Started service: {service_name}")


@service.command(name="stop")
@click.option(
    "--name",
    default=DEFAULT_SERVICE_NAME,
    show_default=True,
    help="Service name to stop.",
)
def stop(name: str) -> None:
    """Stop the installed background service."""
    service_name = _validate_service_name(name)
    click.echo("Stopping service...")
    _control_service(service_name, "stop")
    click.echo(f"Stopped service: {service_name}")


@service.command(name="restart")
@click.option(
    "--name",
    default=DEFAULT_SERVICE_NAME,
    show_default=True,
    help="Service name to restart.",
)
def restart(name: str) -> None:
    """Restart the installed background service."""
    service_name = _validate_service_name(name)
    click.echo("Restarting service...")
    _control_service(service_name, "restart")
    click.echo(f"Restarted service: {service_name}")


@service.command(name="uninstall")
@click.option(
    "--name",
    default=DEFAULT_SERVICE_NAME,
    show_default=True,
    help="Service name to uninstall.",
)
@click.option("--force", is_flag=True, help="Do not ask for confirmation.")
def uninstall(name: str, force: bool) -> None:
    """Remove the installed background service."""
    service_name = _validate_service_name(name)
    click.echo("Uninstalling service...")

    if not force:
        click.confirm(
            f"Uninstall AstrBot service {service_name}?",
            default=False,
            abort=True,
        )

    removed = _uninstall_service(service_name)
    click.echo(f"Uninstalled service: {removed}")


@service.group(name="logs", invoke_without_command=True)
@click.pass_context
@click.option(
    "--name",
    default=DEFAULT_SERVICE_NAME,
    show_default=True,
    help="Service name to read logs for.",
)
@click.option(
    "--workdir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="AstrBot root directory. Required only with --source app.",
)
@click.option(
    "--source",
    type=click.Choice(["service", "app"]),
    default="service",
    show_default=True,
    help="Read service manager output or AstrBot application log file.",
)
@click.option(
    "--lines",
    "-n",
    default=DEFAULT_LOG_LINES,
    show_default=True,
    type=int,
    help="Number of lines to show.",
)
@click.option("--follow", "-f", is_flag=True, help="Follow log output.")
@click.option(
    "--include-stderr",
    is_flag=True,
    help="Also show stderr logs on macOS.",
)
def logs(
    ctx: click.Context,
    name: str,
    workdir: Path | None,
    source: str,
    lines: int,
    follow: bool,
    include_stderr: bool,
) -> None:
    """View service logs or configure the application log file."""
    if ctx.invoked_subcommand is not None:
        return

    if lines <= 0:
        raise click.ClickException("Lines must be greater than 0")

    service_name = _validate_service_name(name)
    if source == "app":
        astrbot_root = _resolve_workdir(workdir)
        _show_log_files([_resolve_app_log_path(astrbot_root)], lines, follow)
        return

    _show_service_logs(service_name, lines, follow, include_stderr=include_stderr)


@logs.command(name="status")
@click.option(
    "--workdir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="AstrBot root directory. Defaults to the current directory.",
)
def logs_status(workdir: Path | None) -> None:
    """Show application log file configuration."""
    astrbot_root = _resolve_workdir(workdir)
    config = _load_or_init_config(astrbot_root)
    log_config = _get_app_log_config(astrbot_root, config)

    click.echo("AstrBot application log file")
    click.echo(f"  Enabled: {_format_yes_no(log_config.enabled)}")
    click.echo(f"  Configured path: {log_config.configured_path or 'logs/astrbot.log'}")
    click.echo(f"  Resolved path: {log_config.path}")
    click.echo(f"  Exists: {_format_yes_no(log_config.path.exists())}")


@logs.command(name="enable")
@click.option(
    "--workdir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="AstrBot root directory. Defaults to the current directory.",
)
@click.option(
    "--path",
    "log_path",
    help="Log file path. Relative paths are resolved from the AstrBot data directory.",
)
def logs_enable(workdir: Path | None, log_path: str | None) -> None:
    """Enable the AstrBot application log file."""
    astrbot_root = _resolve_workdir(workdir)
    config = _load_or_init_config(astrbot_root)
    _set_app_log_config(config, enabled=True, path=log_path)
    _save_config(astrbot_root, config)

    log_config = _get_app_log_config(astrbot_root, config)
    click.echo("Enabled AstrBot application log file.")
    click.echo(f"Log path: {log_config.path}")
    click.echo("Restart AstrBot for this change to take effect.")


@logs.command(name="disable")
@click.option(
    "--workdir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="AstrBot root directory. Defaults to the current directory.",
)
def logs_disable(workdir: Path | None) -> None:
    """Disable the AstrBot application log file."""
    astrbot_root = _resolve_workdir(workdir)
    config = _load_or_init_config(astrbot_root)
    _set_app_log_config(config, enabled=False)
    _save_config(astrbot_root, config)

    click.echo("Disabled AstrBot application log file.")
    click.echo("Restart AstrBot for this change to take effect.")


@service.command(name="status")
@click.option(
    "--name",
    default=DEFAULT_SERVICE_NAME,
    show_default=True,
    help="Service name to inspect.",
)
@click.option(
    "--workdir",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="AstrBot root directory. Defaults to the current directory.",
)
@click.option(
    "--timeout",
    default=DEFAULT_STATUS_TIMEOUT_SECONDS,
    show_default=True,
    type=float,
    help="WebUI probe timeout in seconds.",
)
def status(name: str, workdir: Path | None, timeout: float) -> None:
    """Check background service state, WebUI health, and port."""
    if timeout <= 0:
        raise click.ClickException("Timeout must be greater than 0")

    service_name = _validate_service_name(name)
    astrbot_root = _resolve_workdir(workdir)
    service_state = _get_service_state(service_name)
    dashboard_port = _load_dashboard_port(astrbot_root)
    webui_status = _check_webui(dashboard_port.port, timeout)
    health = _health_label(service_state, webui_status)

    click.echo("AstrBot service status")
    click.echo(f"  Health: {health}")
    click.echo(f"  Platform: {platform.system()}")
    click.echo(f"  Service name: {service_name}")
    click.echo(f"  Service manager: {service_state.manager}")
    click.echo(f"  Installed: {_format_yes_no(service_state.installed)}")
    if service_state.path is not None:
        click.echo(f"  Definition: {service_state.path}")
    click.echo(f"  Service state: {service_state.state}")
    if service_state.enabled is not None:
        click.echo(f"  Enabled: {service_state.enabled}")
    if service_state.detail:
        click.echo(f"  Service detail: {service_state.detail}")
    click.echo(f"  AstrBot root: {astrbot_root}")
    click.echo(f"  Dashboard port: {dashboard_port.port}")
    if dashboard_port.detail:
        click.echo(f"  Port detail: {dashboard_port.detail}")
    click.echo(f"  WebUI URL: {webui_status.url}")
    click.echo(f"  WebUI accessible: {_format_yes_no(webui_status.accessible)}")
    if webui_status.status_code is not None:
        click.echo(f"  WebUI HTTP status: {webui_status.status_code}")
    if webui_status.detail:
        click.echo(f"  WebUI detail: {webui_status.detail}")
