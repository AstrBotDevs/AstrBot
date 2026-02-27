from .api_key import ApiKeyRoute
from .auth import AuthRoute
from .backup import BackupRoute
from .chat import ChatRoute
from .chatui_project import ChatUIProjectRoute
from .command import CommandRoute
from .config import ConfigRoute
from .conversation import ConversationRoute
from .cron import CronRoute
from .file import FileRoute
from .knowledge_base import KnowledgeBaseRoute
from .log import LogRoute
from .open_api import OpenApiRoute
from .persona import PersonaRoute
from .platform import PlatformRoute
from .plugin import PluginRoute
from .session_management import SessionManagementRoute
from .skills import SkillsRoute
from .stat import StatRoute
from .static_file import StaticFileRoute
from .subagent import SubAgentRoute
from .tools import ToolsRoute
from .update import UpdateRoute
from .lang_route import LangRoute

__all__ = [
    "ApiKeyRoute",
    "AuthRoute",
    "BackupRoute",
    "ChatRoute",
    "ChatUIProjectRoute",
    "CommandRoute",
    "ConfigRoute",
    "ConversationRoute",
    "CronRoute",
    "FileRoute",
    "KnowledgeBaseRoute",
    "LogRoute",
    "OpenApiRoute",
    "PersonaRoute",
    "PlatformRoute",
    "PluginRoute",
    "SessionManagementRoute",
    "StatRoute",
    "StaticFileRoute",
    "SubAgentRoute",
    "ToolsRoute",
    "SkillsRoute",
    "UpdateRoute",
    "LangRoute",
]
