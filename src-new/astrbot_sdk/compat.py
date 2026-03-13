"""过渡期旧版顶层导入路径 compat facade。"""

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
