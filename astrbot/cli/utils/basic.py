from pathlib import Path

import click

# Static assets bundled inside the installed wheel (built by hatch_build.py).
_BUNDLED_DIST = Path(__file__).parent.parent.parent / "dashboard" / "dist"


def check_astrbot_root(path: str | Path) -> bool:
    """Check if the path is an AstrBot root directory"""
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists() or not path.is_dir():
        return False
    if not (path / ".astrbot").exists():
        return False
    return True


def get_astrbot_root() -> Path:
    """Get the AstrBot root directory path"""
    return Path.cwd()


async def check_dashboard(astrbot_root: Path) -> None:
    """Check if the dashboard is installed"""
    from astrbot.core.updater import AstrBotUpdater

    # If the wheel ships bundled dashboard assets, no network download is needed.
    if _BUNDLED_DIST.exists():
        click.echo("Dashboard is bundled with the package – skipping download.")
        return

    try:
        dashboard_path = await AstrBotUpdater().ensure_dashboard()
        click.echo(f"Dashboard is ready at {dashboard_path}")
    except Exception as exc:
        click.echo(f"Failed to prepare Dashboard: {exc}")
