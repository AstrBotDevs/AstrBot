import os
import sys
from pathlib import Path

import click
import asyncio
import traceback

from filelock import FileLock, Timeout

from ..utils import check_dashboard, check_astrbot_root, get_astrbot_root


async def run_astrbot(astrbot_root: Path):
    """运行 AstrBot"""
    from astrbot.core import logger, LogManager, LogBroker, db_helper
    from astrbot.core.initial_loader import InitialLoader

    await check_dashboard(astrbot_root / "data")

    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)

    await core_lifecycle.start()


@click.option("--reload", "-r", is_flag=True, help="插件自动重载")
@click.option("--port", "-p", help="Astrbot Dashboard端口", required=False, type=str)
@click.command()
def run(reload: bool, port: str) -> None:
    """运行 AstrBot"""
    try:
        os.environ["ASTRBOT_CLI"] = "1"
        astrbot_root = get_astrbot_root()

        if not check_astrbot_root(astrbot_root):
            raise click.ClickException(
                f"{astrbot_root}不是有效的 AstrBot 根目录，如需初始化请使用 astrbot init"
            )

        os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
        sys.path.insert(0, str(astrbot_root))

        if port:
            os.environ["DASHBOARD_PORT"] = port

        if reload:
            click.echo("启用插件自动重载")
            os.environ["ASTRBOT_RELOAD"] = "1"

        lock_file = astrbot_root / "astrbot.lock"
        lock = FileLock(lock_file, timeout=5)
        with lock.acquire():
            asyncio.run(run_astrbot(astrbot_root))
    except KeyboardInterrupt:
        click.echo("AstrBot 已关闭...")
    except Timeout:
        raise click.ClickException("无法获取锁文件，请检查是否有其他实例正在运行")
    except Exception as e:
        raise click.ClickException(f"运行时出现错误: {e}\n{traceback.format_exc()}")
