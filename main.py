import os
import asyncio
import sys
import mimetypes
from astrbot.dashboard import AstrBotDashBoardLifecycle
from astrbot.core import db_helper
from astrbot.core import logger, LogManager, LogBroker
from astrbot.core.config.default import VERSION
from astrbot.core.utils.io import download_dashboard

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
    '''下载管理面板文件'''
    if os.path.exists("data/dist"):
        if os.path.exists("data/dist/assets/version"):
            with open("data/dist/assets/version", "r") as f:
                v = f.read().strip()
                if v != f"v{VERSION}":
                    logger.warning("检测到管理面板有更新。可以使用 /dashboard update 命令更新。")
                else:
                    logger.info("管理面板文件已是最新。")
        return
    
    logger.info("开始下载管理面板文件...")
    
    try:
        await download_dashboard()
    except Exception as e:
        logger.critical(f"下载管理面板文件失败: {e}")
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
    
    dashboard_lifecycle = AstrBotDashBoardLifecycle(db, log_broker)
    asyncio.run(dashboard_lifecycle.start())