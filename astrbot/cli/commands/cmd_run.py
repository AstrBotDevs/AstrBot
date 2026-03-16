import asyncio
import os
import sys
import traceback
from pathlib import Path

import click
from filelock import FileLock, Timeout

from ..utils import check_astrbot_root, check_dashboard, get_astrbot_root


async def run_astrbot(astrbot_root: Path) -> None:
    """Run AstrBot"""
    from astrbot.core import LogBroker, LogManager, db_helper, logger
    from astrbot.core.initial_loader import InitialLoader

    if (
        os.environ.get("ASTRBOT_DASHBOARD_ENABLE", os.environ.get("DASHBOARD_ENABLE"))
        == "True"
    ):
        await check_dashboard(astrbot_root)

    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)

    await core_lifecycle.start()


@click.option("--reload", "-r", is_flag=True, help="Auto-reload plugins")
@click.option("--host", "-H", help="AstrBot Dashboard Host", required=False, type=str)
@click.option("--port", "-p", help="AstrBot Dashboard port", required=False, type=str)
@click.option(
    "--backend-only",
    is_flag=True,
    default=False,
    help="Disable WebUI, run backend only",
)
@click.option(
    "--log-level",
    help="Log level",
    required=False,
    type=str,
    default="INFO",
)
@click.command()
def run(reload: bool, host: str, port: str, backend_only: bool, log_level: str) -> None:
    """Run AstrBot"""
    try:
        os.environ["ASTRBOT_CLI"] = "1"
        astrbot_root = get_astrbot_root()

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
