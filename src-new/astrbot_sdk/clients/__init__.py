"""Native v4 capability clients.

These clients provide the narrow, typed surface exposed by `Context` for
calling remote capabilities. They handle capability names, payload shaping,
and result decoding, without exposing protocol or transport details.

Compatibility features such as legacy conversation management, MessageChain
bridging, and agent-loop semantics live in `_legacy_api.py` and `api/`.

当前公开客户端：
    - LLMClient: 文本/结构化/流式 LLM 调用
    - MemoryClient: 记忆搜索、保存、读取、删除
    - DBClient: 键值存储 get/set/delete/list
    - PlatformClient: 平台消息发送与成员查询
"""

from .db import DBClient
from .llm import ChatMessage, LLMClient, LLMResponse
from .memory import MemoryClient
from .platform import PlatformClient

__all__ = [
    "ChatMessage",
    "DBClient",
    "LLMClient",
    "LLMResponse",
    "MemoryClient",
    "PlatformClient",
]
