from astrbot.core.lang import t
import asyncio
from pathlib import Path

import click
from filelock import FileLock, Timeout

from ..utils import check_dashboard, get_astrbot_root


async def initialize_astrbot(astrbot_root: Path) -> None:
    """执行 AstrBot 初始化逻辑"""
    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
        click.echo(t("msg-a90a250e", astrbot_root=astrbot_root))
        click.echo(
            t("msg-4deda62e"),
        )
        if click.confirm(
            f"请检查当前目录是否正确，确认正确请回车: {astrbot_root}",
            default=True,
            abort=True,
        ):
            dot_astrbot.touch()
            click.echo(t("msg-3319bf71", dot_astrbot=dot_astrbot))

    paths = {
        "data": astrbot_root / "data",
        "config": astrbot_root / "data" / "config",
        "plugins": astrbot_root / "data" / "plugins",
        "temp": astrbot_root / "data" / "temp",
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        click.echo(t("msg-7054f44f", res='Created' if not path.exists() else 'Directory exists', path=path))

    await check_dashboard(astrbot_root / "data")


@click.command()
def init() -> None:
    """初始化 AstrBot"""
    click.echo(t("msg-b19edc8a"))
    astrbot_root = get_astrbot_root()
    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(initialize_astrbot(astrbot_root))
    except Timeout:
        raise click.ClickException(t("msg-eebc39e3"))

    except Exception as e:
        raise click.ClickException(t("msg-e16da80f", e=e))
