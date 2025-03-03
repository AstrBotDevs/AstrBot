import os
import asyncio
from .log import LogManager, LogBroker  # noqa
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from astrbot.core.utils.shared_preferences import SharedPreferences
from astrbot.core.utils.pip_installer import PipInstaller
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.config.default import DB_PATH
from astrbot.core.config import AstrBotConfig

os.makedirs("data", exist_ok=True)

astrbot_config = AstrBotConfig()
t2i_base_url = astrbot_config.get("t2i_endpoint", "https://t2i.soulter.top/text2img")
html_renderer = HtmlRenderer(t2i_base_url)
logger = LogManager.GetLogger(log_name="astrbot")

if os.environ.get("TESTING", ""):
    logger.setLevel("DEBUG")

db_helper = SQLiteDatabase(DB_PATH)
sp = SharedPreferences()  # 简单的偏好设置存储
pip_installer = PipInstaller(astrbot_config.get("pip_install_arg", ""))
web_chat_queue = asyncio.Queue(maxsize=32)
web_chat_back_queue = asyncio.Queue(maxsize=32)
WEBUI_SK = "Advanced_System_for_Text_Response_and_Bot_Operations_Tool"
