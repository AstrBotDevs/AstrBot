import os
import asyncio
import sys
import mimetypes
from astrbot.core.initial_loader import InitialLoader
from astrbot.core import db_helper
from astrbot.core import logger, LogManager, LogBroker
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import download_dashboard, get_dashboard_version

# add parent path to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


async def check_dashboard_files():
    """下载管理面板文件"""

    dashboard_dist_path = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard", "dist"))
    if os.path.exists(dashboard_dist_path):
        logger.info("检测到本地构建的 dashboard/dist 目录")
        # 等待用户输入
        while True:
            user_input = input("是否使用本地构建的 dashboard/dist 目录？(Y/N): ").strip().lower()
            if user_input in ['y', 'yes', 'a', '是', '']:
                logger.info("将直接使用本地构建的 dashboard/dist 目录作为前端面板")
                return
            elif user_input in ['n', 'no', '否']:
                logger.info("忽略本地构建的 dashboard/dist 目录，使用默认逻辑。如果你希望一直使用 data/dist 目录，请将 dashboard/dist 目录删除。")
                break
            else:
                logger.info("请输入 Y(是) 或 N(否)")
     
    v = await get_dashboard_version()
    if v is not None:
        # has file
        if v == f"v{VERSION}":
            logger.info("WebUI 版本已是最新。")
        else:
            logger.warning(
                f"检测到 WebUI 版本 ({v}) 与当前 AstrBot 版本 (v{VERSION}) 不符。"
            )
        return

    logger.info(
        "开始下载管理面板文件...高峰期（晚上）可能导致较慢的速度。如多次下载失败，请前往 https://github.com/Soulter/AstrBot/releases/latest 下载 dist.zip，并将其中的 dist 文件夹解压至 data 目录下。"
    )

    try:
        await download_dashboard(version=f"v{VERSION}", latest=False)
    except Exception as e:
        logger.critical(f"下载管理面板文件失败: {e}。")
        return

    logger.info("管理面板下载完成。")


if __name__ == "__main__":
    check_env()

    # start log broker
    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)

    # check dashboard files
    asyncio.run(check_dashboard_files())

    db = db_helper

    # print logo
    logger.info(logo_tmpl)

    core_lifecycle = InitialLoader(db, log_broker)
    asyncio.run(core_lifecycle.start())
