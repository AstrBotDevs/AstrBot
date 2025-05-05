import asyncio
import os
import shutil

import click
from pathlib import Path
from ..utils import check_dashboard


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

    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
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
        "root": astrbot_root,
        "config": astrbot_root / "config",
        "plugins": astrbot_root / "plugins",
        "temp": astrbot_root / "temp",
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        click.echo(f"{'Created' if not path.exists() else 'Directory exists'}: {path}")

    asyncio.run(check_dashboard(astrbot_root))
