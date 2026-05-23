from .api_key import ApiKeyRoute
from .auth import AuthRoute
from .backup import BackupRoute
from .chat import ChatRoute
from .chatui_project import ChatUIProjectRoute
from .command import CommandRoute
from .config import ConfigRoute
from .conversation import ConversationRoute
from .cron import CronRoute
from .error_analysis import ErrorAnalysisRoute
from .file import FileRoute
from .knowledge_base import KnowledgeBaseRoute
from .live_chat import LiveChatRoute
from .log import LogRoute
from .memory import MemoryRoute
from .persona import PersonaRoute
from .platform import PlatformRoute
from .plugin import PluginRoute
from .sandbox import SandboxRoute
from .session_management import SessionManagementRoute
from .skills import SkillsRoute
from .stat import StatRoute
from .static_file import StaticFileRoute
from .subagent import SubAgentRoute
from .t2i import T2iRoute
from .tools import ToolsRoute
from .update import UpdateRoute
from .widget import ChatWidget

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
    "ErrorAnalysisRoute",
    "FileRoute",
    "KnowledgeBaseRoute",
    "LiveChatRoute",
    "LogRoute",
    "MemoryRoute",
    "PersonaRoute",
    "PlatformRoute",
    "PluginRoute",
    "SandboxRoute",
    "SessionManagementRoute",
    "SkillsRoute",
    "StatRoute",
    "StaticFileRoute",
    "SubAgentRoute",
    "T2iRoute",
    "ToolsRoute",
    "UpdateRoute",
    "ChatWidget",
]
