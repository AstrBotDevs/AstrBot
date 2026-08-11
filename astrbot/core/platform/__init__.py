"""Platform public names with lazy imports.

Keeping this package initializer light is important for source-independent
plugin contracts such as :mod:`astrbot.api.onebot`.
"""

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.astrbot_message import (
        AstrBotMessage,
        Group,
        MessageMember,
    )
    from astrbot.core.platform.message_type import MessageType
    from astrbot.core.platform.platform import Platform
    from astrbot.core.platform.platform_metadata import PlatformMetadata
    from astrbot.core.platform.route_identity import PlatformRouteIdentity
    from astrbot.core.platform.send_result import PlatformSendResult

_EXPORTS = {
    "AstrBotMessage": ("astrbot.core.platform.astrbot_message", "AstrBotMessage"),
    "Group": ("astrbot.core.platform.astrbot_message", "Group"),
    "MessageMember": ("astrbot.core.platform.astrbot_message", "MessageMember"),
    "MessageType": ("astrbot.core.platform.message_type", "MessageType"),
    "AstrMessageEvent": (
        "astrbot.core.platform.astr_message_event",
        "AstrMessageEvent",
    ),
    "Platform": ("astrbot.core.platform.platform", "Platform"),
    "PlatformMetadata": ("astrbot.core.platform.platform_metadata", "PlatformMetadata"),
    "PlatformRouteIdentity": (
        "astrbot.core.platform.route_identity",
        "PlatformRouteIdentity",
    ),
    "PlatformSendResult": ("astrbot.core.platform.send_result", "PlatformSendResult"),
}


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module = import_module(target[0])
    value = getattr(module, target[1])
    globals()[name] = value
    return value


__all__ = [
    "AstrBotMessage",
    "AstrMessageEvent",
    "Group",
    "MessageMember",
    "MessageType",
    "Platform",
    "PlatformMetadata",
    "PlatformRouteIdentity",
    "PlatformSendResult",
]
