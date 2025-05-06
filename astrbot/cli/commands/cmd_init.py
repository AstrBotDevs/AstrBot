import asyncio

import click
from filelock import FileLock, Timeout

from ..utils import check_dashboard, get_astrbot_root


async def initialize_astrbot(astrbot_root) -> None:
    """执行 AstrBot 初始化逻辑"""
    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
        click.echo(f"Current Directory: {astrbot_root}")
        click.echo(
            "如果你确认这是 Astrbot root directory, 你需要在当前目录下创建一个 .astrbot 文件标记该目录为 AstrBot 的数据目录。"
        )
        if click.confirm(
            f"请检查当前目录是否正确，确认正确请回车: {astrbot_root}",
            default=True,
            abort=True,
        ):
            dot_astrbot.touch()
            click.echo(f"Created {dot_astrbot}")

    paths = {
        "data": astrbot_root / "data",
        "config": astrbot_root / "data" / "config",
        "plugins": astrbot_root / "data" / "plugins",
        "temp": astrbot_root / "data" / "temp",
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        click.echo(f"{'Created' if not path.exists() else 'Directory exists'}: {path}")

    await check_dashboard(astrbot_root / "data")


@click.command()
def init() -> None:
    """初始化 AstrBot"""
    click.echo("Initializing AstrBot...")
    astrbot_root = get_astrbot_root()
    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(initialize_astrbot(astrbot_root))
    except Timeout:
        raise click.ClickException("无法获取锁文件，请检查是否有其他实例正在运行")

    except Exception as e:
        raise click.ClickException(f"初始化失败: {e!s}")
