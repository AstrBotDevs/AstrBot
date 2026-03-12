"""旧版 ``astrbot_sdk.api.event`` 的兼容入口。"""

from .astr_message_event import AstrMessageEvent, AstrMessageEventModel
from .astrbot_message import AstrBotMessage, Group, MessageMember
from .event_result import EventResultType, MessageEventResult, ResultContentType
from .event_type import EventType
from .filter import ADMIN, filter
from .message_session import MessageSesion, MessageSession
from .message_type import MessageType

__all__ = [
    "ADMIN",
    "AstrBotMessage",
    "AstrMessageEvent",
    "AstrMessageEventModel",
    "EventResultType",
    "EventType",
    "Group",
    "MessageEventResult",
    "MessageMember",
    "MessageSesion",
    "MessageSession",
    "MessageType",
    "ResultContentType",
    "filter",
]
