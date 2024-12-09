
import os
import asyncio
import sys
import mimetypes
import aiohttp
import zipfile
from typing import List
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.config import DB_PATH
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
    dashboard_release_url = "https://api.github.com/repos/Soulter/AstrBot-Dashboard/releases/latest"
    logger.info("正在获取管理面板最新版本信息，请稍等片刻...")
    async with aiohttp.ClientSession() as session:
        async with session.get(dashboard_release_url) as resp:
            if resp.status != 200:
                logger.error(f"获取管理面板最新版本信息失败: {resp.status}")
                return
            release_info = await resp.json()
            download_url = release_info["assets"][0]["browser_download_url"]

    mirrors = ["https://ghp.ci/"]
    for i in range(len(mirrors)):
        mirrors[i] += download_url
    mirrors.append(download_url)
    
    ok = False
    for mirror in mirrors:
        logger.info(f"正在从 GitHub 下载管理面板文件: {mirror}")
        async with aiohttp.ClientSession() as session:
            async with session.get(mirror) as resp:
                if resp.status != 200:
                    logger.error(f"下载管理面板文件失败: {resp.status}")
                    continue
                with open("data/dashboard.zip", "wb") as f:
                    f.write(await resp.read())
                logger.info("管理面板文件下载完成。")
                ok = True
                break
                
    if not ok:
        logger.fatal(f"下载管理面板文件失败，请手动前往 {download_url} 下载，并将其中的 dist 文件夹解压到 data 目录下。")
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
    
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    asyncio.run(core_lifecycle.initialize())
    
    dashboard_lifecycle = AstrBotDashBoardLifecycle(db)
    asyncio.run(dashboard_lifecycle.start(core_lifecycle))