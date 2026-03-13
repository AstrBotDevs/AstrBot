"""AstrBot SDK 的顶层公共 API。

这里仅重新导出 v4 推荐直接导入的稳定入口。

- ``astrbot_sdk``: v4 原生稳定 API
- ``astrbot_sdk.compat``: 旧版顶层导入路径兼容入口
- ``astrbot_sdk.api``: 历史 ``api.*`` 导入路径兼容面

这样可以把原生 API 与迁移入口明确分开，避免旧路径继续反向污染顶层包。
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
