
import os
import asyncio
import sys
import warnings
import traceback
import mimetypes
from astrbot.bootstrap import AstrBotBootstrap
from SparkleLogging.utils.core import LogManager
from logging import Formatter

warnings.filterwarnings("ignore")
logo_tmpl = """
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |     
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |     
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|     
                                                                                    
"""
    
def main():
    global logger
    try:
        import botpy, logging
        # delete qqbotpy's logger
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)

        bootstrap = AstrBotBootstrap() 
        asyncio.run(bootstrap.run())
    except KeyboardInterrupt:
        logger.info("AstrBot 已退出。")

    except BaseException as e:
        logger.error(traceback.format_exc())

def check_env():
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 9):
        logger.error("请使用 Python3.9+ 运行本项目。")
        exit()
        
    os.makedirs("data/config", exist_ok=True)
    os.makedirs("temp", exist_ok=True)

    # workaround for issue #181
    mimetypes.add_type("text/javascript", ".js") 
    mimetypes.add_type("text/javascript", ".mjs")
    mimetypes.add_type("application/json", ".json")
    
if __name__ == "__main__":
    check_env()
    
    logger = LogManager.GetLogger(
    log_name='astrbot',
        out_to_console=True,
        custom_formatter=Formatter('[%(asctime)s| %(name)s - %(levelname)s|%(filename)s:%(lineno)d]: %(message)s', datefmt="%H:%M:%S")
    )
    logger.info(logo_tmpl)
    main()
