import asyncio
import json
import os
from pathlib import Path

import click
from filelock import FileLock, Timeout

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.astrbot_path import astrbot_paths

from ..utils import check_dashboard
from .cmd_conf import (
    _validate_dashboard_password,
    ensure_config_file,
    prompt_dashboard_password,
    set_dashboard_credentials,
)


async def initialize_astrbot(
    astrbot_root: Path,
    *,
    yes: bool,
    backend_only: bool,
    admin_username: str | None,
    admin_password: str | None,
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
        "skills": astrbot_root / "data" / "skills",
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        click.echo(
            f"{'Created' if not path.exists() else f'{name} Directory exists'}: {path}"
        )

    config_path = astrbot_root / "data" / "cmd_config.json"
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        click.echo(f"Created config file: {config_path}")

    if admin_password and not admin_username:
        raise click.ClickException(
            "--admin-password requires --admin-username to be provided"
        )

    if admin_username:
        password_hash = (
            _validate_dashboard_password(admin_password)
            if admin_password is not None
            else None
        )
        if password_hash is None:
            if yes or os.environ.get("ASTRBOT_SYSTEMD") == "1":
                raise click.ClickException(
                    "Non-interactive init requires --admin-password when --admin-username is set"
                )
            password_hash = prompt_dashboard_password("Dashboard admin password")

        config = ensure_config_file()
        set_dashboard_credentials(
            config,
            username=admin_username.strip(),
            password_hash=password_hash,
        )
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        click.echo(f"Configured dashboard admin username: {admin_username.strip()}")

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
        click.echo("你可以使用在线面版（需支持配置后端）来控制。")


@click.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option("--backend-only", "-b", is_flag=True, help="Only initialize the backend")
@click.option("--backup", "-f", help="Initialize from backup file", type=str)
@click.option(
    "-u",
    "--admin-username",
    type=str,
    help="Set dashboard admin username during initialization",
)
@click.option(
    "-p",
    "--admin-password",
    type=str,
    help="Set dashboard admin password during initialization without prompting",
)
def init(
    yes: bool,
    backend_only: bool,
    backup: str | None,
    admin_username: str | None,
    admin_password: str | None,
) -> None:
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
                initialize_astrbot(
                    astrbot_root,
                    yes=yes,
                    backend_only=backend_only,
                    admin_username=admin_username,
                    admin_password=admin_password,
                )
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
