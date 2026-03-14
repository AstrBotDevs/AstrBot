"""AstrBot SDK 的顶层公共 API。

这里仅重新导出 v4 推荐直接导入的稳定入口。

新插件应直接使用此模块的导出：
    from astrbot_sdk import Star, Context, MessageEvent
    from astrbot_sdk.decorators import on_command, on_message

迁移期适配入口位于独立模块；此处只暴露 v4 原生主入口。
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
