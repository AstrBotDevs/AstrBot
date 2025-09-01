"""
astrbot.api.event
该模块包含 AstrBot 所有事件相关模块
"""

# AstrBot 事件, event api的所有者
from astrbot.core.platform import AstrMessageEvent

# AstrBot 事件相关组件
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    MessageChain,
    CommandResult,
    EventResultType,
    ResultContentType,
)

from astrbot.core.platform.astr_message_event import MessageSesion as MessageSession


__all__ = [
    "MessageEventResult",
    "MessageChain",
    "CommandResult",
    "EventResultType",
    "AstrMessageEvent",
    "MessageSession",
    "ResultContentType",
]
