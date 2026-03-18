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

Dashboard:
- `ASTRBOT_DASHBOARD_ENABLE` / `DASHBOARD_ENABLE`: Enable/Disable Dashboard.
- `ASTRBOT_DASHBOARD_HOST` / `DASHBOARD_HOST`: Dashboard bind host.
- `ASTRBOT_DASHBOARD_PORT` / `DASHBOARD_PORT`: Dashboard bind port.
- `ASTRBOT_DASHBOARD_SSL_ENABLE` / `DASHBOARD_SSL_ENABLE`: Enable SSL.
- `ASTRBOT_DASHBOARD_SSL_CERT` / `DASHBOARD_SSL_CERT`: SSL Certificate path.
- `ASTRBOT_DASHBOARD_SSL_KEY` / `DASHBOARD_SSL_KEY`: SSL Key path.
- `ASTRBOT_DASHBOARD_SSL_CA_CERTS` / `DASHBOARD_SSL_CA_CERTS`: SSL CA Certs path.

Network:
- `http_proxy` / `https_proxy`: Proxy URL.
- `no_proxy`: No proxy list.

Integrations:
- `DASHSCOPE_API_KEY`: Alibaba DashScope API Key (for Rerank).
- `COZE_API_KEY` / `COZE_BOT_ID`: Coze integration.
- `BAY_DATA_DIR`: Computer Use data directory.

Platform Specific:
- `TEST_MODE`: Test mode for QQOfficial.
"""

import asyncio
import os
import sys
import traceback
from pathlib import Path

import click
from filelock import FileLock, Timeout

from astrbot.core.utils.astrbot_path import astrbot_paths

from ..utils import check_astrbot_root, check_dashboard


async def run_astrbot(astrbot_root: Path) -> None:
    """Run AstrBot"""
    from astrbot.core import LogBroker, LogManager, db_helper, logger
    from astrbot.core.initial_loader import InitialLoader

    if (
        os.environ.get("ASTRBOT_DASHBOARD_ENABLE", os.environ.get("DASHBOARD_ENABLE"))
        == "True"
    ):
        # 避免在 systemd 模式下因等待输入而阻塞
        if os.environ.get("ASTRBOT_SYSTEMD") != "1":
            await check_dashboard(astrbot_root)

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
    help="Service configuration file path",
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
    debug: bool,
) -> None:
    """Run AstrBot"""
    try:
        if debug:
            log_level = "DEBUG"

        if service_config:
            svc_path = Path(service_config)
            if svc_path.exists():
                content = svc_path.read_text(encoding="utf-8")
                for line in content.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip()
                        # Remove quotes
                        if (value.startswith('"') and value.endswith('"')) or (
                            value.startswith("'") and value.endswith("'")
                        ):
                            value = value[1:-1]

                        if key == "HOST" and not host:
                            host = value
                        elif key == "PORT" and not port:
                            port = value
                        elif key == "ASTRBOT_ROOT" and not root:
                            root = value

        # Normalize environment variables for backward compatibility
        # If the legacy env var is set but the new one isn't, copy it over.
        env_map = {
            "DASHBOARD_ENABLE": "ASTRBOT_DASHBOARD_ENABLE",
            "DASHBOARD_HOST": "ASTRBOT_DASHBOARD_HOST",
            "DASHBOARD_PORT": "ASTRBOT_DASHBOARD_PORT",
            "DASHBOARD_SSL_ENABLE": "ASTRBOT_DASHBOARD_SSL_ENABLE",
            "DASHBOARD_SSL_CERT": "ASTRBOT_DASHBOARD_SSL_CERT",
            "DASHBOARD_SSL_KEY": "ASTRBOT_DASHBOARD_SSL_KEY",
            "DASHBOARD_SSL_CA_CERTS": "ASTRBOT_DASHBOARD_SSL_CA_CERTS",
        }
        for legacy, new in env_map.items():
            if legacy in os.environ and new not in os.environ:
                os.environ[new] = os.environ[legacy]

        os.environ["ASTRBOT_CLI"] = "1"
        if root:
            os.environ["ASTRBOT_ROOT"] = root
            astrbot_root = Path(root)
        else:
            astrbot_root = astrbot_paths.root

        if not check_astrbot_root(astrbot_root):
            raise click.ClickException(
                f"{astrbot_root} is not a valid AstrBot root directory. Use 'astrbot init' to initialize",
            )

        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        sys.path.insert(0, str(astrbot_root))

        if port is not None:
            os.environ["ASTRBOT_DASHBOARD_PORT"] = port
            os.environ["DASHBOARD_PORT"] = port  # 今后应该移除
        if host is not None:
            os.environ["ASTRBOT_DASHBOARD_HOST"] = host
            os.environ["DASHBOARD_HOST"] = host  # 今后应该移除
        os.environ["ASTRBOT_DASHBOARD_ENABLE"] = str(not backend_only)
        os.environ["DASHBOARD_ENABLE"] = str(not backend_only)  # 今后应该移除
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
                "ASTRBOT_DASHBOARD_HOST",
                "DASHBOARD_HOST",
                "ASTRBOT_DASHBOARD_PORT",
                "DASHBOARD_PORT",
                "ASTRBOT_DASHBOARD_SSL_ENABLE",
                "DASHBOARD_SSL_ENABLE",
                "ASTRBOT_DASHBOARD_SSL_CERT",
                "DASHBOARD_SSL_CERT",
                "ASTRBOT_DASHBOARD_SSL_KEY",
                "DASHBOARD_SSL_KEY",
                "ASTRBOT_DASHBOARD_SSL_CA_CERTS",
                "DASHBOARD_SSL_CA_CERTS",
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
            click.echo("")

        lock_file = astrbot_root / "astrbot.lock"
        lock = FileLock(lock_file, timeout=5)
        with lock.acquire():
            asyncio.run(run_astrbot(astrbot_root))
    except KeyboardInterrupt:
        click.echo("AstrBot has been shut down.")
    except Timeout:
        raise click.ClickException(
            "Cannot acquire lock file. Please check if another instance is running"
        )
    except Exception as e:
        raise click.ClickException(f"Runtime error: {e}\n{traceback.format_exc()}")
