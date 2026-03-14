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
    - PlatformClient: 平台消息发送与成员查询
    - HTTPClient: Web API 注册
    - MetadataClient: 插件元数据查询
"""

from .db import DBClient
from .http import HTTPClient
from .llm import ChatMessage, LLMClient, LLMResponse
from .memory import MemoryClient
from .metadata import MetadataClient, PluginMetadata
from .platform import PlatformClient

__all__ = [
    "ChatMessage",
    "DBClient",
    "HTTPClient",
    "LLMClient",
    "LLMResponse",
    "MemoryClient",
    "MetadataClient",
    "PlatformClient",
    "PluginMetadata",
]
