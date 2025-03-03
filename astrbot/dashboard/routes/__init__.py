from .auth import AuthRoute
from .plugin import PluginRoute
from .config import ConfigRoute
from .update import UpdateRoute
from .stat import StatRoute
from .log import LogRoute
from .static_file import StaticFileRoute
from .chat import ChatRoute


__all__ = [
    "AuthRoute",
    "PluginRoute",
    "ConfigRoute",
    "UpdateRoute",
    "StatRoute",
    "LogRoute",
    "StaticFileRoute",
    "ChatRoute",
]
