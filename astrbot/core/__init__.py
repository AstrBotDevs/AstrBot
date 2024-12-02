from .log import LogManager, LogBroker
from astrbot.core.utils.t2i.renderer import HtmlRenderer
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.config.default import DB_PATH

html_renderer = HtmlRenderer()
logger = LogManager.GetLogger(log_name='astrbot')
db_helper = SQLiteDatabase(DB_PATH)