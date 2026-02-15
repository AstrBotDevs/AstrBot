from pathlib import Path

import click


def check_astrbot_root(path: str | Path) -> bool:
    """检查路径是否为 AstrBot 根目录"""
    if not isinstance(path, Path):
        path = Path(path)
    if not path.exists() or not path.is_dir():
        return False
    if not (path / ".astrbot").exists():
        return False
    return True


def get_astrbot_root() -> Path:
    """获取 AstrBot 根目录路径

    查找顺序：
    1. 环境变量 ASTRBOT_ROOT
    2. 通过包安装路径定位（editable install / 源码目录）
    3. 从当前目录向上查找包含 .astrbot 标记的目录
    4. 回退到当前工作目录
    """
    # 1. 环境变量
    import os

    env_root = os.environ.get("ASTRBOT_ROOT")
    if env_root:
        p = Path(env_root)
        if check_astrbot_root(p):
            return p

    # 2. 通过包安装路径定位（editable install 场景）
    # __file__ 在 astrbot/cli/utils/basic.py，向上 4 级到达项目根目录
    source_root = Path(__file__).resolve().parent.parent.parent.parent
    if check_astrbot_root(source_root):
        return source_root

    # 3. 向上查找 .astrbot 标记
    current = Path.cwd()
    for parent in [current, *current.parents]:
        if (parent / ".astrbot").exists():
            return parent

    # 4. 回退到当前目录
    return current


async def check_dashboard(astrbot_root: Path) -> None:
    """检查是否安装了dashboard"""
    from astrbot.core.config.default import VERSION
    from astrbot.core.utils.io import download_dashboard, get_dashboard_version

    from .version_comparator import VersionComparator

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
                        path="data/dashboard.zip",
                        extract_path=str(astrbot_root),
                        version=f"v{VERSION}",
                        latest=False,
                    )
                    click.echo("管理面板安装完成")

            case str():
                if VersionComparator.compare_version(VERSION, dashboard_version) <= 0:
                    click.echo("管理面板已是最新版本")
                    return
                try:
                    version = dashboard_version.split("v")[1]
                    click.echo(f"管理面板版本: {version}")
                    await download_dashboard(
                        path="data/dashboard.zip",
                        extract_path=str(astrbot_root),
                        version=f"v{VERSION}",
                        latest=False,
                    )
                except Exception as e:
                    click.echo(f"下载管理面板失败: {e}")
                    return
    except FileNotFoundError:
        click.echo("初始化管理面板目录...")
        try:
            await download_dashboard(
                path=str(astrbot_root / "dashboard.zip"),
                extract_path=str(astrbot_root),
                version=f"v{VERSION}",
                latest=False,
            )
            click.echo("管理面板初始化完成")
        except Exception as e:
            click.echo(f"下载管理面板失败: {e}")
            return
