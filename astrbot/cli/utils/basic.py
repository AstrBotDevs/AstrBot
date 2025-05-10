import click
from pathlib import Path
import toml



async def check_dashboard(astrbot_root: Path) -> None:
    """检查是否安装了dashboard"""
    from astrbot.core.utils.io import get_dashboard_version, download_dashboard
    from astrbot.core.config.default import VERSION
    from .version_comparator import VersionComparator


    dashboard_version: str = await get_dashboard_version()
    match dashboard_version:
        case "N/A":
            click.echo("未安装管理面板")
            if click.confirm(
                "是否安装管理面板？",
                default=True,
                abort=True,
            ):
                click.echo("正在安装管理面板...")
                await download_dashboard()
                metadata = toml.load(astrbot_root / ".astrbot") 
                metadata["dashboard_version"] = VERSION
                click.echo("管理面板安装完成")
        case str():
            if VersionComparator.compare_version(VERSION, dashboard_version) <= 0:
                click.echo("管理面板已是最新版本")
                return
            else:
                click.echo(f"管理面板版本: {dashboard_version}")
                await download_dashboard()

