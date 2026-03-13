"""旧版顶层导入路径的兼容入口。

这个模块只承接历史上的顶层 legacy 导入习惯，例如 ``Context`` /
``CommandComponent``。更细的旧路径兼容仍保留在 ``astrbot_sdk.api`` 下。

新代码不应从这里导入；这里的职责是给旧插件一个明确、可隔离的旁路入口。
"""

from ._legacy_api import (
    CommandComponent,
    Context,
    LegacyContext,
    LegacyConversationManager,
)

__all__ = [
    "CommandComponent",
    "Context",
    "LegacyContext",
    "LegacyConversationManager",
]
