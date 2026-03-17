"""v4 原生运行时上下文。

`Context` 是插件与 AstrBot Core 交互的主要入口，
负责组合所有 capability 客户端并提供统一的访问接口。

每个 handler 调用都会创建一个新的 Context 实例，
绑定到当前的 Peer、插件 ID 和取消令牌。

Attributes:
    llm: LLM 能力客户端，用于 AI 对话
    memory: 记忆能力客户端，用于语义存储
    db: 数据库客户端，用于 KV 持久化
    files: 文件服务客户端，用于文件令牌注册与解析
    platform: 平台客户端，用于发送消息
    providers: Provider 客户端，用于查询和调用专用 Provider
    provider_manager: Provider 管理客户端，用于 reserved/system 级操作
    personas: 人格管理客户端
    conversations: 对话管理客户端
    kbs: 知识库管理客户端
    http: HTTP 客户端，用于注册 API 端点
    metadata: 元数据客户端，用于查询插件信息
    plugin_id: 当前插件的唯一标识
    logger: 绑定了插件 ID 的日志器
    cancel_token: 取消令牌，用于处理请求取消
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger as base_logger

from ._plugin_logger import PluginLogger
from ._star_runtime import current_star_instance
from .clients import (
    DBClient,
    HTTPClient,
    LLMClient,
    MemoryClient,
    MetadataClient,
    PlatformClient,
    PlatformError,
    PlatformStats,
    PlatformStatus,
    RegistryClient,
)
from .clients._proxy import CapabilityProxy
from .clients.files import FileServiceClient
from .clients.llm import LLMResponse
from .clients.managers import (
    ConversationManagerClient,
    KnowledgeBaseManagerClient,
    PersonaManagerClient,
)
from .clients.provider import ProviderClient, ProviderManagerClient
from .clients.session import SessionPluginManager, SessionServiceManager
from .errors import AstrBotError
from .llm.entities import LLMToolSpec, ProviderMeta, ProviderRequest
from .llm.tools import LLMToolManager
from .message_components import BaseMessageComponent
from .message_result import MessageChain
from .message_session import MessageSession

PlatformCompatContent = (
    str | MessageChain | Sequence[BaseMessageComponent] | Sequence[dict[str, Any]]
)


@dataclass(slots=True)
class PlatformCompatFacade:
    """兼容层平台入口，仅暴露安全元信息和主动发送能力。"""

    _ctx: Context
    id: str
    name: str
    type: str
    status: PlatformStatus = PlatformStatus.PENDING
    errors: list[PlatformError] = field(default_factory=list)
    last_error: PlatformError | None = None
    unified_webhook: bool = False
    _state_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    async def send_by_session(
        self,
        session: str | MessageSession,
        content: PlatformCompatContent,
    ) -> dict[str, Any]:
        return await self._ctx.platform.send_by_session(session, content)

    async def send_by_id(
        self,
        session_id: str,
        content: PlatformCompatContent,
        *,
        message_type: str = "private",
    ) -> dict[str, Any]:
        return await self._ctx.platform.send_by_id(
            self.id,
            session_id,
            content,
            message_type=message_type,
        )

    async def send(
        self,
        session: str | MessageSession,
        content: PlatformCompatContent,
        *,
        message_type: str = "private",
    ) -> dict[str, Any]:
        if isinstance(session, MessageSession):
            return await self.send_by_session(session, content)
        session_text = str(session).strip()
        if ":" in session_text:
            return await self.send_by_session(session_text, content)
        return await self.send_by_id(
            session_text,
            content,
            message_type=message_type,
        )

    async def refresh(self) -> None:
        async with self._state_lock:
            await self._refresh_locked()

    async def clear_errors(self) -> None:
        async with self._state_lock:
            await self._ctx._proxy.call(
                "platform.manager.clear_errors",
                {"platform_id": self.id},
            )
            await self._refresh_locked()

    async def get_stats(self) -> PlatformStats | None:
        output = await self._ctx._proxy.call(
            "platform.manager.get_stats",
            {"platform_id": self.id},
        )
        return PlatformStats.from_payload(output.get("stats"))

    def _apply_snapshot(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        self.name = str(payload.get("name", self.name))
        self.type = str(payload.get("type", self.type))
        self.status = PlatformStatus.from_value(payload.get("status"))
        errors_payload = payload.get("errors")
        if isinstance(errors_payload, list):
            self.errors = [
                error
                for error in (
                    PlatformError.from_payload(item) if isinstance(item, dict) else None
                    for item in errors_payload
                )
                if error is not None
            ]
        self.last_error = PlatformError.from_payload(payload.get("last_error"))
        self.unified_webhook = bool(payload.get("unified_webhook", False))

    async def _refresh_locked(self) -> None:
        output = await self._ctx._proxy.call(
            "platform.manager.get_by_id",
            {"platform_id": self.id},
        )
        self._apply_snapshot(output.get("platform"))


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
        providers: Provider 客户端
        provider_manager: Provider 管理客户端
        personas: 人格管理客户端
        conversations: 对话管理客户端
        kbs: 知识库管理客户端
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
        if isinstance(logger, PluginLogger):
            bound_logger = logger
        else:
            bound_logger = logger or base_logger.bind(plugin_id=plugin_id)
        self._proxy = proxy
        self.peer = peer
        self.llm = LLMClient(proxy)
        self.memory = MemoryClient(proxy)
        self.db = DBClient(proxy)
        self.files = FileServiceClient(proxy)
        self.platform = PlatformClient(proxy)
        self.providers = ProviderClient(proxy)
        self.provider_manager = ProviderManagerClient(
            proxy,
            plugin_id=plugin_id,
            logger=bound_logger,
        )
        self.personas = PersonaManagerClient(proxy)
        self.conversations = ConversationManagerClient(proxy)
        self.kbs = KnowledgeBaseManagerClient(proxy)
        self.http = HTTPClient(proxy)
        self.metadata = MetadataClient(proxy, plugin_id)
        self.registry = RegistryClient(proxy)
        self.session_plugins = SessionPluginManager(proxy)
        self.session_services = SessionServiceManager(proxy)
        self.persona_manager = self.personas
        self.conversation_manager = self.conversations
        self.kb_manager = self.kbs
        self._llm_tool_manager = LLMToolManager(proxy)
        self.plugin_id = plugin_id
        self.logger: PluginLogger = (
            bound_logger
            if isinstance(bound_logger, PluginLogger)
            else PluginLogger(plugin_id=plugin_id, logger=bound_logger)
        )
        self.cancel_token = cancel_token or CancelToken()
        self._source_event_payload = (
            dict(source_event_payload) if isinstance(source_event_payload, dict) else {}
        )

    async def get_data_dir(self) -> Path:
        """Return the plugin-scoped data directory path."""
        output = await self._proxy.call("system.get_data_dir", {})
        return Path(str(output.get("path", "")))

    async def _register_file_url(
        self,
        path: str,
        timeout: float | None = None,
    ) -> str:
        return await self.files._register_file_url(path, timeout=timeout)

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
        return await self.providers.get_using_chat(umo)

    async def get_current_chat_provider_id(self, umo: str | None = None) -> str | None:
        output = await self._proxy.call(
            "provider.get_current_chat_provider_id",
            {"umo": umo},
        )
        value = output.get("provider_id")
        return str(value) if value else None

    async def get_all_providers(self) -> list[ProviderMeta]:
        return await self.providers.list_all()

    async def get_all_tts_providers(self) -> list[ProviderMeta]:
        return await self.providers.list_tts()

    async def get_all_stt_providers(self) -> list[ProviderMeta]:
        return await self.providers.list_stt()

    async def get_all_embedding_providers(self) -> list[ProviderMeta]:
        return await self.providers.list_embedding()

    async def get_all_rerank_providers(self) -> list[ProviderMeta]:
        return await self.providers.list_rerank()

    async def get_using_tts_provider(
        self, umo: str | None = None
    ) -> ProviderMeta | None:
        provider = await self.providers.get_using_tts(umo)
        return provider.meta() if provider is not None else None

    async def get_using_stt_provider(
        self, umo: str | None = None
    ) -> ProviderMeta | None:
        provider = await self.providers.get_using_stt(umo)
        return provider.meta() if provider is not None else None

    async def send_message(
        self,
        session: str | MessageSession,
        content: PlatformCompatContent,
    ) -> dict[str, Any]:
        return await self.platform.send_by_session(session, content)

    async def send_message_by_id(
        self,
        type: str,
        id: str,
        content: PlatformCompatContent,
        *,
        platform: str,
    ) -> dict[str, Any]:
        platform_payload = await self._resolve_platform_target(platform)
        return await self.platform.send_by_id(
            str(platform_payload.get("id", "")),
            str(id),
            content,
            message_type=self._normalize_compat_message_type(type),
        )

    @staticmethod
    def _normalize_compat_message_type(value: str) -> str:
        normalized = str(value).strip().lower()
        if normalized in {"groupmessage", "group_message", "group"}:
            return "group"
        if normalized in {
            "privatemessage",
            "private_message",
            "private",
            "friendmessage",
            "friend_message",
            "friend",
        }:
            return "private"
        if not normalized:
            raise AstrBotError.invalid_input("send_message_by_id requires type")
        return normalized

    async def _resolve_platform_target(self, platform: str) -> dict[str, Any]:
        target = str(platform).strip()
        if not target:
            raise AstrBotError.invalid_input(
                "send_message_by_id requires explicit platform"
            )
        instances = await self._list_platform_instances()
        id_matches = [
            item for item in instances if str(item.get("id", "")).strip() == target
        ]
        if len(id_matches) == 1:
            return id_matches[0]
        normalized_target = target.lower()
        alias_matches = [
            item
            for item in instances
            if str(item.get("type", "")).strip().lower() == normalized_target
            or str(item.get("name", "")).strip().lower() == normalized_target
        ]
        if len(alias_matches) == 1:
            return alias_matches[0]
        if len(alias_matches) > 1:
            raise AstrBotError.invalid_input(
                f"send_message_by_id platform '{target}' is ambiguous"
            )
        raise AstrBotError.invalid_input(
            f"send_message_by_id cannot resolve platform '{target}'"
        )

    def get_llm_tool_manager(self) -> LLMToolManager:
        return self._llm_tool_manager

    async def activate_llm_tool(self, name: str) -> bool:
        return await self._llm_tool_manager.activate(name)

    async def deactivate_llm_tool(self, name: str) -> bool:
        return await self._llm_tool_manager.deactivate(name)

    async def add_llm_tools(self, *tools: LLMToolSpec) -> list[str]:
        return await self._llm_tool_manager.add(*tools)

    async def register_llm_tool(
        self,
        name: str,
        parameters_schema: dict[str, Any],
        desc: str,
        func_obj: Callable[..., Any] | Callable[..., Awaitable[Any]],
        *,
        active: bool = True,
    ) -> list[str]:
        if not callable(func_obj):
            raise TypeError("register_llm_tool requires a callable func_obj")
        tool_name = str(name).strip()
        if not tool_name:
            raise AstrBotError.invalid_input("register_llm_tool requires name")
        if not isinstance(parameters_schema, dict):
            raise TypeError("register_llm_tool requires parameters_schema dict")

        handler_ref = f"__dynamic_llm_tool__:{tool_name}"
        owner = getattr(func_obj, "__self__", None) or current_star_instance()
        dispatcher = getattr(self.peer, "_sdk_capability_dispatcher", None)
        if dispatcher is not None and hasattr(dispatcher, "add_dynamic_llm_tool"):
            dispatcher.add_dynamic_llm_tool(
                plugin_id=self.plugin_id,
                spec=LLMToolSpec(
                    name=tool_name,
                    description=str(desc),
                    parameters_schema=dict(parameters_schema),
                    handler_ref=handler_ref,
                    active=bool(active),
                ),
                callable_obj=func_obj,
                owner=owner,
            )
        try:
            return await self._llm_tool_manager.add(
                LLMToolSpec(
                    name=tool_name,
                    description=str(desc),
                    parameters_schema=dict(parameters_schema),
                    handler_ref=handler_ref,
                    active=bool(active),
                )
            )
        except Exception:
            if dispatcher is not None and hasattr(dispatcher, "remove_llm_tool"):
                dispatcher.remove_llm_tool(self.plugin_id, tool_name)
            raise

    async def unregister_llm_tool(self, name: str) -> bool:
        removed = await self._llm_tool_manager.remove(str(name))
        dispatcher = getattr(self.peer, "_sdk_capability_dispatcher", None)
        if dispatcher is not None and hasattr(dispatcher, "remove_llm_tool"):
            dispatcher.remove_llm_tool(self.plugin_id, str(name))
        return removed

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

    def _source_event_type(self) -> str:
        event_type = self._source_event_payload.get("event_type")
        if isinstance(event_type, str) and event_type.strip():
            return event_type.strip()
        fallback_type = self._source_event_payload.get("type")
        if isinstance(fallback_type, str) and fallback_type.strip():
            return fallback_type.strip()
        raw_payload = self._source_event_payload.get("raw")
        if isinstance(raw_payload, dict):
            raw_event_type = raw_payload.get("event_type")
            if isinstance(raw_event_type, str) and raw_event_type.strip():
                return raw_event_type.strip()
        return ""

    async def register_commands(
        self,
        command_name: str,
        handler_full_name: str,
        *,
        desc: str = "",
        priority: int = 0,
        use_regex: bool = False,
        ignore_prefix: bool = False,
    ) -> None:
        source_event_type = self._source_event_type()
        if source_event_type not in {"astrbot_loaded", "platform_loaded"}:
            raise AstrBotError.invalid_input(
                "register_commands is only available in astrbot_loaded/platform_loaded events"
            )
        if ignore_prefix:
            raise AstrBotError.invalid_input(
                "register_commands(ignore_prefix=True) is unsupported in SDK runtime"
            )
        await self._proxy.call(
            "registry.command.register",
            {
                "command_name": str(command_name),
                "handler_full_name": str(handler_full_name),
                "source_event_type": source_event_type,
                "desc": str(desc),
                "priority": int(priority),
                "use_regex": bool(use_regex),
                "ignore_prefix": False,
            },
        )

    async def register_task(
        self,
        task: Awaitable[Any],
        desc: str,
    ) -> asyncio.Task[Any]:
        task_desc = str(desc)

        async def _await_future(future: asyncio.Future[Any]) -> Any:
            return await future

        if isinstance(task, asyncio.Task):
            background_task = task
        elif asyncio.isfuture(task):
            background_task = asyncio.create_task(_await_future(task))
        elif asyncio.iscoroutine(task):
            background_task = asyncio.create_task(task)
        else:
            raise TypeError("register_task requires an awaitable task object")

        def _on_done(done_task: asyncio.Task[Any]) -> None:
            if done_task.cancelled():
                debug_logger = getattr(self.logger, "debug", None)
                if callable(debug_logger):
                    debug_logger(
                        "SDK background task cancelled: plugin_id={} desc={}",
                        self.plugin_id,
                        task_desc,
                    )
                return
            try:
                done_task.result()
            except asyncio.CancelledError:
                debug_logger = getattr(self.logger, "debug", None)
                if callable(debug_logger):
                    debug_logger(
                        "SDK background task cancelled: plugin_id={} desc={}",
                        self.plugin_id,
                        task_desc,
                    )
            except Exception:
                exception_logger = getattr(self.logger, "exception", None)
                if callable(exception_logger):
                    exception_logger(
                        "SDK background task failed: plugin_id={} desc={}",
                        self.plugin_id,
                        task_desc,
                    )

        background_task.add_done_callback(_on_done)
        return background_task

    async def _list_platform_instances(self) -> list[dict[str, Any]]:
        output = await self._proxy.call("platform.list_instances", {})
        items = output.get("platforms")
        if not isinstance(items, list):
            return []
        normalized: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            platform_id = str(item.get("id", "")).strip()
            platform_type = str(item.get("type", "")).strip()
            if not platform_id or not platform_type:
                continue
            normalized.append(
                {
                    "id": platform_id,
                    "name": str(item.get("name", platform_id)),
                    "type": platform_type,
                    "status": PlatformStatus.from_value(item.get("status")),
                }
            )
        return normalized

    def _build_platform_facade(
        self,
        platform_payload: dict[str, Any],
    ) -> PlatformCompatFacade:
        return PlatformCompatFacade(
            _ctx=self,
            id=str(platform_payload.get("id", "")),
            name=str(platform_payload.get("name", "")),
            type=str(platform_payload.get("type", "")),
            status=PlatformStatus.from_value(platform_payload.get("status")),
        )

    async def get_platform(self, platform_type: str) -> PlatformCompatFacade | None:
        target_type = str(platform_type).strip().lower()
        if not target_type:
            return None
        for item in await self._list_platform_instances():
            if str(item.get("type", "")).strip().lower() == target_type:
                return self._build_platform_facade(item)
        return None

    async def get_platform_inst(self, platform_id: str) -> PlatformCompatFacade | None:
        target_id = str(platform_id).strip()
        if not target_id:
            return None
        for item in await self._list_platform_instances():
            if str(item.get("id", "")).strip() == target_id:
                return self._build_platform_facade(item)
        return None
