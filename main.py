import argparse
import asyncio
import mimetypes
import os
import sys
from pathlib import Path

from astrbot.core import LogBroker, LogManager, db_helper, logger
from astrbot.core.config.default import VERSION
from astrbot.core.initial_loader import InitialLoader
from astrbot.core.utils.astrbot_path import get_astrbot_data_path
from astrbot.core.utils.io import download_dashboard, get_dashboard_version

# add parent path to sys.path
sys.path.append(Path(__file__).parent.as_posix())

logo_tmpl = r"""
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|

"""


def check_env():
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 10):
        logger.error("请使用 Python3.10+ 运行本项目。")
        exit()

    os.makedirs("data/config", exist_ok=True)
    os.makedirs("data/plugins", exist_ok=True)
    os.makedirs("data/temp", exist_ok=True)

    # workaround for issue #181
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("application/json", ".json")


async def check_dashboard_files(webui_dir: str | None = None):
    """下载管理面板文件"""
    # 指定webui目录
    if webui_dir:
        if os.path.exists(webui_dir):
            logger.info(f"使用指定的 WebUI 目录: {webui_dir}")
            return webui_dir
        logger.warning(f"指定的 WebUI 目录 {webui_dir} 不存在，将使用默认逻辑。")

    data_dist_path = os.path.join(get_astrbot_data_path(), "dist")
    if os.path.exists(data_dist_path):
        v = await get_dashboard_version()
        if v is not None:
            # has file
            if v == f"v{VERSION}":
                logger.info("WebUI 版本已是最新。")
            else:
                logger.warning(
                    f"检测到 WebUI 版本 ({v}) 与当前 AstrBot 版本 (v{VERSION}) 不符。",
                )
        return data_dist_path

    logger.info(
        "开始下载管理面板文件...高峰期（晚上）可能导致较慢的速度。如多次下载失败，请前往 https://github.com/AstrBotDevs/AstrBot/releases/latest 下载 dist.zip，并将其中的 dist 文件夹解压至 data 目录下。",
    )

    try:
        await download_dashboard(version=f"v{VERSION}", latest=False)
    except Exception as e:
        logger.critical(f"下载管理面板文件失败: {e}。")
        return None

    logger.info("管理面板下载完成。")
    return data_dist_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AstrBot")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help="指定 WebUI 静态文件目录路径",
        default=None,
    )
    args = parser.parse_args()

    check_env()

    # start log broker
    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)

    # check dashboard files
    webui_dir = asyncio.run(check_dashboard_files(args.webui_dir))

    db = db_helper

    # print logo
    logger.info(logo_tmpl)

    core_lifecycle = InitialLoader(db, log_broker)
    core_lifecycle.webui_dir = webui_dir
    asyncio.run(core_lifecycle.start())
