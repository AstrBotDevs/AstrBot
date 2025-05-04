import os
from pathlib import Path

import click
import asyncio


from ..utils import _check_dashboard, _init_astrbot_root


async def run_astrbot(path: str | None = None):
    """异步运行 AstrBot 的主函数"""
    from astrbot.core import logger, LogManager, LogBroker, db_helper
    from astrbot.core.initial_loader import InitialLoader

    astrbot_root = Path(path).resolve() if path else (Path.cwd() / "data").resolve()
    os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
    _init_astrbot_root(astrbot_root)
    await _check_dashboard(astrbot_root)

    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)

    await core_lifecycle.start()


@click.option("--path", "-p", help="AstrBot 数据目录")
@click.command()
def run(path) -> None:
    """运行 AstrBot"""
    try:
        asyncio.run(run_astrbot(path))
    except KeyboardInterrupt:
        click.echo("AstrBot 已关闭...")
    except Exception as e:
        click.echo(f"运行时出现错误: {e}")
