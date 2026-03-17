import asyncio
import platform
import shutil
import subprocess
from pathlib import Path

import click
from filelock import FileLock, Timeout

from ..utils import check_dashboard, get_astrbot_root

SYSTEMD_SERVICE = r"""
# user service
[Unit]
Description=AstrBot Service
Documentation=https://github.com/AstrBotDevs/AstrBot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/.local/share/astrbot
ExecStart=/usr/bin/sh -c '/usr/bin/astrbot run || { /usr/bin/astrbot init && /usr/bin/astrbot run; }'
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=astrbot-%u
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


async def initialize_astrbot(astrbot_root: Path, *, yes: bool) -> None:
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
    if yes or click.confirm(
        "是否需要集成式 WebUI？（个人电脑推荐，服务器不推荐）",
        default=True,
    ):
        await check_dashboard(astrbot_root)
    else:
        click.echo("你可以使用在线面版（v4.14.4+），填写后端地址的方式来控制。")


@click.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
def init(yes: bool) -> None:
    """Initialize AstrBot"""
    click.echo("Initializing AstrBot...")

    # 检查当前系统是否为 Linux 且存在 systemd
    if platform.system() == "Linux" and shutil.which("systemctl"):
        if yes or click.confirm(
            "Detected Linux with systemd. Install AstrBot user service?", default=True
        ):
            user_config_dir = Path.home() / ".config" / "systemd" / "user"
            user_config_dir.mkdir(parents=True, exist_ok=True)

            service_path = user_config_dir / "astrbot.service"

            service_path.write_text(SYSTEMD_SERVICE)
            click.echo(f"Created service file at {service_path}")

            try:
                subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                click.echo("Systemd daemon reloaded.")
                click.echo("Management commands:")
                click.echo("  Start:  systemctl --user start astrbot")
                click.echo("  Stop:   systemctl --user stop astrbot")
                click.echo("  Enable: systemctl --user enable astrbot")
                click.echo("  Log:    journalctl --user -u astrbot -f")
            except subprocess.CalledProcessError as e:
                click.echo(f"Failed to reload systemd daemon: {e}", err=True)

    astrbot_root = get_astrbot_root()
    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(initialize_astrbot(astrbot_root, yes=yes))
            click.echo("Done! You can now run 'astrbot run' to start AstrBot")
    except Timeout:
        raise click.ClickException(
            "Cannot acquire lock file. Please check if another instance is running"
        )

    except Exception as e:
        raise click.ClickException(f"Initialization failed: {e!s}")
