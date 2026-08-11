"""Typed, forward-compatible OneBot event DTOs."""

from astrbot.core.platform.contracts.onebot import (
    OneBotEvent,
    OneBotMessageEvent,
    OneBotMetaEvent,
    OneBotNoticeEvent,
    OneBotRequestEvent,
    OneBotSegment,
    OneBotSender,
)

__all__ = [
    "OneBotEvent",
    "OneBotMessageEvent",
    "OneBotNoticeEvent",
    "OneBotRequestEvent",
    "OneBotMetaEvent",
    "OneBotSegment",
    "OneBotSender",
]
