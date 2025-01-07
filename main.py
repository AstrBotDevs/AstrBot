import os
import asyncio
import sys
import mimetypes
import aiohttp
import zipfile
from astrbot.dashboard import AstrBotDashBoardLifecycle
from astrbot.core import db_helper
from astrbot.core import logger, LogManager, LogBroker

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
        return
    dashboard_release_url = "https://astrbot-registry.soulter.top/download/astrbot-dashboard/latest/dist.zip"
    logger.info("开始下载管理面板文件...")
    ok = False
    async with aiohttp.ClientSession() as session:
        async with session.get(dashboard_release_url) as resp:
            if resp.status != 200:
                logger.error(f"下载管理面板文件失败: {resp.status}")
            else:
                with open("data/dashboard.zip", "wb") as f:
                    f.write(await resp.read())
                logger.info("管理面板文件下载完成。")
                ok = True
                
    if not ok:
        logger.critical("下载管理面板文件失败")
        return
    
    # unzip
    with zipfile.ZipFile("data/dashboard.zip", "r") as z:
        z.extractall("data")
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