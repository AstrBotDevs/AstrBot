from .auth import AuthRoute
from .backup import BackupRoute
from .chain_management import ChainManagementRoute
from .chat import ChatRoute
from .chatui_project import ChatUIProjectRoute
from .command import CommandRoute
from .config import ConfigRoute
from .conversation import ConversationRoute
from .file import FileRoute
from .knowledge_base import KnowledgeBaseRoute
from .log import LogRoute
from .persona import PersonaRoute
from .platform import PlatformRoute
from .plugin import PluginRoute
from .skills import SkillsRoute
from .stat import StatRoute
from .static_file import StaticFileRoute
from .tools import ToolsRoute
from .update import UpdateRoute

__all__ = [
    "AuthRoute",
    "BackupRoute",
    "ChatRoute",
    "ChainManagementRoute",
    "ChatUIProjectRoute",
    "CommandRoute",
    "ConfigRoute",
    "ConversationRoute",
    "FileRoute",
    "KnowledgeBaseRoute",
    "LogRoute",
    "PersonaRoute",
    "PlatformRoute",
    "PluginRoute",
    "StatRoute",
    "StaticFileRoute",
    "ToolsRoute",
    "SkillsRoute",
    "UpdateRoute",
]
