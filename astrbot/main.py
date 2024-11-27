
import os
import asyncio
import sys
import mimetypes

from core.core_lifecycle import AstrBotCoreLifecycle
from core.db.sqlite import SQLiteDatabase
from core.config import DB_PATH
from dashboard import AstrBotDashBoardLifecycle

from core import logger, LogManager, LogBroker

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

if __name__ == "__main__":
    check_env()
    
    # start log broker
    log_broker = LogBroker()
    LogManager.set_queue_handler(logger, log_broker)
    
    # start db
    db = SQLiteDatabase(DB_PATH)
    
    # print logo
    logger.info(logo_tmpl)
    
    dashboard_lifecycle = AstrBotDashBoardLifecycle(db)
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    
    asyncio.run(dashboard_lifecycle.start(core_lifecycle))