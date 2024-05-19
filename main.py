
import os
import sys
import warnings
import traceback
import threading
from SparkleLogging.utils.core import LogManager
from logging import Formatter, Logger

warnings.filterwarnings("ignore")
abs_path = os.path.dirname(os.path.realpath(sys.argv[0])) + '/'

logger: Logger = None

logo_tmpl = """
     ___           _______.___________..______      .______     ______   .___________.
    /   \         /       |           ||   _  \     |   _  \   /  __  \  |           |
   /  ^  \       |   (----`---|  |----`|  |_)  |    |  |_)  | |  |  |  | `---|  |----`
  /  /_\  \       \   \       |  |     |      /     |   _  <  |  |  |  |     |  |     
 /  _____  \  .----)   |      |  |     |  |\  \----.|  |_)  | |  `--'  |     |  |     
/__/     \__\ |_______/       |__|     | _| `._____||______/   \______/      |__|     
                                                                                    
"""

def make_necessary_dirs():
    os.makedirs("data/config", exist_ok=True)
    os.makedirs("temp", exist_ok=True)

def main():
    logger = LogManager.GetLogger(
        log_name='astrbot-core',
        out_to_console=True,
        # HTTPpost_url='http://localhost:6185/api/log',
        # http_mode = True,
        custom_formatter=Formatter('[%(asctime)s| %(name)s - %(levelname)s|%(filename)s:%(lineno)d]: %(message)s', datefmt="%H:%M:%S")
    )
    logger.info(logo_tmpl)
    # config.yaml 配置文件加载和环境确认
    try:
        import botpy, logging, yaml
        import astrbot.core as bot_core
        # delete qqbotpy's logger
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        ymlfile = open(abs_path+"configs/config.yaml", 'r', encoding='utf-8')
        cfg = yaml.safe_load(ymlfile)
    except ImportError as import_error:
        logger.error(import_error)
        logger.error("检测到一些依赖库没有安装。由于兼容性问题，AstrBot 此版本将不会自动为您安装依赖库。请您先自行安装，然后重试。")
        logger.info("如何安装？如果：")
        logger.info("- Windows 启动器部署且使用启动器下载了 Python的：在 launcher.exe 所在目录下的地址框输入 powershell，然后执行 .\python\python.exe -m pip install .\AstrBot\requirements.txt")
        logger.info("- Windows 启动器部署且使用自己之前下载的 Python的：在 launcher.exe 所在目录下的地址框输入 powershell，然后执行 python -m pip install .\AstrBot\requirements.txt")
        logger.info("- 自行 clone 源码部署的：python -m pip install -r requirements.txt")
        logger.info("- 如果还不会，加群 322154837 ")
        input("按任意键退出。")
        exit()
    except FileNotFoundError as file_not_found:
        logger.error(file_not_found)
        input("配置文件不存在，请检查是否已经下载配置文件。")
        exit()
    except BaseException as e:
        logger.error(traceback.format_exc())
        input("未知错误。")
        exit()

    # 设置代理
    if 'http_proxy' in cfg and cfg['http_proxy'] != '':
        os.environ['HTTP_PROXY'] = cfg['http_proxy']
    if 'https_proxy' in cfg and cfg['https_proxy'] != '':
        os.environ['HTTPS_PROXY'] = cfg['https_proxy']
    os.environ['NO_PROXY'] = 'https://api.sgroup.qq.com'

    make_necessary_dirs()

    # 启动主程序（cores/qqbot/core.py）
    bot_core.init(cfg)


def check_env():
    if not (sys.version_info.major == 3 and sys.version_info.minor >= 9):
        logger.error("请使用 Python3.9+ 运行本项目。按任意键退出。")
        input("")
        exit()

if __name__ == "__main__":
    check_env()
    t = threading.Thread(target=main, daemon=True)
    t.start()
    try:
        t.join()
    except KeyboardInterrupt as e:
        logger.info("退出 AstrBot。")
        exit()
