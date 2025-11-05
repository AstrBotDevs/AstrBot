import argparse
import asyncio
import mimetypes
import os
import sys

from astrbot.base import LOGO, AstrbotPaths
from astrbot.core import LogBroker, LogManager, db_helper, logger
from astrbot.core.config.default import VERSION
from astrbot.core.initial_loader import InitialLoader
from astrbot.core.utils.io import download_dashboard, get_dashboard_version


def check_env():
    if sys.version_info.major != 3 or sys.version_info.minor < 10:
        logger.error("请使用 Python3.10+ 运行本项目。")
        exit()

    # os.makedirs("data/config", exist_ok=True)
    # os.makedirs("data/plugins", exist_ok=True)
    # os.makedirs("data/temp", exist_ok=True)

    # 针对问题 #181 的临时解决方案
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

    data_dist_path = str(AstrbotPaths.astrbot_root / "dist")
    if os.path.exists(data_dist_path):
        v = await get_dashboard_version()
        if v is not None:
            # 存在文件
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


def main():
    parser = argparse.ArgumentParser(description="AstrBot")
    parser.add_argument(
        "--webui-dir",
        type=str,
        help="指定 WebUI 静态文件目录路径",
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
    logger.info(LOGO)

    core_lifecycle = InitialLoader(db, log_broker)
    core_lifecycle.webui_dir = webui_dir
    asyncio.run(core_lifecycle.start())


if __name__ == "__main__":
    main()
