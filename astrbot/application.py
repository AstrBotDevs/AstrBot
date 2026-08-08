"""The single application startup path shared by every runtime entry point."""

from __future__ import annotations

import mimetypes
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from astrbot import logger
from astrbot.core.config.default import VERSION
from astrbot.core.initial_loader import InitialLoader
from astrbot.core.log import LogBroker, LogManager
from astrbot.core.runtime_services import create_runtime_services
from astrbot.core.utils.astrbot_path import (
    get_astrbot_config_path,
    get_astrbot_data_path,
    get_astrbot_knowledge_base_path,
    get_astrbot_plugin_path,
    get_astrbot_root,
    get_astrbot_site_packages_path,
    get_astrbot_temp_path,
)
from astrbot.core.utils.io import (
    get_bundled_dashboard_dist_path,
    get_dashboard_dist_version,
    get_repo_dashboard_dist_path,
    is_dashboard_dist_compatible,
    is_dashboard_version_compatible,
    remove_dir,
    should_use_bundled_dashboard_dist,
)
from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime


@dataclass(frozen=True, slots=True)
class ApplicationOptions:
    """Options consumed by the process-wide application runner."""

    webui_dir: str | None = None


_LOGO = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|

"""


def prepare_runtime_environment() -> None:
    """Prepare runtime paths after bootstrap and before service construction."""
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 14):
        logger.error("请使用 Python3.14+ 运行本项目。")
        raise SystemExit(1)

    astrbot_root = get_astrbot_root()
    if astrbot_root not in sys.path:
        sys.path.insert(0, astrbot_root)

    site_packages_path = get_astrbot_site_packages_path()
    if not is_packaged_desktop_runtime() and site_packages_path not in sys.path:
        sys.path.append(site_packages_path)

    for path in (
        get_astrbot_config_path(),
        get_astrbot_plugin_path(),
        get_astrbot_temp_path(),
        get_astrbot_knowledge_base_path(),
        site_packages_path,
    ):
        os.makedirs(path, exist_ok=True)

    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("application/json", ".json")


async def resolve_dashboard_assets(webui_dir: str | None = None) -> str | None:
    """Resolve and repair the compatible Dashboard asset directory.

    Args:
        webui_dir: An explicit WebUI static directory selected by the caller.

    Returns:
        The directory to serve, or ``None`` when no compatible build exists.
    """
    if webui_dir:
        explicit_dist = Path(webui_dir)
        if explicit_dist.exists():
            explicit_version = get_dashboard_dist_version(explicit_dist)
            if not is_dashboard_version_compatible(explicit_version, VERSION):
                logger.warning(
                    "Serving the explicitly configured WebUI directory even though "
                    "it does not declare a version matching core: %s, expected v%s "
                    "(%s). Some Dashboard features may not work until matching "
                    "assets are available.",
                    explicit_version or "unknown",
                    VERSION,
                    explicit_dist,
                )
            logger.info("Using WebUI directory: %s", webui_dir)
            return webui_dir
        logger.warning("WebUI directory not found: %s. Using default.", webui_dir)

    data_dist_path = Path(get_astrbot_data_path()) / "dist"
    repo_dist = get_repo_dashboard_dist_path()
    bundled_dist = get_bundled_dashboard_dist_path()

    if is_dashboard_dist_compatible(repo_dist, VERSION):
        logger.info(
            "Using source-tree WebUI %s.", get_dashboard_dist_version(repo_dist)
        )
        return str(repo_dist)

    if data_dist_path.exists():
        version = get_dashboard_dist_version(data_dist_path)
        if is_dashboard_dist_compatible(data_dist_path, VERSION):
            logger.info("WebUI is up to date.")
            return str(data_dist_path)

        if should_use_bundled_dashboard_dist(data_dist_path, VERSION):
            logger.info(
                "Replacing data/dist with bundled WebUI because its version does not match core version v%s.",
                VERSION,
            )
            try:
                remove_dir(str(data_dist_path))
                shutil.copytree(bundled_dist, data_dist_path)
                return str(data_dist_path)
            except Exception as exc:
                logger.warning(
                    "Failed to replace data/dist with bundled WebUI: %s. Using bundled WebUI directly.",
                    exc,
                )
                return str(bundled_dist)

        logger.warning(
            "Ignoring incompatible data/dist WebUI %s; core requires v%s.",
            version or "unknown",
            VERSION,
        )

    if is_dashboard_dist_compatible(bundled_dist, VERSION):
        logger.info("Using bundled WebUI %s.", get_dashboard_dist_version(bundled_dist))
        return str(bundled_dist)

    logger.critical(
        "No compatible WebUI build is available. Build dashboard/dist from this "
        "checkout and run scripts/sync_dashboard_dist.py, or pass --webui-dir.",
    )
    return None


async def run_application(options: ApplicationOptions) -> None:
    """Create and supervise one complete AstrBot runtime instance."""
    prepare_runtime_environment()
    webui_dir = await resolve_dashboard_assets(options.webui_dir)
    if webui_dir is None:
        logger.warning(
            "管理面板文件检查失败，WebUI 功能将不可用。"
            "请构建当前 checkout 的 dashboard/dist，运行 "
            "scripts/sync_dashboard_dist.py，或手动指定 --webui-dir。",
        )

    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    services = create_runtime_services()
    logger.info(_LOGO)
    loader = InitialLoader(services, log_broker, webui_dir=webui_dir)
    await loader.start()
