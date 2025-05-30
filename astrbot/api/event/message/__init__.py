"""
astrbot.api.event.message
此模块包含事件中的消息相关模块
"""

from . import message_components as MessageComponents
from astrbot.core.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
)
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    MessageChain,
    MessageEventResult,
)

__all__ = [
    "AstrBotMessage",
    "MessageMember",
    "MessageType",
    "MessageEventResult",
    "MessageChain",
    "MessageComponents",
]
