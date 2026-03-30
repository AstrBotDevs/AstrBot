"""原生 astrbot-sdk 能力客户端

这些客户端为 Context 提供了用于调用远程能力的狭窄且具类型化 (typed) 的接口。
它们负责处理能力名称、载荷格式化（payload shaping）以及结果解码，且不会暴露协议或传输层的具体细节。

为了保持 Context 接口的精简与稳定，迁移适配层 (Migration shims) 以及高层级编排逻辑 (higher-level orchestration) 均不包含在这些原生能力客户端之内。

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
    - SkillClient: 运行时注册插件 skill
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
    MessageHistoryManagerClient,
    MessageHistoryPage,
    MessageHistoryRecord,
    MessageHistorySender,
    PersonaCreateParams,
    PersonaManagerClient,
    PersonaRecord,
    PersonaUpdateParams,
)
from .mcp import MCPManagerClient, MCPServerRecord, MCPServerScope, MCPSession
from .memory import MemoryClient
from .metadata import MetadataClient, PluginMetadata, StarMetadata
from .permission import PermissionCheckResult, PermissionClient, PermissionManagerClient
from .platform import PlatformClient, PlatformError, PlatformStats, PlatformStatus
from .provider import (
    ManagedProviderRecord,
    ProviderChangeEvent,
    ProviderClient,
    ProviderManagerClient,
)
from .registry import HandlerMetadata, RegistryClient
from .session import SessionPluginManager, SessionServiceManager
from .skills import SkillClient, SkillRegistration

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
    "MessageHistoryManagerClient",
    "MessageHistoryPage",
    "MessageHistoryRecord",
    "MessageHistorySender",
    "LLMClient",
    "LLMResponse",
    "MCPManagerClient",
    "MCPSession",
    "MCPServerRecord",
    "MCPServerScope",
    "MemoryClient",
    "ManagedProviderRecord",
    "MetadataClient",
    "PermissionCheckResult",
    "PermissionClient",
    "PermissionManagerClient",
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
    "SkillClient",
    "SkillRegistration",
]
