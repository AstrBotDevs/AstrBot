import argparse
import asyncio
import mimetypes
import os
import sys
from pathlib import Path

import runtime_bootstrap

runtime_bootstrap.initialize_runtime_bootstrap()

from astrbot.core import LogBroker, LogManager, db_helper, logger, t  # noqa: E402
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
    get_dashboard_version,
)

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
        logger.error(t("main-python-version-error"))
        exit()

    astrbot_root = get_astrbot_root()
    if astrbot_root not in sys.path:
        sys.path.insert(0, astrbot_root)

    site_packages_path = get_astrbot_site_packages_path()
    if site_packages_path not in sys.path:
        sys.path.insert(0, site_packages_path)

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
    """下载管理面板文件"""
    # 指定webui目录
    if webui_dir:
        if os.path.exists(webui_dir):
            logger.info(t("main-use-specified-webui", webui_dir=webui_dir))
            return webui_dir
        logger.warning(t("main-webui-not-found", webui_dir=webui_dir))

    data_dist_path = os.path.join(get_astrbot_data_path(), "dist")
    if os.path.exists(data_dist_path):
        v = await get_dashboard_version()
        if v is not None:
            # 存在文件
            if v == f"v{VERSION}":
                logger.info(t("main-webui-latest"))
            else:
                logger.warning(
                    t("main-webui-version-mismatch", v=v, version=VERSION),
                )
        return data_dist_path

    logger.info(t("main-downloading-dashboard"))

    try:
        await download_dashboard(version=f"v{VERSION}", latest=False)
    except Exception as e:
        logger.critical(t("main-download-dashboard-failed", e=e))
        return None

    logger.info(t("main-download-dashboard-success"))
    return data_dist_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstrBot")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help=t("main-argparse-webui-dir-help"),
        default=None,
    )
    args = parser.parse_args()

    check_env()

    # 启动日志代理
    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)

    # 检查仪表板文件
    webui_dir = asyncio.run(check_dashboard_files(args.webui_dir))

    db = db_helper

    # 打印 logo
    logger.info(logo_tmpl)

    core_lifecycle = InitialLoader(db, log_broker)
    core_lifecycle.webui_dir = webui_dir
    asyncio.run(core_lifecycle.start())
