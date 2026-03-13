"""旧版 ``astrbot.api.platform`` 导入路径兼容入口。"""

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


def register_platform_adapter(*args, **kwargs):
    raise NotImplementedError(
        "astrbot.api.platform.register_platform_adapter() 尚未在 v4 兼容层实现。"
    )


__all__ = [
    "AstrBotMessage",
    "AstrMessageEvent",
    "Group",
    "MessageMember",
    "MessageType",
    "Platform",
    "PlatformMetadata",
    "register_platform_adapter",
]
