"""AstrBot SDK 的顶层公共 API。

这里仅重新导出 v4 推荐直接导入的稳定入口。

新插件应直接使用此模块的导出：
    from astrbot_sdk import Star, Context, MessageEvent
    from astrbot_sdk.decorators import on_command, on_message

旧插件请使用 AstrBot 主程序运行，不再由 SDK 提供 compat 层。
"""

from .context import Context
from .decorators import (
    on_command,
    on_event,
    on_message,
    on_schedule,
    provide_capability,
    require_admin,
)
from .errors import AstrBotError
from .events import MessageEvent
from .star import Star

__all__ = [
    "AstrBotError",
    "Context",
    "MessageEvent",
    "Star",
    "on_command",
    "on_event",
    "on_message",
    "on_schedule",
    "provide_capability",
    "require_admin",
]
