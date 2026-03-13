"""旧版 ``astrbot.core.message.message_event_result`` 导入路径兼容入口。"""

from astrbot_sdk.api.event import (
    EventResultType,
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot_sdk.api.event.event_result import CommandResult

__all__ = [
    "CommandResult",
    "EventResultType",
    "MessageChain",
    "MessageEventResult",
    "ResultContentType",
]
