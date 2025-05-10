
from .core.config.default import VERSION
from .core.log import LogManager

logger = LogManager.GetLogger(log_name="astrbot")

__version__ = VERSION
""" astrbot 版本号 """
