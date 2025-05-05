import click
import asyncio
from ..utils import get_astrbot_root, check_astrbot_root, check_dashboard


@click.command()
@click.option("--path", "-p", help="AstrBot 数据目录")
def run(path: str | None = None) -> None:
    """运行 AstrBot"""
    try:
        from ..core.log import LogBroker
        from ..core import db_helper
        from ..core.initial_loader import InitialLoader
    except ImportError:
        from astrbot.core.log import LogBroker
        from astrbot.core import db_helper
        from astrbot.core.initial_loader import InitialLoader

    astrbot_root = get_astrbot_root(path)
    check_astrbot_root(astrbot_root)
    asyncio.run(check_dashboard(astrbot_root))

    log_broker = LogBroker()
    db = db_helper

    core_lifecycle = InitialLoader(db, log_broker)
    try:
        asyncio.run(core_lifecycle.start())
    except KeyboardInterrupt:
        click.echo("接收到退出信号，正在关闭 AstrBot...")
    except Exception as e:
        click.echo(f"运行时出现错误: {e}")