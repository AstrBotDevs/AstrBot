"""v4 原生能力客户端集合。

这些客户端是 `Context` 的窄接口，分别封装 llm、memory、db、platform
四类远程 capability。它们只负责能力调用与轻量参数整形，不承载旧版
`conversation_manager`、`MessageChain` 或 agent loop 语义；这些兼容能力由
`_legacy_api.py` 与 `api/` compat 子模块处理。

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
