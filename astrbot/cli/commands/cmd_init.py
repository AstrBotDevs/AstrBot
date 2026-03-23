import asyncio
import json
import os
import re
from pathlib import Path

import click
from filelock import FileLock, Timeout

from astrbot.cli.utils import DashboardManager
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.astrbot_path import astrbot_paths

from .cmd_conf import (
    ensure_config_file,
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

    # Generate an .env for this instance from the bundled config.template (if available).
    # The generated file will be written to ASTRBOT_ROOT/.env and will be automatically
    # loaded by `astrbot run` (service-config/.env precedence applies).
    ASTRBOT_ROOT = astrbot_root
    env_file = ASTRBOT_ROOT / ".env"
    if not env_file.exists():
        tmpl_candidates = [
            Path("/opt/astrbot/config.template"),
            # project_root may point to the installed package directory; try it as well
            getattr(astrbot_paths, "project_root", Path.cwd()) / "config.template",
            Path.cwd() / "config.template",
        ]
        tmpl = None
        for t in tmpl_candidates:
            try:
                if t.exists():
                    tmpl = t
                    break
            except Exception:
                continue
        if tmpl is not None:
            try:
                txt = tmpl.read_text(encoding="utf-8")
                # Determine instance name for template replacement (fallback to directory name)
                instance_name = astrbot_root.name or "astrbot"
                # Substitute ${VAR} and ${VAR:-default} for INSTANCE_NAME, PORT, ASTRBOT_ROOT
                txt = re.sub(r"\$\{INSTANCE_NAME(:-[^}]*)?\}", instance_name, txt)
                port_val = (
                    os.environ.get("ASTRBOT_PORT") or os.environ.get("PORT") or "8000"
                )
                txt = re.sub(r"\$\{PORT(:-[^}]*)?\}", str(port_val), txt)
                txt = re.sub(r"\$\{ASTRBOT_ROOT(:-[^}]*)?\}", str(ASTRBOT_ROOT), txt)
                header = (
                    f"# Generated from config.template by astrbot init for instance: {instance_name}\n"
                    "# This file will be auto-loaded by 'astrbot run'\n\n"
                )
                env_file.write_text(header + txt, encoding="utf-8")
                env_file.chmod(0o644)
                click.echo(f"Created environment file from template: {env_file}")
            except Exception as e:
                click.echo(f"Warning: failed to generate .env from template: {e!s}")
        else:
            click.echo("No config.template found; skipping .env generation")

    if admin_password is not None:
        raise click.ClickException(
            "--admin-password is no longer supported during init. "
            "Run 'astrbot conf admin' after initialization."
        )

    effective_admin_username = (
        admin_username.strip()
        if admin_username
        else str(DEFAULT_CONFIG["dashboard"]["username"])
    )
    if admin_username:
        config = ensure_config_file()
        set_dashboard_credentials(
            config,
            username=effective_admin_username,
            password_hash=None,
        )
        config_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
    click.echo(f"Configured dashboard admin username: {effective_admin_username}")
    click.echo(
        "Dashboard password is not initialized for interactive use. "
        "Run 'astrbot conf admin' before the first login."
    )

    if not backend_only and (
        yes
        or click.confirm(
            "是否需要集成式 WebUI?(个人电脑推荐,服务器不推荐)",
            default=True,
        )
    ):
        await DashboardManager().ensure_installed(astrbot_root)
    else:
        click.echo("你可以使用在线面版(需支持配置后端)来控制｡")


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
    help="Deprecated. Run `astrbot conf admin` after initialization.",
)
@click.option(
    "--root",
    help="ASTRBOT root directory to initialize (overrides ASTRBOT_ROOT env)",
    type=str,
)
def init(
    yes: bool,
    backend_only: bool,
    backup: str | None,
    admin_username: str | None,
    admin_password: str | None,
    root: str | None = None,
) -> None:
    """Initialize AstrBot"""
    click.echo("Initializing AstrBot...")

    if os.environ.get("ASTRBOT_SYSTEMD") == "1":
        yes = True
    from astrbot.core.utils.astrbot_path import astrbot_paths

    astrbot_root = Path(root) if root else astrbot_paths.root
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
