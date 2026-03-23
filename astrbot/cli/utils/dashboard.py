import os
import sys
from importlib import resources
from pathlib import Path

import click

from .version_comparator import VersionComparator


class DashboardManager:
    _bundled_dist = resources.files("astrbot") / "dashboard" / "dist"

    async def ensure_installed(self, astrbot_root: Path) -> None:
        """Ensure the dashboard assets are installed and up to date."""
        from astrbot.core.config.default import VERSION
        from astrbot.core.utils.io import download_dashboard, get_dashboard_version

        if self._bundled_dist.is_dir():
            click.echo("Dashboard is bundled with the package - skipping download.")
            return

        try:
            dashboard_version = await get_dashboard_version()
            match dashboard_version:
                case None:
                    click.echo("Dashboard is not installed")
                    # Skip interactive prompt in non-interactive environments
                    if not sys.stdin.isatty():
                        click.echo(
                            "Skipping interactive dashboard installation in non-interactive mode."
                        )
                        return
                    if click.confirm(
                        "Install dashboard?",
                        default=True,
                    ):
                        click.echo("Installing dashboard...")
                        try:
                            await download_dashboard(
                                path="data/dashboard.zip",
                                extract_path=str(astrbot_root / "data"),
                                version=f"v{VERSION}",
                                latest=False,
                            )
                            click.echo("Dashboard installed successfully")
                        except Exception as e:
                            click.echo(f"Failed to install dashboard: {e}")
                    else:
                        click.echo("Dashboard installation declined.")

                case str():
                    if (
                        VersionComparator.compare_version(VERSION, dashboard_version)
                        <= 0
                    ):
                        click.echo("Dashboard is already up to date")
                        return
                    try:
                        version = dashboard_version.split("v")[1]
                        click.echo(f"Dashboard version: {version}")
                        await download_dashboard(
                            path="data/dashboard.zip",
                            extract_path=str(astrbot_root / "data"),
                            version=f"v{VERSION}",
                            latest=False,
                        )
                    except Exception as e:
                        click.echo(f"Failed to download dashboard: {e}")
                        return
        except FileNotFoundError:
            click.echo("Initializing dashboard directory...")
            try:
                await download_dashboard(
                    path=str(astrbot_root / "data" / "dashboard.zip"),
                    extract_path=str(astrbot_root / "data"),
                    version=f"v{VERSION}",
                    latest=False,
                )
                click.echo("Dashboard initialized successfully")
            except Exception as e:
                click.echo(f"Failed to download dashboard: {e}")
                return
