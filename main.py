import argparse
import asyncio
import mimetypes
import os
import shutil
import sys
from pathlib import Path

import runtime_bootstrap

runtime_bootstrap.initialize_runtime_bootstrap()

DASHBOARD_RESET_PASSWORD_ENV = "ASTRBOT_RESET_DASHBOARD_PASSWORD"


def _apply_startup_env_flags(argv: list[str]) -> None:
    """Apply startup flags that must take effect before core imports.

    Args:
        argv: Command-line arguments excluding the executable name.
    """

    if "-h" in argv or "--help" in argv:
        return

    startup_parser = argparse.ArgumentParser(add_help=False)
    startup_parser.add_argument("--reset-password", action="store_true")
    startup_args, _ = startup_parser.parse_known_args(argv)
    if startup_args.reset_password:
        os.environ[DASHBOARD_RESET_PASSWORD_ENV] = "1"


_apply_startup_env_flags(sys.argv[1:])

from astrbot.core import LogBroker, LogManager, db_helper, logger  # noqa: E402
from astrbot.core.config.default import VERSION  # noqa: E402
from astrbot.core.initial_loader import InitialLoader  # noqa: E402
from astrbot.core.utils.astrbot_path import (  # noqa: E402
    get_astrbot_config_path,
    get_astrbot_data_path,
    get_astrbot_knowledge_base_path,
    get_astrbot_plugin_path,
    get_astrbot_root,
    get_astrbot_site_packages_path,
    get_astrbot_temp_path,
)
from astrbot.core.utils.io import (  # noqa: E402
    download_dashboard,
    get_bundled_dashboard_dist_path,
    get_dashboard_dist_version,
    is_dashboard_dist_compatible,
    is_dashboard_version_compatible,
    remove_dir,
    should_use_bundled_dashboard_dist,
)
from astrbot.core.utils.runtime_env import is_packaged_desktop_runtime  # noqa: E402

# 将父目录添加到 sys.path
sys.path.append(Path(__file__).parent.as_posix())

logo_tmpl = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|

"""


def check_env() -> None:
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 10):
        logger.error("请使用 Python3.10+ 运行本项目。")
        exit()

    astrbot_root = get_astrbot_root()
    if astrbot_root not in sys.path:
        sys.path.insert(0, astrbot_root)

    site_packages_path = get_astrbot_site_packages_path()
    if not is_packaged_desktop_runtime() and site_packages_path not in sys.path:
        sys.path.append(site_packages_path)

    os.makedirs(get_astrbot_config_path(), exist_ok=True)
    os.makedirs(get_astrbot_plugin_path(), exist_ok=True)
    os.makedirs(get_astrbot_temp_path(), exist_ok=True)
    os.makedirs(get_astrbot_knowledge_base_path(), exist_ok=True)
    os.makedirs(site_packages_path, exist_ok=True)

    # 针对问题 #181 的临时解决方案
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("application/json", ".json")


async def check_dashboard_files(webui_dir: str | None = None):
    """Resolve and repair dashboard static files for startup.

    Args:
        webui_dir: Optional explicit WebUI directory path from CLI.

    Returns:
        The directory path to serve, or None when no usable WebUI can be prepared.
    """

    # 指定webui目录
    if webui_dir:
        if os.path.exists(webui_dir):
            logger.info("Using WebUI directory: %s", webui_dir)
            return webui_dir
        logger.warning("WebUI directory not found: %s. Using default.", webui_dir)

    data_dist_path = Path(get_astrbot_data_path()) / "dist"
    bundled_dist = get_bundled_dashboard_dist_path()
    if data_dist_path.exists():
        v = get_dashboard_dist_version(data_dist_path)
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
            except Exception as e:
                logger.warning(
                    "Failed to replace data/dist with bundled WebUI: %s. Using bundled WebUI directly.",
                    e,
                )
                return str(bundled_dist)

        if is_dashboard_version_compatible(v, VERSION):
            logger.warning(
                "WebUI files are incomplete for v%s. Re-downloading WebUI.",
                VERSION,
            )
        elif v is not None:
            logger.warning(
                "WebUI version mismatch: %s, expected v%s. Re-downloading WebUI.",
                v,
                VERSION,
            )
        else:
            logger.warning(
                "WebUI version file is missing. Re-downloading WebUI v%s.",
                VERSION,
            )

        try:
            await download_dashboard(
                version=f"v{VERSION}",
                latest=False,
                allow_insecure_ssl_fallback=False,
            )
        except Exception as e:
            logger.critical(f"下载管理面板文件失败: {e}。")
            if (data_dist_path / "index.html").is_file():
                logger.warning(
                    "Falling back to existing data/dist WebUI %s even though core expects v%s. "
                    "Some dashboard features may not work until the matching WebUI is available.",
                    v or "unknown",
                    VERSION,
                )
                return str(data_dist_path)
            return None
        logger.info("管理面板下载完成。")
        return str(data_dist_path)

    if is_dashboard_dist_compatible(bundled_dist, VERSION):
        logger.info(
            "Using bundled WebUI v%s.", get_dashboard_dist_version(bundled_dist)
        )
        return str(bundled_dist)

    logger.info(
        "Downloading WebUI. If it fails, download dist.zip from https://github.com/AstrBotDevs/AstrBot/releases/latest and extract dist to data/.",
    )

    try:
        await download_dashboard(
            version=f"v{VERSION}",
            latest=False,
            allow_insecure_ssl_fallback=False,
        )
    except Exception as e:
        logger.critical(f"下载管理面板文件失败: {e}。")
        return None

    logger.info("管理面板下载完成。")
    return str(data_dist_path)


async def main_async(webui_dir_arg: str | None) -> None:
    """主异步入口"""
    # 检查仪表板文件
    webui_dir = await check_dashboard_files(webui_dir_arg)
    if webui_dir is None:
        logger.warning(
            "管理面板文件检查失败，WebUI 功能将不可用。"
            "请检查网络连接或手动指定 --webui-dir 参数。"
        )

    db = db_helper

    # 打印 logo
    logger.info(logo_tmpl)

    core_lifecycle = InitialLoader(db, log_broker)
    core_lifecycle.webui_dir = webui_dir
    await core_lifecycle.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstrBot")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help="Specify the directory path for WebUI static files",
        default=None,
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help=(
            "Reset the dashboard initial password on startup and print it in "
            "startup logs"
        ),
    )
    args = parser.parse_args()

    check_env()

    # 启动日志代理
    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)

    # 只使用一次 asyncio.run()
    asyncio.run(main_async(args.webui_dir))
