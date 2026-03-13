"""旧版 ``astrbot.api`` 导入路径兼容入口。"""

from loguru import logger

from astrbot_sdk.api import (
    AstrBotConfig,
    components,
    event,
    message,
    message_components,
    platform,
    provider,
    star,
)

__all__ = [
    "AstrBotConfig",
    "components",
    "event",
    "logger",
    "message",
    "message_components",
    "platform",
    "provider",
    "star",
]
