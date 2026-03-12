"""客户端模块。

提供与 AstrBot 核心通信的客户端接口，通过 RPC 能力代理实现远程调用。
所有客户端均基于 CapabilityProxy 构建，统一处理方法调用和流式响应。

架构说明：
    旧版 (src/astrbot_sdk/api/star/context.py):
        - Context 基类直接提供 llm_generate(), tool_loop_agent(), send_message() 等方法
        - 使用 MessageChain, ToolSet 等复杂类型
        - 内置 conversation_manager 会话管理

    新版 (src-new):
        - Context 组合多个专用客户端 (llm, memory, db, platform)
        - 每个客户端负责单一领域的功能
        - 通过 Peer 和 CapabilityProxy 实现远程能力调用
        - 支持流式响应 (stream_chat)

可用客户端：
    - LLMClient: 大语言模型调用，支持普通/流式聊天
    - MemoryClient: 记忆存储，支持搜索、保存、获取、删除
    - DBClient: 键值数据库，支持 get/set/delete/list
    - PlatformClient: 平台消息发送，支持文本和图片消息

TODO: (相比旧版缺失的功能):
    - LLMClient 缺少 tool_loop_agent() Agent 循环能力
    - LLMClient 缺少 add_llm_tools() 动态工具注册
    - LLMClient.chat() 缺少 image_urls、tools、contexts 等高级参数支持
    - Context 缺少 conversation_manager 会话管理器集成
    - 缺少 MessageChain 消息链构建支持
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
