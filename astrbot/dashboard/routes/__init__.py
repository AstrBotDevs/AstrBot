from .auth import AuthRoute
from .backup import BackupRoute
from .chat import ChatRoute
from .chatui_project import ChatUIProjectRoute
from .collection import CollectionRoute
from .command import CommandRoute
from .config import ConfigRoute
from .conversation import ConversationRoute
from .file import FileRoute
from .knowledge_base import KnowledgeBaseRoute
from .log import LogRoute
from .persona import PersonaRoute
from .platform import PlatformRoute
from .plugin import PluginRoute
from .session_management import SessionManagementRoute
from .skills import SkillsRoute
from .stat import StatRoute
from .static_file import StaticFileRoute
from .tools import ToolsRoute
from .update import UpdateRoute

__all__ = [
    "AuthRoute",
    "BackupRoute",
    "ChatRoute",
    "ChatUIProjectRoute",
    "CollectionRoute",
    "CommandRoute",
    "ConfigRoute",
    "ConversationRoute",
    "FileRoute",
    "KnowledgeBaseRoute",
    "LogRoute",
    "PersonaRoute",
    "PlatformRoute",
    "PluginRoute",
    "SessionManagementRoute",
    "StatRoute",
    "StaticFileRoute",
    "ToolsRoute",
    "SkillsRoute",
    "UpdateRoute",
]
