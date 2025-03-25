from .auth import AuthRoute
from .plugin import PluginRoute
from .config import ConfigRoute
from .update import UpdateRoute
from .stat import StatRoute
from .log import LogRoute
from .static_file import StaticFileRoute
from .chat import ChatRoute
from .tools import ToolsRoute  # 导入新的ToolsRoute
from .conversation import ConversationRoute


__all__ = [
    "AuthRoute",
    "PluginRoute",
    "ConfigRoute",
    "UpdateRoute",
    "StatRoute",
    "LogRoute",
    "StaticFileRoute",
    "ChatRoute",
    "ToolsRoute",  # 添加新的ToolsRoute
    "ConversationRoute",
]
