"""
astrbot.api.platform.qqofficial
该模块包含了 AstrBot 对 QQ 官方 平台的适配器
"""

from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)

from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    botClient,
    QQOfficialPlatformAdapter as QQOfficialAdapter,
)

__all__ = [
    "QQOfficialAdapter",
    "botClient",
    "QQOfficialMessageEvent",
]
