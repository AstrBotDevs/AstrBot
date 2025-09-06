"""
astrbot.api.platform.telegram
该模块包含了 AstrBot 对 Telegram 平台的适配器
"""

from astrbot.core.platform.sources.telegram.tg_event import (
    TelegramPlatformEvent as TelegramMessageEvent,
)

from astrbot.core.platform.sources.telegram.tg_adapter import (
    TelegramPlatformAdapter as TelegramAdapter,
)

__all__ = [
    "TelegramAdapter",
    "TelegramMessageEvent",
]
