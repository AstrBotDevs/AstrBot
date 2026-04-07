import sys
from importlib import resources
from pathlib import Path

import click

from astrbot.cli.i18n import t

from .version_comparator import VersionComparator


class DashboardManager:
    _bundled_dist = resources.files("astrbot") / "dashboard" / "dist"

    async def ensure_installed(self, astrbot_root: Path) -> None:
        """Ensure the dashboard assets are installed and up to date."""
        from astrbot.core.config.default import VERSION
        from astrbot.core.utils.io import download_dashboard, get_dashboard_version

        if self._bundled_dist.is_dir():
            click.echo(t("dashboard_bundled"))
            return

        try:
            dashboard_version = await get_dashboard_version()
            match dashboard_version:
                case None:
                    click.echo(t("dashboard_not_installed"))
                    # Skip interactive prompt in non-interactive environments
                    if not sys.stdin.isatty():
                        click.echo(t("dashboard_not_needed"))
                        return
                    if click.confirm(t("dashboard_install_confirm"), default=True):
                        click.echo(t("dashboard_installing"))
                        try:
                            await download_dashboard(
                                path="data/dashboard.zip",
                                extract_path=str(astrbot_root / "data"),
                                version=f"v{VERSION}",
                                latest=False,
                            )
                            click.echo(t("dashboard_install_success"))
                        except Exception as e:
                            click.echo(t("dashboard_install_failed", error=str(e)))
                    else:
                        click.echo(t("dashboard_declined"))

                case str():
                    if (
                        VersionComparator.compare_version(VERSION, dashboard_version)
                        <= 0
                    ):
                        click.echo(t("dashboard_already_up_to_date"))
                        return
                    try:
                        version = dashboard_version.split("v")[1]
                        click.echo(t("dashboard_version", version=version))
                        await download_dashboard(
                            path="data/dashboard.zip",
                            extract_path=str(astrbot_root / "data"),
                            version=f"v{VERSION}",
                            latest=False,
                        )
                    except Exception as e:
                        click.echo(t("dashboard_download_failed", error=str(e)))
                        return
        except FileNotFoundError:
            click.echo(t("dashboard_init_dir"))
            try:
                await download_dashboard(
                    path=str(astrbot_root / "data" / "dashboard.zip"),
                    extract_path=str(astrbot_root / "data"),
                    version=f"v{VERSION}",
                    latest=False,
                )
                click.echo(t("dashboard_init_success"))
            except Exception as e:
                click.echo(t("dashboard_download_failed", error=str(e)))
                return
