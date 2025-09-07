"""
astrbot.api.event.message
此模块包含事件中的消息相关模块
"""

from . import message_components as MessageComponents
from astrbot.core.platform import (
    AstrBotMessage,  # AstrBot 的消息对象, 包括id, 消息链等
    MessageMember,  # 消息成员, 包括发送者id和昵称
    MessageType,  # 消息类型(私聊/群聊/其他)
)

# 消息链与消息链的结果
from astrbot.core.message.message_event_result import (
    MessageEventResult,  # 消息中的所有组件和事件处理的结果
    MessageChain,  # 消息链
    EventResultType,  # 事件处理结果类型(继续/终止)
    ResultContentType,  # 事件结果内容类型(LLM/流式/普通)
)

__all__ = [
    "AstrBotMessage",
    "MessageMember",
    "MessageType",
    "MessageEventResult",
    "MessageChain",
    "EventResultType",
    "ResultContentType",
    "MessageComponents",
]
