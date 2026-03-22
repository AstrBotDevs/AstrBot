import os
import shutil
from pathlib import Path

import click

from astrbot.core.utils.astrbot_path import astrbot_paths


@click.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--keep-data", is_flag=True, help="Keep data directory (config, plugins, etc.)"
)
def uninstall(yes: bool, keep_data: bool) -> None:
    """Remove AstrBot files from the current root directory."""

    if os.environ.get("ASTRBOT_SYSTEMD") == "1":
        yes = True

    dot_astrbot = astrbot_paths.root / ".astrbot"
    lock_file = astrbot_paths.root / "astrbot.lock"
    data_dir = astrbot_paths.data
    removable_paths: list[Path] = [dot_astrbot, lock_file]

    if not keep_data:
        removable_paths.insert(0, data_dir)

    # Check if this looks like an AstrBot root before blowing things up
    if not dot_astrbot.exists() and not data_dir.exists():
        click.echo("No AstrBot initialization found in current directory.")
        return

    if keep_data:
        click.echo("Keeping data directory as requested.")

    if yes or click.confirm(
        f"Are you sure you want to remove AstrBot data at {astrbot_paths.root}? \n"
        f"This will delete:\n"
        f" - {data_dir} (Config, Plugins, Database)\n"
        f" - {dot_astrbot}\n"
        f" - {lock_file}",
        default=False,
        abort=True,
    ):
        removed_any = False
        for path in removable_paths:
            if not path.exists():
                continue
            removed_any = True
            if path.is_dir():
                click.echo(f"Removing directory: {path}")
                shutil.rmtree(path)
            else:
                click.echo(f"Removing file: {path}")
                path.unlink()

        if removed_any:
            click.echo("AstrBot files removed successfully.")
        else:
            click.echo("No removable AstrBot files were found.")

        # TODO: Consider adding an explicit `--service` cleanup mode instead of
        # touching systemd or other service managers during normal uninstall.
        # TODO: Consider adding package-manager-specific uninstall helpers once
        # the CLI can reliably detect the installation source.
        click.echo("uv: uv tool uninstall astrbot")
        click.echo("paru/yay: paru -R astrbot")
