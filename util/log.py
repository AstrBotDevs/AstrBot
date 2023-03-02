import logging
from logging.handlers import RotatingFileHandler
import colorlog

logger = logging.getLogger("QQChannelChatGPT")
logger.setLevel(logging.DEBUG)
handler = colorlog.StreamHandler()
fmt = "%(log_color)s[%(name)s] %(message)s"
handler.setFormatter(colorlog.ColoredFormatter(
 fmt))
logger.addHandler(handler)