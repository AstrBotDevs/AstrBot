from .log import LogManager, LogBroker
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.config.default import DB_PATH

html_renderer = HtmlRenderer()
logger = LogManager.GetLogger(log_name='astrbot')
db_helper = SQLiteDatabase(DB_PATH)
WEBUI_SK = "Advanced_System_for_Text_Response_and_Bot_Operations_Tool"