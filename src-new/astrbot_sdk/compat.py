"""旧版顶层导入路径的兼容重导出。"""

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
