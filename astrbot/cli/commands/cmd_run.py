"""AstrBot Run
Environment Variables Used in Project:

Core:
- `ASTRBOT_ROOT`: AstrBot root directory path.
- `ASTRBOT_LOG_LEVEL`: Log level (e.g. INFO, DEBUG).
- `ASTRBOT_CLI`: Flag indicating execution via CLI.
- `ASTRBOT_DESKTOP_CLIENT`: Flag indicating execution via desktop client.
- `ASTRBOT_SYSTEMD`: Flag indicating execution via systemd service.
- `ASTRBOT_RELOAD`: Enable plugin auto-reload (set to "1").
- `ASTRBOT_DISABLE_METRICS`: Disable metrics upload (set to "1").
- `TESTING`: Enable testing mode.
- `DEMO_MODE`: Enable demo mode.
- `PYTHON`: Python executable path override (for local code execution).

Dashboard / Backend:
- `ASTRBOT_DASHBOARD_ENABLE`: Enable/Disable Dashboard.
- `ASTRBOT_HOST`: Dashboard bind host.
- `ASTRBOT_PORT`: Dashboard bind port.

SSL (AstrBot-standard names):
- `ASTRBOT_SSL_ENABLE`: Enable SSL for API.
- `ASTRBOT_SSL_CERT`: SSL Certificate path for backend.
- `ASTRBOT_SSL_KEY`: SSL Key path for backend.
- `ASTRBOT_SSL_CA_CERTS`: SSL CA Certs path for backend.

Network:
- `http_proxy` / `https_proxy`: Proxy URL.
- `no_proxy`: No proxy list.

Internationalization:
- `ASTRBOT_CLI_LANG`: CLI interface language (zh/en).
- `ASTRBOT_TUI_LANG`: TUI interface language (zh/en).

Integrations:
- `DASHSCOPE_API_KEY`: Alibaba DashScope API Key (for Rerank).
- `COZE_API_KEY` / `COZE_BOT_ID`: Coze integration.
- `BAY_DATA_DIR`: Computer Use data directory.

Platform Specific:
- `TEST_MODE`: Test mode for QQOfficial.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import traceback
from pathlib import Path

import click
from dotenv import load_dotenv
from filelock import FileLock, Timeout

from astrbot.cli.utils import DashboardManager
from astrbot.runtime_bootstrap import initialize_runtime_bootstrap

initialize_runtime_bootstrap()
# Regular expression to find bash-like parameter expansions:
# ${VAR:-default} or ${VAR}
_PARAM_EXPAND_RE = re.compile(r"\$\{([^}:]+?)(:-([^}]*))?\}")


def _expand_parameter(
    match: re.Match, env: dict[str, str], local: dict[str, str]
) -> str:
    """Helper to expand a single ${VAR:-default} or ${VAR} occurrence.

    Precedence:
      1. local dict (parsed from the same file, earlier entries)
      2. environment variables
      3. default provided in the expansion (if any)
      4. empty string
    """
    var = match.group(1)
    default = match.group(3) if match.group(3) is not None else ""
    # Prefer 'local' parsed values first
    if var in local and local[var] != "":
        return local[var]
    val = env.get(var, "")
    if val != "":
        return val
    return default


async def run_astrbot(astrbot_root: Path) -> None:
    """Run AstrBot"""
    from astrbot.core import LogBroker, LogManager, db_helper, logger
    from astrbot.core.initial_loader import InitialLoader

    if (
        os.environ.get("ASTRBOT_DASHBOARD_ENABLE", os.environ.get("DASHBOARD_ENABLE"))
        == "True"
    ):
        await DashboardManager().ensure_installed(astrbot_root)

    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)

    await core_lifecycle.start()


@click.option("--reload", "-r", is_flag=True, help="Auto-reload plugins")
@click.option("--host", "-H", help="AstrBot Dashboard Host", required=False, type=str)
@click.option("--port", "-p", help="AstrBot Dashboard port", required=False, type=str)
@click.option("--root", help="AstrBot root directory", required=False, type=str)
@click.option(
    "--service-config",
    "-c",
    help="Service configuration file path (supports ${VAR:-default} style expansion)",
    required=False,
    type=str,
)
@click.option(
    "--backend-only",
    "-b",
    is_flag=True,
    default=False,
    help="Disable WebUI, run backend only",
)
@click.option(
    "--log-level",
    "-l",
    help="Log level",
    required=False,
    type=str,
    default="INFO",
)
@click.option(
    "--ssl-cert",
    help="SSL certificate file path for backend (preferred env name: ASTRBOT_SSL_CERT)",
    required=False,
    type=str,
)
@click.option(
    "--ssl-key",
    help="SSL private key file path for backend (preferred env name: ASTRBOT_SSL_KEY)",
    required=False,
    type=str,
)
@click.option(
    "--ssl-ca",
    help="SSL CA certificates file path for backend (preferred env name: ASTRBOT_SSL_CA_CERTS)",
    required=False,
    type=str,
)
@click.option("--debug", is_flag=True, help="Enable debug mode")
@click.command()
def run(
    reload: bool,
    host: str,
    port: str,
    root: str,
    service_config: str,
    backend_only: bool,
    log_level: str,
    ssl_cert: str,
    ssl_key: str,
    ssl_ca: str,
    debug: bool,
) -> None:
    """Run AstrBot"""
    try:
        if debug:
            log_level = "DEBUG"

        # --- Step 1: Resolve service-config path (if provided). We'll treat it as a .env file later. ---
        svc_path: Path | None = None
        if service_config:
            candidate = Path(service_config)
            if not candidate.exists():
                # Try to expand user and resolve
                candidate = Path(os.path.expanduser(service_config))
            if candidate.exists():
                svc_path = candidate

        # NOTE:
        # Loading of common .env files (CWD/.env, packaged project .env, ASTRBOT_ROOT/.env)
        # has been moved to astrbot.core.utils.astrbot_path during import-time to avoid
        # early-initialization ordering issues. Those files are loaded there using
        # `override=False` so they do not clobber environment variables provided by the
        # systemd unit or the caller.
        #
        # Here we only load an explicit service-config file (if given). Service-config
        # should be able to override the common .env files, but CLI-provided values must
        # still win; the CLI will set/overwrite corresponding environment variables
        # below after this load.
        if svc_path and svc_path.exists():
            # Load service-config as an env file and allow it to override previously-loaded
            # .env values (those were loaded by astrbot_path). CLI variables are applied
            # after this point and will take precedence.
            load_dotenv(dotenv_path=str(svc_path), override=True)

        # Mark CLI execution
        os.environ["ASTRBOT_CLI"] = "1"

        from astrbot.core.utils.astrbot_path import astrbot_paths

        # Resolve astrbot_root with the following precedence:
        # 1. CLI --root parameter (local variable `root`)
        # 2. ASTRBOT_ROOT environment variable (possibly from .env or parsed service config)
        # 3. packaged default astrbot_paths.root
        if root:
            os.environ["ASTRBOT_ROOT"] = root
            astrbot_root = Path(root)
        elif os.environ.get("ASTRBOT_ROOT"):
            astrbot_root = Path(os.environ["ASTRBOT_ROOT"])
        else:
            astrbot_root = astrbot_paths.root

        if not astrbot_paths.is_root:
            raise click.ClickException(
                f"{astrbot_root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize",
            )

        # Ensure ASTRBOT_ROOT env var is set to the resolved root (without overriding a CLI-provided root value above)
        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        sys.path.insert(0, str(astrbot_root))

        # Host/Port precedence: CLI args > parsed service config/env/.env > defaults.
        if port is not None:
            os.environ["ASTRBOT_PORT"] = port

        if host is not None:
            os.environ["ASTRBOT_HOST"] = host

        # CLI-provided SSL paths should set backend-standard env names.
        if ssl_cert is not None:
            os.environ["ASTRBOT_SSL_CERT"] = ssl_cert
        if ssl_key is not None:
            os.environ["ASTRBOT_SSL_KEY"] = ssl_key
        if ssl_ca is not None:
            os.environ["ASTRBOT_SSL_CA_CERTS"] = ssl_ca

        # Dashboard enable is derived from CLI flag (--backend-only). CLI decision should win.
        os.environ["ASTRBOT_DASHBOARD_ENABLE"] = str(not backend_only)

        os.environ["ASTRBOT_LOG_LEVEL"] = log_level

        if reload:
            click.echo("Plugin auto-reload enabled")
            os.environ["ASTRBOT_RELOAD"] = "1"

        if debug:
            keys_to_print = [
                "ASTRBOT_ROOT",
                "ASTRBOT_LOG_LEVEL",
                "ASTRBOT_CLI",
                "ASTRBOT_DESKTOP_CLIENT",
                "ASTRBOT_SYSTEMD",
                "ASTRBOT_RELOAD",
                "ASTRBOT_DISABLE_METRICS",
                "TESTING",
                "DEMO_MODE",
                "PYTHON",
                "ASTRBOT_DASHBOARD_ENABLE",
                "DASHBOARD_ENABLE",
                "ASTRBOT_HOST",
                "DASHBOARD_HOST",
                "ASTRBOT_PORT",
                "DASHBOARD_PORT",
                # Dashboard SSL (legacy)
                "ASTRBOT_SSL_ENABLE",
                "DASHBOARD_SSL_ENABLE",
                "ASTRBOT_SSL_CERT",
                "DASHBOARD_SSL_CERT",
                "ASTRBOT_SSL_KEY",
                "DASHBOARD_SSL_KEY",
                "ASTRBOT_SSL_CA_CERTS",
                "DASHBOARD_SSL_CA_CERTS",
                # Backend-standard SSL (preferred)
                "ASTRBOT_SSL_ENABLE",
                "ASTRBOT_SSL_CERT",
                "ASTRBOT_SSL_KEY",
                "ASTRBOT_SSL_CA_CERTS",
                "http_proxy",
                "https_proxy",
                "no_proxy",
                "DASHSCOPE_API_KEY",
                "COZE_API_KEY",
                "COZE_BOT_ID",
                "BAY_DATA_DIR",
                "TEST_MODE",
            ]
            click.secho("\n[Debug Mode] Environment Variables:", fg="yellow", bold=True)
            for key in keys_to_print:
                if key in os.environ:
                    val = os.environ[key]
                    if "KEY" in key or "PASSWORD" in key or "SECRET" in key:
                        if len(val) > 8:
                            val = val[:4] + "****" + val[-4:]
                        else:
                            val = "****"
                    click.echo(f"  {click.style(key, fg='cyan')}: {val}")
            if svc_path:
                click.echo(
                    f"  {click.style('SERVICE_CONFIG', fg='cyan')}: {svc_path!s}"
                )
            click.echo("")

        lock_file = astrbot_root / "astrbot.lock"
        lock = FileLock(lock_file, timeout=5)
        with lock.acquire():
            # Use TUI if in interactive TTY mode
            if sys.stdin.isatty() and sys.stdout.isatty():
                from astrbot.cli.commands.cmd_run_tui import run_tui

                async def wrapped_startup() -> None:
                    await run_astrbot(astrbot_root)

                asyncio.run(
                    run_tui(
                        startup_coro=wrapped_startup,
                        astrbot_root=astrbot_root,
                        backend_only=backend_only,
                        host=os.environ.get("ASTRBOT_HOST"),
                        port=os.environ.get("ASTRBOT_PORT"),
                    )
                )
            else:
                click.echo("AstrBot is running...")
                if backend_only:
                    click.echo("Visit the dashboard at : https://dash.astrbot.men/")
                    click.echo("Backend Requests : localhost or based on https")

                asyncio.run(run_astrbot(astrbot_root))
    except KeyboardInterrupt:
        click.echo("AstrBot has been shut down.")
    except Timeout:
        raise click.ClickException(
            "Cannot acquire lock file. Please check if another instance is running"
        )
    except Exception as e:
        # Keep original traceback visible for diagnostics
        raise click.ClickException(f"Runtime error: {e}\n{traceback.format_exc()}")
