"""旧版 ``astrbot.core`` 导入路径兼容入口。"""

from loguru import logger

from astrbot_sdk._shared_preferences import sp
from astrbot_sdk.api.basic import AstrBotConfig

from . import utils

__all__ = ["AstrBotConfig", "logger", "sp", "utils"]
