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
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger as base_logger

from .clients import (
    DBClient,
    HTTPClient,
    LLMClient,
    MemoryClient,
    MetadataClient,
    PlatformClient,
    RegistryClient,
    SessionPluginManager,
    SessionServiceManager,
)
from .clients._proxy import CapabilityProxy
from .clients.llm import LLMResponse
from .llm.entities import LLMToolSpec, ProviderMeta, ProviderRequest
from .llm.tools import LLMToolManager


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
        source_event_payload: dict[str, Any] | None = None,
    ) -> None:
        """初始化上下文。

        Args:
            peer: 协议对等端实例
            plugin_id: 当前插件 ID
            cancel_token: 取消令牌，None 时创建新令牌
            logger: 日志器，None 时使用默认 logger 并绑定 plugin_id
        """
        proxy = CapabilityProxy(peer, caller_plugin_id=plugin_id)
        self._proxy = proxy
        self.peer = peer
        self.llm = LLMClient(proxy)
        self.memory = MemoryClient(proxy)
        self.db = DBClient(proxy)
        self.platform = PlatformClient(proxy)
        self.http = HTTPClient(proxy)
        self.metadata = MetadataClient(proxy, plugin_id)
        self.registry = RegistryClient(proxy)
        self.session_plugins = SessionPluginManager(proxy)
        self.session_services = SessionServiceManager(proxy)
        self._llm_tool_manager = LLMToolManager(proxy)
        self.plugin_id = plugin_id
        self.logger = logger or base_logger.bind(plugin_id=plugin_id)
        self.cancel_token = cancel_token or CancelToken()
        self._source_event_payload = (
            dict(source_event_payload) if isinstance(source_event_payload, dict) else {}
        )

    @staticmethod
    def _provider_meta_list(items: Iterable[Any]) -> list[ProviderMeta]:
        providers: list[ProviderMeta] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            provider = ProviderMeta.from_payload(item)
            if provider is not None:
                providers.append(provider)
        return providers

    async def get_data_dir(self) -> Path:
        """Return the plugin-scoped data directory path."""
        output = await self._proxy.call("system.get_data_dir", {})
        return Path(str(output.get("path", "")))

    async def text_to_image(
        self,
        text: str,
        *,
        return_url: bool = True,
    ) -> str:
        """Render plain text into an image using the host renderer."""
        output = await self._proxy.call(
            "system.text_to_image",
            {"text": text, "return_url": return_url},
        )
        return str(output.get("result", ""))

    async def html_render(
        self,
        tmpl: str,
        data: dict[str, Any],
        *,
        return_url: bool = True,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Render an HTML template using the host renderer."""
        output = await self._proxy.call(
            "system.html_render",
            {
                "tmpl": tmpl,
                "data": dict(data),
                "return_url": return_url,
                "options": options,
            },
        )
        return str(output.get("result", ""))

    async def get_using_provider(self, umo: str | None = None) -> ProviderMeta | None:
        output = await self._proxy.call("provider.get_using", {"umo": umo})
        return ProviderMeta.from_payload(output.get("provider"))

    async def get_current_chat_provider_id(self, umo: str | None = None) -> str | None:
        output = await self._proxy.call(
            "provider.get_current_chat_provider_id",
            {"umo": umo},
        )
        value = output.get("provider_id")
        return str(value) if value else None

    async def get_all_providers(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all", {})
        return self._provider_meta_list(output.get("providers", []))

    async def get_all_tts_providers(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all_tts", {})
        return self._provider_meta_list(output.get("providers", []))

    async def get_all_stt_providers(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all_stt", {})
        return self._provider_meta_list(output.get("providers", []))

    async def get_all_embedding_providers(self) -> list[ProviderMeta]:
        output = await self._proxy.call("provider.list_all_embedding", {})
        return self._provider_meta_list(output.get("providers", []))

    async def get_using_tts_provider(
        self, umo: str | None = None
    ) -> ProviderMeta | None:
        output = await self._proxy.call("provider.get_using_tts", {"umo": umo})
        return ProviderMeta.from_payload(output.get("provider"))

    async def get_using_stt_provider(
        self, umo: str | None = None
    ) -> ProviderMeta | None:
        output = await self._proxy.call("provider.get_using_stt", {"umo": umo})
        return ProviderMeta.from_payload(output.get("provider"))

    def get_llm_tool_manager(self) -> LLMToolManager:
        return self._llm_tool_manager

    async def activate_llm_tool(self, name: str) -> bool:
        return await self._llm_tool_manager.activate(name)

    async def deactivate_llm_tool(self, name: str) -> bool:
        return await self._llm_tool_manager.deactivate(name)

    async def add_llm_tools(self, *tools: LLMToolSpec) -> list[str]:
        return await self._llm_tool_manager.add(*tools)

    async def tool_loop_agent(
        self,
        request: ProviderRequest | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        provider_request = request or ProviderRequest()
        if kwargs:
            merged = provider_request.model_dump()
            merged.update(kwargs)
            provider_request = ProviderRequest.model_validate(merged)
        payload = provider_request.to_payload()
        target_payload = self._source_event_payload.get("target")
        if isinstance(target_payload, dict):
            # Preserve the original message target so core can recover the
            # dispatch token for message-bound tool loop execution.
            payload["target"] = dict(target_payload)
        output = await self._proxy.call("agent.tool_loop.run", payload)
        return LLMResponse.model_validate(output)
