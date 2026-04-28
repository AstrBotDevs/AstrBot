import asyncio
import json
import os
import re
from pathlib import Path

import click
from filelock import FileLock, Timeout

from astrbot.cli.utils import DashboardManager
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.astrbot_path import get_astrbot_root


async def initialize_astrbot(
    astrbot_root: Path,
    *,
    yes: bool,
    backend_only: bool,
    admin_username: str | None,
    admin_password: str | None,
) -> None:
    """Execute AstrBot initialization logic"""
    from astrbot.cli.banner import print_logo

    click.echo("=" * 60)
    click.echo("AstrBot 初始化向导")
    click.echo("=" * 60)
    print_logo()
    click.echo()

    dot_astrbot = astrbot_root / ".astrbot"
    if not dot_astrbot.exists():
        if yes or click.confirm(
            f"确定要将 AstrBot 安装到以下目录吗？\n  {astrbot_root}",
            default=True,
            abort=True,
        ):
            dot_astrbot.touch()
            click.echo(f"[OK] 已创建: {dot_astrbot}")

    paths = {
        "data": astrbot_root / "data",
        "config": astrbot_root / "data" / "config",
        "plugins": astrbot_root / "data" / "plugins",
        "temp": astrbot_root / "data" / "temp",
        "skills": astrbot_root / "data" / "skills",
    }

    for name, path in paths.items():
        path.mkdir(parents=True, exist_ok=True)
        status = "Created" if not path.exists() else "Exists"
        click.echo(f"  [{status}] {name.title()}: {path}")

    config_path = astrbot_root / "data" / "cmd_config.json"
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8-sig",
        )
        click.echo(f"[OK] 配置文件已创建: {config_path}")

    ASTRBOT_ROOT = astrbot_root
    env_file = ASTRBOT_ROOT / ".env"
    if not env_file.exists():
        tmpl_candidates = [
            Path("/opt/astrbot/config.template"),
            Path.cwd() / "config.template",
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
                instance_name = astrbot_root.name or "astrbot"
                txt = re.sub("\\$\\{INSTANCE_NAME(:-[^}]*)?\\}", instance_name, txt)
                port_val = (
                    os.environ.get("ASTRBOT_PORT") or os.environ.get("PORT") or "8000"
                )
                txt = re.sub("\\$\\{PORT(:-[^}]*)?\\}", str(port_val), txt)
                txt = re.sub("\\$\\{ASTRBOT_ROOT(:-[^}]*)?\\}", str(ASTRBOT_ROOT), txt)
                header = f"# Generated from config.template by astrbot init for instance: {instance_name}\n# This file will be auto-loaded by 'astrbot run'\n\n"
                env_file.write_text(header + txt, encoding="utf-8")
                env_file.chmod(420)
                click.echo(f"[OK] 环境变量文件已创建: {env_file}")
            except Exception as e:
                click.echo(f"[警告] 无法从模板生成 .env 文件: {e!s}")
        else:
            click.echo("[提示] 未找到 config.template 文件，跳过 .env 生成")

    if admin_password is not None:
        click.echo(
            "[警告] --admin-password 在初始化中不再支持。启动后请使用 'astrbot conf admin' 设置密码。"
        )

    if not backend_only and (
        yes
        or click.confirm(
            "是否需要集成式 WebUI？（个人电脑推荐，服务器推荐使用后端模式）",
            default=True,
        )
    ):
        await DashboardManager().ensure_installed(astrbot_root)
    else:
        click.echo()
        click.echo("[提示] 你选择了后端模式，可以使用以下方式管理 AstrBot：")
        click.echo("  - 使用在线 Dashboard: 在浏览器中访问远程服务器的 WebUI")
        click.echo("  - 使用 CLI 命令: astrbot conf / astrbot plug 等")
        click.echo()
        click.echo("!" * 60)
        click.echo("安全提示：")
        click.echo("  HTTPS 前端只能安全连接 localhost 的 HTTP 后端")
        click.echo("  不支持远程 + HTTP 后端（不安全）")
        click.echo("  如需远程访问，请使用 HTTPS 后端或通过反向代理")
        click.echo("!" * 60)
        click.echo()


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
    help="Deprecated. Set password after initialization.",
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

    astrbot_root = Path(root) if root else Path(get_astrbot_root())
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
                ),
            )
            if backup:
                click.echo(f"Backup restore option specified: {backup}")
                click.echo(
                    "Backup restoration requires the backup module. "
                    "Please restore manually or use the dashboard."
                )
            click.echo()
            click.echo("=" * 60)
            click.echo("初始化完成！")
            click.echo("=" * 60)
            click.echo()
            click.echo("启动 AstrBot：")
            click.echo("  完整模式（含 Dashboard）: astrbot run")
            click.echo("  仅后端模式:           astrbot run --backend-only")
            click.echo()
            click.echo("首次使用前请先设置管理员密码：")
            click.echo("  astrbot conf admin")
            click.echo()
    except Timeout:
        raise click.ClickException(
            "Cannot acquire lock file. Please check if another instance is running",
        )
    except Exception as e:
        raise click.ClickException(f"Initialization failed: {e!s}")
