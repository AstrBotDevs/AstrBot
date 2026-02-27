from astrbot.core.lang import t
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
    """获取Astrbot根目录路径"""
    return Path.cwd()


async def check_dashboard(astrbot_root: Path) -> None:
    """检查是否安装了dashboard"""
    from astrbot.core.config.default import VERSION
    from astrbot.core.utils.io import download_dashboard, get_dashboard_version

    from .version_comparator import VersionComparator

    try:
        dashboard_version = await get_dashboard_version()
        match dashboard_version:
            case None:
                click.echo(t("msg-f4e0fd7b"))
                if click.confirm(
                    "是否安装管理面板？",
                    default=True,
                    abort=True,
                ):
                    click.echo(t("msg-2d090cc3"))
                    await download_dashboard(
                        path="data/dashboard.zip",
                        extract_path=str(astrbot_root),
                        version=f"v{VERSION}",
                        latest=False,
                    )
                    click.echo(t("msg-2eeb67e0"))

            case str():
                if VersionComparator.compare_version(VERSION, dashboard_version) <= 0:
                    click.echo(t("msg-9c727dca"))
                    return
                try:
                    version = dashboard_version.split("v")[1]
                    click.echo(t("msg-11b49913", version=version))
                    await download_dashboard(
                        path="data/dashboard.zip",
                        extract_path=str(astrbot_root),
                        version=f"v{VERSION}",
                        latest=False,
                    )
                except Exception as e:
                    click.echo(t("msg-f0b6145e", e=e))
                    return
    except FileNotFoundError:
        click.echo(t("msg-9504d173"))
        try:
            await download_dashboard(
                path=str(astrbot_root / "dashboard.zip"),
                extract_path=str(astrbot_root),
                version=f"v{VERSION}",
                latest=False,
            )
            click.echo(t("msg-699e2509"))
        except Exception as e:
            click.echo(t("msg-f0b6145e", e=e))
            return
