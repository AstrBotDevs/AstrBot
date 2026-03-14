"""v4 原生运行时上下文。

`Context` 是插件与 AstrBot Core 交互的主要入口，
负责组合所有 capability 客户端并提供统一的访问接口。

每个 handler 调用都会创建一个新的 Context 实例，
绑定到当前的 Peer、插件 ID 和取消令牌。

Attributes:
    llm: LLM 能力客户端，用于 AI 对话
    memory: 记忆能力客户端，用于语义存储
    db: 数据库客户端，用于 KV 持久化
    platform: 平台客户端，用于发送消息
    http: HTTP 客户端，用于注册 API 端点
    metadata: 元数据客户端，用于查询插件信息
    plugin_id: 当前插件的唯一标识
    logger: 绑定了插件 ID 的日志器
    cancel_token: 取消令牌，用于处理请求取消
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from loguru import logger as base_logger

from .clients import (
    DBClient,
    HTTPClient,
    LLMClient,
    MemoryClient,
    MetadataClient,
    PlatformClient,
)
from .clients._proxy import CapabilityProxy


@dataclass(slots=True)
class CancelToken:
    """请求取消令牌。

    用于协调长时间运行操作的取消。当用户取消请求或
    上游超时时，令牌会被触发，允许 handler 及时清理资源。

    Example:
        async def long_operation(ctx: Context):
            for item in large_list:
                ctx.cancel_token.raise_if_cancelled()
                await process(item)
    """

    _cancelled: asyncio.Event

    def __init__(self) -> None:
        self._cancelled = asyncio.Event()

    def cancel(self) -> None:
        """触发取消信号。"""
        self._cancelled.set()

    @property
    def cancelled(self) -> bool:
        """检查是否已被取消。"""
        return self._cancelled.is_set()

    async def wait(self) -> None:
        """等待取消信号。"""
        await self._cancelled.wait()

    def raise_if_cancelled(self) -> None:
        """如果已取消则抛出 CancelledError。

        Raises:
            asyncio.CancelledError: 如果令牌已被取消
        """
        if self.cancelled:
            raise asyncio.CancelledError


class Context:
    """插件运行时上下文。

    组合所有 capability 客户端，提供统一的访问接口。
    每个 handler 调用都会创建新的 Context 实例。

    Attributes:
        peer: 协议对等端，用于底层通信
        llm: LLM 客户端
        memory: 记忆客户端
        db: 数据库客户端
        platform: 平台客户端
        http: HTTP 客户端
        metadata: 元数据客户端
        plugin_id: 当前插件 ID
        logger: 日志器
        cancel_token: 取消令牌
    """

    def __init__(
        self,
        *,
        peer,
        plugin_id: str,
        cancel_token: CancelToken | None = None,
        logger: Any | None = None,
    ) -> None:
        """初始化上下文。

        Args:
            peer: 协议对等端实例
            plugin_id: 当前插件 ID
            cancel_token: 取消令牌，None 时创建新令牌
            logger: 日志器，None 时使用默认 logger 并绑定 plugin_id
        """
        proxy = CapabilityProxy(peer, caller_plugin_id=plugin_id)
        self.peer = peer
        self.llm = LLMClient(proxy)
        self.memory = MemoryClient(proxy)
        self.db = DBClient(proxy)
        self.platform = PlatformClient(proxy)
        self.http = HTTPClient(proxy)
        self.metadata = MetadataClient(proxy, plugin_id)
        self.plugin_id = plugin_id
        self.logger = logger or base_logger.bind(plugin_id=plugin_id)
        self.cancel_token = cancel_token or CancelToken()
