import platform
import shutil
import subprocess
from pathlib import Path

import click

from ..utils import get_astrbot_root


@click.command()
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompts")
@click.option(
    "--keep-data", is_flag=True, help="Keep data directory (config, plugins, etc.)"
)
def uninstall(yes: bool, keep_data: bool) -> None:
    """Uninstall AstrBot systemd service and cleanup data"""

    # 1. Remove Systemd Service
    if platform.system() == "Linux" and shutil.which("systemctl"):
        service_path = Path.home() / ".config" / "systemd" / "user" / "astrbot.service"

        if service_path.exists():
            if yes or click.confirm(
                "Detected AstrBot systemd service. Stop and remove it?",
                default=True,
            ):
                try:
                    click.echo("Stopping AstrBot service...")
                    subprocess.run(
                        ["systemctl", "--user", "stop", "astrbot"], check=False
                    )

                    click.echo("Disabling AstrBot service...")
                    subprocess.run(
                        ["systemctl", "--user", "disable", "astrbot"], check=False
                    )

                    click.echo(f"Removing service file: {service_path}")
                    service_path.unlink()

                    click.echo("Reloading systemd daemon...")
                    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
                    click.echo("Systemd service uninstalled.")

                except subprocess.CalledProcessError as e:
                    click.echo(f"Failed to remove systemd service: {e}", err=True)
                except Exception as e:
                    click.echo(
                        f"An error occurred during service removal: {e}", err=True
                    )

    # 2. Remove Data
    astrbot_root = get_astrbot_root()
    data_dir = astrbot_root / "data"
    dot_astrbot = astrbot_root / ".astrbot"
    lock_file = astrbot_root / "astrbot.lock"

    if keep_data:
        click.echo("Skipping data removal as requested.")
        return

    # Check if this looks like an AstrBot root before blowing things up
    if not dot_astrbot.exists() and not data_dir.exists():
        click.echo("No AstrBot initialization found in current directory.")
        return

    if yes or click.confirm(
        f"Are you sure you want to remove AstrBot data at {astrbot_root}? \n"
        f"This will delete:\n"
        f" - {data_dir} (Config, Plugins, Database)\n"
        f" - {dot_astrbot}\n"
        f" - {lock_file}",
        default=False,
        abort=True,
    ):
        if data_dir.exists():
            click.echo(f"Removing directory: {data_dir}")
            shutil.rmtree(data_dir)

        if dot_astrbot.exists():
            click.echo(f"Removing file: {dot_astrbot}")
            dot_astrbot.unlink()

        if lock_file.exists():
            click.echo(f"Removing file: {lock_file}")
            lock_file.unlink()

        click.echo("AstrBot data removed successfully.")
