from pathlib import Path

import click

from astrbot.cli.i18n import t

from .dashboard import DashboardManager


def check_astrbot_root(path: str | Path) -> bool:
    """Check if the path is an AstrBot root directory."""
    root = Path(path)
    return root.exists() and root.is_dir() and (root / ".astrbot").exists()


def get_astrbot_root() -> Path:
    """Get the current AstrBot root directory path."""
    return Path.cwd()


async def check_dashboard(astrbot_root: Path) -> None:
    """Ensure dashboard assets are installed."""
    try:
        await DashboardManager().ensure_installed(astrbot_root)
    except Exception as exc:
        click.echo(t("dashboard_download_failed", error=str(exc)))
