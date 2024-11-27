from .log import LogManager, LogBroker
from core.utils.t2i.renderer import HtmlRenderer

html_renderer = HtmlRenderer()
logger = LogManager.GetLogger(log_name='astrbot')