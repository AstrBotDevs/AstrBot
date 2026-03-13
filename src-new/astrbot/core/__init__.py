"""旧版 ``astrbot.core`` 导入路径兼容入口。"""

from loguru import logger

from astrbot_sdk._shared_preferences import sp

from . import utils

__all__ = ["logger", "sp", "utils"]
