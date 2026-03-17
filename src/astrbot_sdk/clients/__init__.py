"""Native v4 capability clients.

These clients provide the narrow, typed surface exposed by `Context` for
calling remote capabilities. They handle capability names, payload shaping,
and result decoding, without exposing protocol or transport details.

Migration shims and higher-level orchestration stay outside these native
capability clients so `Context` keeps a narrow, stable surface.

当前公开客户端：
    - LLMClient: 文本/结构化/流式 LLM 调用
    - MemoryClient: 记忆搜索、保存、读取、删除
    - DBClient: 键值存储 get/set/delete/list
    - FileServiceClient: 文件令牌注册与解析
    - PlatformClient: 平台消息发送与成员查询
    - ProviderClient: Provider 元信息与专用 provider proxy
    - PersonaManagerClient: 人格管理
    - ConversationManagerClient: 对话管理
    - KnowledgeBaseManagerClient: 知识库管理
    - HTTPClient: Web API 注册
    - MetadataClient: 插件元数据查询
"""

from .db import DBClient
from .files import FileRegistration, FileServiceClient
from .http import HTTPClient
from .llm import ChatMessage, LLMClient, LLMResponse
from .managers import (
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
from .memory import MemoryClient
from .metadata import MetadataClient, PluginMetadata, StarMetadata
from .platform import PlatformClient, PlatformError, PlatformStats, PlatformStatus
from .provider import (
    ManagedProviderRecord,
    ProviderChangeEvent,
    ProviderClient,
    ProviderManagerClient,
)
from .registry import HandlerMetadata, RegistryClient
from .session import SessionPluginManager, SessionServiceManager

__all__ = [
    "ChatMessage",
    "ConversationCreateParams",
    "ConversationManagerClient",
    "ConversationRecord",
    "ConversationUpdateParams",
    "DBClient",
    "FileRegistration",
    "FileServiceClient",
    "HTTPClient",
    "KnowledgeBaseCreateParams",
    "KnowledgeBaseManagerClient",
    "KnowledgeBaseRecord",
    "LLMClient",
    "LLMResponse",
    "MemoryClient",
    "ManagedProviderRecord",
    "MetadataClient",
    "PlatformClient",
    "PlatformError",
    "PlatformStats",
    "PlatformStatus",
    "PersonaCreateParams",
    "PersonaManagerClient",
    "PersonaRecord",
    "PersonaUpdateParams",
    "ProviderChangeEvent",
    "ProviderClient",
    "ProviderManagerClient",
    "PluginMetadata",
    "StarMetadata",
    "HandlerMetadata",
    "RegistryClient",
    "SessionPluginManager",
    "SessionServiceManager",
]
