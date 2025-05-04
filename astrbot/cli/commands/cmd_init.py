import asyncio
import os
import shutil

import click
from pathlib import Path
from ..utils import _init_astrbot_root, _check_dashboard


@click.command()
@click.option("--path", "-p", help="AstrBot 数据目录")
@click.option("--force", "-f", is_flag=True, help="强制初始化")
def init(path: str | None, force: bool) -> None:
    """初始化 AstrBot"""
    click.echo("Initializing AstrBot...")
    astrbot_root = Path(path).resolve() if path else (Path.cwd() / "data").resolve()
    os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
    if force:
        if click.confirm(
            "强制初始化会删除数据目录下的所有文件，是否继续？",
            default=False,
            abort=True,
        ):
            click.echo("正在删除数据目录下的所有文件...")
            shutil.rmtree(astrbot_root, ignore_errors=True)

    click.echo(f"AstrBot root directory: {astrbot_root}")
    _init_astrbot_root(astrbot_root)
    asyncio.run(_check_dashboard(astrbot_root))
