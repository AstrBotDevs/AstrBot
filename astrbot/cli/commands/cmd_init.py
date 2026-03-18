import asyncio
import os
from pathlib import Path

import click
from filelock import FileLock, Timeout

from astrbot.core.utils.astrbot_path import astrbot_paths

from ..utils import check_dashboard


async def initialize_astrbot(
    astrbot_root: Path, *, yes: bool, backend_only: bool
) -> None:
    """Execute AstrBot initialization logic"""
    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
        if yes or click.confirm(
            f"Install AstrBot to this directory? {astrbot_root}",
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
        click.echo(
            f"{'Created' if not path.exists() else f'{name} Directory exists'}: {path}"
        )

    if not backend_only and (
        yes
        or click.confirm(
            "是否需要集成式 WebUI？（个人电脑推荐，服务器不推荐）",
            default=True,
        )
    ):
        # 避免在 systemd 模式下因等待输入而阻塞
        if os.environ.get("ASTRBOT_SYSTEMD") == "1":
            click.echo("Systemd detected: Skipping dashboard check.")
        else:
            await check_dashboard(astrbot_root)
    else:
        click.echo("你可以使用在线面版（v4.14.4+），填写后端地址的方式来控制。")


@click.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--backend-only", "-b", is_flag=True, help="Only initialize the backend")
@click.option("--backup", help="Initialize from backup file", type=str)
def init(yes: bool, backend_only: bool, backup: str | None) -> None:
    """Initialize AstrBot"""
    click.echo("Initializing AstrBot...")

    if os.environ.get("ASTRBOT_SYSTEMD") == "1":
        yes = True

    astrbot_root = astrbot_paths.root
    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(
                initialize_astrbot(astrbot_root, yes=yes, backend_only=backend_only)
            )

            if backup:
                from .cmd_bk import import_data_command

                click.echo(f"Restoring from backup: {backup}")
                click.get_current_context().invoke(
                    import_data_command, backup_file=backup, yes=True
                )

            click.echo("Done! You can now run 'astrbot run' to start AstrBot")
    except Timeout:
        raise click.ClickException(
            "Cannot acquire lock file. Please check if another instance is running"
        )

    except Exception as e:
        raise click.ClickException(f"Initialization failed: {e!s}")
