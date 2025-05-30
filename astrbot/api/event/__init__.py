"""
astrbot.api.event
该模块包含 AstrBot 所有事件相关模块
"""

from astrbot.core.message.message_event_result import (
    MessageEventResult,
    MessageChain,
    CommandResult,
    EventResultType,
    ResultContentType,
)

from astrbot.core.platform import AstrMessageEvent

__all__ = [
    "MessageEventResult",
    "MessageChain",
    "CommandResult",
    "EventResultType",
    "AstrMessageEvent",
    "ResultContentType",
]
