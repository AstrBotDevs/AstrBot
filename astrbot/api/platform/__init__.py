from astrbot.core.platform import (
    AstrMessageEvent,
    Platform,
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)

from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.message.components import *

__all__ = [
    "AstrMessageEvent",
    "Platform",
    "AstrBotMessage",
    "MessageMember",
    "MessageType",
    "PlatformMetadata",
    "register_platform_adapter",
]
