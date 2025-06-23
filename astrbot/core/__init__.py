import os
import asyncio
from .log import LogManager, LogBroker  # noqa
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.config.default import DB_PATH
from astrbot.core.config import AstrBotConfig
from astrbot.core.file_token_service import FileTokenService
from .utils.astrbot_path import get_astrbot_data_path

# 初始化数据存储文件夹
os.makedirs(get_astrbot_data_path(), exist_ok=True)

DEMO_MODE = os.getenv("DEMO_MODE", False)

astrbot_config = AstrBotConfig()
t2i_base_url = astrbot_config.get("t2i_endpoint", "https://t2i.soulter.top/text2img")
html_renderer = HtmlRenderer(t2i_base_url)
logger = LogManager.GetLogger(log_name="astrbot")
db_helper = SQLiteDatabase(DB_PATH)
# 简单的偏好设置存储, 这里后续应该存储到数据库中, 一些部分可以存储到配置中
sp = SharedPreferences()
# 文件令牌服务
file_token_service = FileTokenService()
pip_installer = PipInstaller(
    astrbot_config.get("pip_install_arg", ""),
    astrbot_config.get("pypi_index_url", None),
)
web_chat_queue = asyncio.Queue(maxsize=32)
web_chat_back_queue = asyncio.Queue(maxsize=32)
