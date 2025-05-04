import os
import sys
from pathlib import Path
import click
from astrbot.core.config.default import VERSION


def _get_astrbot_root(path: str | None) -> Path:
    """获取astrbot根目录"""
    match path:
        case None:
            match ASTRBOT_ROOT := os.getenv("ASTRBOT_ROOT"):
                case None:
                    astrbot_root = Path.cwd() / "data"
                case _:
                    astrbot_root = Path(ASTRBOT_ROOT).resolve()
        case str():
            astrbot_root = Path(path).resolve()

    dot_astrbot = astrbot_root / ".astrbot"
    if not dot_astrbot.exists():
        if click.confirm(
            f"运行前必须先执行初始化！请检查当前目录是否正确，回车以继续: {astrbot_root}",
            default=True,
            abort=True,
        ):
            dot_astrbot.touch()
            astrbot_root.mkdir(parents=True, exist_ok=True)
            click.echo(f"Created {dot_astrbot}")

    return astrbot_root


def _check_astrbot_root(astrbot_root: Path) -> None:
    """验证"""
    dot_astrbot = astrbot_root / ".astrbot"
    if not astrbot_root.exists():
        click.echo(f"AstrBot root directory does not exist: {astrbot_root}")
        click.echo("Please run 'astrbot init' to create the directory.")
        sys.exit(1)
    else:
        click.echo(f"AstrBot root directory exists: {astrbot_root}")
        if not dot_astrbot.exists():
            click.echo(
                "如果你确认这是 Astrbot root directory, 你需要在当前目录下创建一个 .astrbot 文件标记该目录为 AstrBot 的数据目录。"
            )
            if click.confirm(
                f"请检查当前目录是否正确，确认正确请回车: {astrbot_root}",
                default=True,
                abort=True,
            ):
                dot_astrbot.touch()
                click.echo(f"Created {dot_astrbot}")
        else:
            click.echo(f"Welcome back! AstrBot root directory: {astrbot_root}")


async def _check_dashboard(astrbot_root: Path) -> None:
    """检查是否安装了dashboard"""
    try:
        from ..core.utils.io import get_dashboard_version, download_dashboard
    except ImportError:
        from astrbot.core.utils.io import get_dashboard_version, download_dashboard

    try:
        dashboard_version = await get_dashboard_version()
        match dashboard_version:
            case None:
                click.echo("未安装管理面板")
                if click.confirm(
                    "是否安装管理面板？",
                    default=True,
                    abort=True,
                ):
                    click.echo("正在安装管理面板...")
                    await download_dashboard(
                        path="data/dashboard.zip", extract_path=str(astrbot_root)
                    )
                    click.echo("管理面板安装完成")

            case str():
                if dashboard_version == f"v{VERSION}":
                    click.echo("无需更新")
                else:
                    try:
                        version = dashboard_version.split("v")[1]
                        click.echo(f"管理面板版本: {version}")
                        await download_dashboard(
                            path="data/dashboard.zip", extract_path=str(astrbot_root)
                        )
                    except Exception as e:
                        click.echo(f"下载管理面板失败: {e}")
                        return
    except FileNotFoundError:
        click.echo("初始化管理面板目录...")
        try:
            await download_dashboard(
                path=str(astrbot_root / "dashboard.zip"), extract_path=str(astrbot_root)
            )
            click.echo("管理面板初始化完成")
        except Exception as e:
            click.echo(f"下载管理面板失败: {e}")
            return
