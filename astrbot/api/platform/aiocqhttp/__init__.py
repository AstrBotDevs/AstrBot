"""
astrbot.api.platform.aiocqhttp
该模块包含了 AstrBot 有关 aiocqhttp 平台适配器的相关
"""

from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)

__all__ = [
    "AiocqhttpAdapter",
    "AiocqhttpMessageEvent",
]
