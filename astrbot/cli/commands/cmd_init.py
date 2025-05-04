import shutil

import click
import asyncio
from pathlib import Path
from ..utils import _get_astrbot_root, _check_astrbot_root, _check_dashboard


@click.command()
@click.option("--path", "-p", help="AstrBot 数据目录")
@click.option("--force", "-f", is_flag=True, help="强制初始化")
def init(path: str | None, force: bool) -> None:
    """初始化 AstrBot"""
    click.echo("Initializing AstrBot...")
    astrbot_root = _get_astrbot_root(path)
    if force:
        if click.confirm(
            "强制初始化会删除当前目录下的所有文件，是否继续？",
            default=False,
            abort=True,
        ):
            click.echo("正在删除当前目录下的所有文件...")
            shutil.rmtree(astrbot_root, ignore_errors=True)

    _check_astrbot_root(astrbot_root)

    click.echo(f"AstrBot root directory: {astrbot_root}")

    if not astrbot_root.exists():
        astrbot_root.mkdir(parents=True, exist_ok=True)
        click.echo(f"Created directory: {astrbot_root}")
    else:
        click.echo(f"Directory already exists: {astrbot_root}")

    config_path: Path = astrbot_root / "config"
    plugins_path: Path = astrbot_root / "plugins"
    temp_path: Path = astrbot_root / "temp"
    config_path.mkdir(parents=True, exist_ok=True)
    plugins_path.mkdir(parents=True, exist_ok=True)
    temp_path.mkdir(parents=True, exist_ok=True)

    click.echo(f"Created directories: {config_path}, {plugins_path}, {temp_path}")

    asyncio.run(_check_dashboard(astrbot_root))
