"""AstrBot SDK 的顶层公共 API。

这里仅重新导出 v4 推荐直接导入的稳定入口。
旧版兼容能力由 ``astrbot_sdk.api`` 与 ``astrbot_sdk.compat`` 承接，
避免把迁移层和原生 API 混在同一个包入口里。
"""

from .context import Context
from .decorators import on_command, on_event, on_message, on_schedule, require_admin
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
    "require_admin",
]
