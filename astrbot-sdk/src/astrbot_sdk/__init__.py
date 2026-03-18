"""AstrBot SDK 的顶层公共 API。

这里仅重新导出 v4 推荐直接导入的稳定入口。

新插件应直接使用此模块的导出：
    from astrbot_sdk import Star, Context, MessageEvent
    from astrbot_sdk.decorators import on_command, on_message

迁移期适配入口位于独立模块；此处只暴露 v4 原生主入口。
"""

from .clients.managers import (
    ConversationCreateParams,
    ConversationManagerClient,
    ConversationRecord,
    ConversationUpdateParams,
    KnowledgeBaseCreateParams,
    KnowledgeBaseManagerClient,
    KnowledgeBaseRecord,
    PersonaCreateParams,
    PersonaManagerClient,
    PersonaRecord,
    PersonaUpdateParams,
)
from .clients.metadata import PluginMetadata, StarMetadata
from .clients.platform import PlatformError, PlatformStats, PlatformStatus
from .clients.provider import (
    ManagedProviderRecord,
    ProviderChangeEvent,
    ProviderManagerClient,
)
from .clients.session import SessionPluginManager, SessionServiceManager
from .commands import CommandGroup, command_group, print_cmd_tree
from .context import Context
from .conversation import (
    ConversationClosed,
    ConversationReplaced,
    ConversationSession,
    ConversationState,
)
from .decorators import (
    admin_only,
    conversation_command,
    cooldown,
    group_only,
    message_types,
    on_command,
    on_event,
    on_message,
    on_schedule,
    platforms,
    priority,
    private_only,
    provide_capability,
    rate_limit,
    require_admin,
)
from .errors import AstrBotError
from .events import MessageEvent
from .filters import (
    CustomFilter,
    MessageTypeFilter,
    PlatformFilter,
    all_of,
    any_of,
    custom_filter,
)
from .message_components import (
    At,
    AtAll,
    BaseMessageComponent,
    File,
    Forward,
    Image,
    MediaHelper,
    Plain,
    Poke,
    Record,
    Reply,
    UnknownComponent,
    Video,
)
from .message_result import (
    EventResultType,
    MessageBuilder,
    MessageChain,
    MessageEventResult,
)
from .message_session import MessageSession
from .plugin_kv import PluginKVStoreMixin
from .schedule import ScheduleContext
from .session_waiter import SessionController, session_waiter
from .star import Star
from .star_tools import StarTools
from .types import GreedyStr

__all__ = [
    "AstrBotError",
    "At",
    "AtAll",
    "BaseMessageComponent",
    "CommandGroup",
    "ConversationClosed",
    "ConversationCreateParams",
    "ConversationManagerClient",
    "ConversationReplaced",
    "ConversationRecord",
    "ConversationSession",
    "ConversationState",
    "ConversationUpdateParams",
    "Context",
    "CustomFilter",
    "EventResultType",
    "File",
    "Forward",
    "GreedyStr",
    "Image",
    "KnowledgeBaseCreateParams",
    "KnowledgeBaseManagerClient",
    "KnowledgeBaseRecord",
    "ManagedProviderRecord",
    "MediaHelper",
    "MessageEvent",
    "MessageEventResult",
    "MessageChain",
    "MessageBuilder",
    "MessageSession",
    "MessageTypeFilter",
    "Plain",
    "PluginKVStoreMixin",
    "PluginMetadata",
    "PlatformFilter",
    "PlatformError",
    "PlatformStats",
    "PlatformStatus",
    "Poke",
    "PersonaCreateParams",
    "PersonaManagerClient",
    "PersonaRecord",
    "PersonaUpdateParams",
    "ProviderChangeEvent",
    "ProviderManagerClient",
    "Record",
    "Reply",
    "ScheduleContext",
    "SessionPluginManager",
    "SessionServiceManager",
    "SessionController",
    "Star",
    "StarMetadata",
    "StarTools",
    "UnknownComponent",
    "Video",
    "admin_only",
    "all_of",
    "any_of",
    "cooldown",
    "conversation_command",
    "command_group",
    "custom_filter",
    "group_only",
    "message_types",
    "on_command",
    "on_event",
    "on_message",
    "on_schedule",
    "platforms",
    "print_cmd_tree",
    "priority",
    "provide_capability",
    "private_only",
    "rate_limit",
    "require_admin",
    "session_waiter",
]
