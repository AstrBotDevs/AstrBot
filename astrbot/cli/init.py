import asyncio
import datetime
from pathlib import Path

import click
from filelock import FileLock, Timeout

from . import __version__

from .utils import check_dashboard


async def initialize_astrbot(astrbot_root) -> None:
    """执行 AstrBot 初始化逻辑"""
    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
        click.echo(f"Current Directory: {click.style(str(astrbot_root), fg='yellow')}")
        click.echo(
            "如果你确认这是 Astrbot root directory, 你需要在当前目录下创建一个 .astrbot 文件标记该目录为 AstrBot 的数据目录。"
        )
        if click.confirm(
            f"请检查当前目录是否正确，确认正确请回车: {astrbot_root}",
            default=True,
            abort=True,
        ):
            dot_astrbot.touch()
            metadata = {}
            metadata["last_update"] = datetime.datetime.now().strftime("%d/%m/%Y, %H:%M:%S")
            metadata["version"] = __version__

            import toml

            with open(dot_astrbot,"w") as f:
                toml.dump(metadata,f)


            click.echo(f"Created {click.style(str(dot_astrbot), fg='green')}")

    paths = {
        "data": astrbot_root / "data",
        "config": astrbot_root / "data" / "config",
        "plugins": astrbot_root / "data" / "plugins",
        "temp": astrbot_root / "data" / "temp",
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        status = "Created" if not path.exists() else "Directory exists"
        status_color = "green" if status == "Created" else "cyan"
        click.echo(f"{click.style(status, fg=status_color)}: {click.style(str(path), fg='yellow')}")

    await check_dashboard(astrbot_root / "data")


@click.command()
@click.option("--root","-r",envvar="ASTRBOT_ROOT",required=True ,help="astrbot根目录，--root cwd表示使用当前目录",default=Path.home() / ".astrbot" )
def init(root: str) -> None:
    """初始化 AstrBot"""
    if root == "cwd":
        astrbot_root = Path.cwd()
    else:
        astrbot_root = Path(root)

    click.echo(click.style("Initializing AstrBot...", fg="green", bold=True))

    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(initialize_astrbot(astrbot_root))
        click.echo(click.style("✓ AstrBot initialization completed successfully!", fg="green", bold=True))
    except Timeout:
        raise click.ClickException(click.style("无法获取锁文件，请检查是否有其他实例正在运行", fg="red"))

    except Exception as e:
        raise click.ClickException(click.style(f"初始化失败: {e!s}", fg="red"))
