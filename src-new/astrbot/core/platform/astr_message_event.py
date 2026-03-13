"""旧版 ``astrbot.core.platform.astr_message_event`` 导入路径兼容入口。"""

from astrbot_sdk.api.event import (
    AstrMessageEvent,
    AstrMessageEventModel,
    MessageSesion,
    MessageSession,
)

if not hasattr(AstrMessageEvent, "bot"):
    AstrMessageEvent.bot = None

__all__ = [
    "AstrMessageEvent",
    "AstrMessageEventModel",
    "MessageSesion",
    "MessageSession",
]
