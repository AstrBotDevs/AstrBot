import asyncio
import os
from pathlib import Path

import click
from filelock import FileLock, Timeout

from ..utils import check_dashboard, get_astrbot_root

DASHBOARD_INITIAL_PASSWORD_ENV = "ASTRBOT_DASHBOARD_INITIAL_PASSWORD"


def _initialize_config_from_env(astrbot_root: Path) -> None:
    if DASHBOARD_INITIAL_PASSWORD_ENV not in os.environ:
        return

    from astrbot.core.config.astrbot_config import AstrBotConfig

    AstrBotConfig(config_path=str(astrbot_root / "data" / "cmd_config.json"))
    click.echo("Initialized data/cmd_config.json with dashboard initial password.")


async def initialize_astrbot(astrbot_root: Path) -> None:
    """Execute AstrBot initialization logic.

    Args:
        astrbot_root: Runtime root directory to initialize.
    """
    dot_astrbot = astrbot_root / ".astrbot"

    if not dot_astrbot.exists():
        dot_astrbot.touch()
        click.echo(f"Created {dot_astrbot}")

    paths = {
        "data": astrbot_root / "data",
        "config": astrbot_root / "data" / "config",
        "plugins": astrbot_root / "data" / "plugins",
        "temp": astrbot_root / "data" / "temp",
    }

    for name, path in paths.items():
        path_exists = path.exists()
        path.mkdir(parents=True, exist_ok=True)
        click.echo(f"{'Directory exists' if path_exists else 'Created'}: {path}")

    _initialize_config_from_env(astrbot_root)

    await check_dashboard(astrbot_root / "data")


@click.command()
def init() -> None:
    """Initialize AstrBot"""
    click.echo("Initializing AstrBot...")
    if os.environ.get("ASTRBOT_ROOT"):
        astrbot_root = get_astrbot_root()
        click.echo(f"Using ASTRBOT_ROOT: {astrbot_root}")
    else:
        user_root = (Path.home() / ".astrbot").resolve()
        current_root = Path.cwd().resolve()
        click.echo("Choose AstrBot runtime directory:")
        click.echo(f"1. {user_root} (recommended)")
        click.echo(f"2. Current directory: {current_root}")
        choice = click.prompt(
            "Select",
            type=click.Choice(["1", "2"]),
            default="1",
            show_choices=False,
        )
        astrbot_root = user_root if choice == "1" else current_root

    astrbot_root.mkdir(parents=True, exist_ok=True)
    os.environ["ASTRBOT_ROOT"] = str(astrbot_root)
    lock_file = astrbot_root / "astrbot.lock"
    lock = FileLock(lock_file, timeout=5)

    try:
        with lock.acquire():
            asyncio.run(initialize_astrbot(astrbot_root))
            click.echo("Done! You can now run 'astrbot run' to start AstrBot")
    except Timeout:
        raise click.ClickException(
            "Cannot acquire lock file. Please check if another instance is running"
        )
    except click.Abort:
        raise

    except Exception as e:
        raise click.ClickException(f"Initialization failed: {e!s}")
