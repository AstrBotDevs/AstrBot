"""旧版 ``astrbot.core.platform`` 导入路径兼容入口。"""

from astrbot.core.message.components import *  # noqa: F403
from astrbot_sdk.api.event import (
    AstrBotMessage,
    AstrMessageEvent,
    Group,
    MessageMember,
    MessageType,
)
from astrbot_sdk.api.platform import PlatformMetadata


class Platform:
    """旧版平台适配器基类占位。"""


__all__ = [
    "AstrBotMessage",
    "AstrMessageEvent",
    "Group",
    "MessageMember",
    "MessageType",
    "Platform",
    "PlatformMetadata",
]
