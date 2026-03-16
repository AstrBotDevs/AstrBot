"""能力路由模块。

定义 CapabilityRouter 类，负责能力的注册、发现和执行路由。
能力是核心侧提供给插件侧调用的功能，如 LLM 聊天、存储、消息发送等。

核心概念：
    CapabilityDescriptor: 能力描述符，声明能力名称、输入输出 Schema 等
    CallHandler: 同步调用处理器，签名 (request_id, payload, cancel_token) -> dict
    StreamHandler: 流式调用处理器，签名 (request_id, payload, cancel_token) -> AsyncIterator
    FinalizeHandler: 流式结果聚合器，签名 (chunks) -> dict

内置能力：
    LLM:
        llm.chat: 同步 LLM 聊天
        llm.chat_raw: 同步 LLM 聊天（完整响应）
        llm.stream_chat: 流式 LLM 聊天
    Memory:
        memory.search: 搜索记忆
        memory.save: 保存记忆
        memory.save_with_ttl: 保存带过期时间的记忆
        memory.get: 读取单条记忆
        memory.get_many: 批量获取多条记忆
        memory.delete: 删除记忆
        memory.delete_many: 批量删除多条记忆
        memory.stats: 获取记忆统计信息
    DB:
        db.get: 读取 KV 存储
        db.set: 写入 KV 存储
        db.delete: 删除 KV 存储
        db.list: 列出 KV 键
        db.get_many: 批量读取多个 KV 键
        db.set_many: 批量写入多个 KV 键
        db.watch: 订阅 KV 变更事件
    Platform:
        platform.send: 发送消息
        platform.send_image: 发送图片
        platform.send_chain: 发送消息链
        platform.send_by_session: 主动按会话发送消息链
        platform.get_group: 获取当前群信息
        platform.get_members: 获取群成员
    HTTP:
        http.register_api: 注册 HTTP 路由到插件 capability
        http.unregister_api: 注销 HTTP 路由
        http.list_apis: 查询已注册的 HTTP 路由
    Metadata:
        metadata.get_plugin: 获取单个插件元数据
        metadata.list_plugins: 列出所有插件元数据
        metadata.get_plugin_config: 获取当前调用插件自己的配置
    Provider:
        provider.get_using: 获取当前聊天 Provider
        provider.get_current_chat_provider_id: 获取当前聊天 Provider ID
        provider.list_all: 列出聊天 Providers
        provider.list_all_tts: 列出 TTS Providers
        provider.list_all_stt: 列出 STT Providers
        provider.list_all_embedding: 列出 Embedding Providers
        provider.list_all_rerank: 列出 Rerank Providers
        provider.get_using_tts: 获取当前 TTS Provider
        provider.get_using_stt: 获取当前 STT Provider
        provider.get_by_id: 按 ID 获取 Provider
        provider.stt.get_text: STT 转写
        provider.tts.get_audio: TTS 合成音频
        provider.tts.support_stream: 检查 TTS 原生流式支持
        provider.tts.get_audio_stream: 流式 TTS 音频输出
        provider.embedding.get_embedding: 获取单条向量
        provider.embedding.get_embeddings: 批量获取向量
        provider.embedding.get_dim: 获取向量维度
        provider.rerank.rerank: 文档重排序
    LLM Tool:
        llm_tool.manager.get: 获取 LLM 工具状态
        llm_tool.manager.activate: 激活 LLM 工具
        llm_tool.manager.deactivate: 停用 LLM 工具
        llm_tool.manager.add: 动态添加 LLM 工具
        llm_tool.manager.remove: 动态移除 LLM 工具
    Agent:
        agent.tool_loop.run: 运行 tool loop
        agent.registry.list: 列出 Agent 元数据
        agent.registry.get: 获取 Agent 元数据
    Registry:
        registry.get_handlers_by_event_type: 按事件类型列出 handler 元数据
        registry.get_handler_by_full_name: 按 full name 查询 handler 元数据
    Managers:
        persona.get / persona.list / persona.create / persona.update / persona.delete
        conversation.new / conversation.switch / conversation.delete
        conversation.get / conversation.list / conversation.update
        kb.get / kb.create / kb.delete

能力命名规范：
    - 格式: {namespace}.{action} 或 {namespace}.{sub_namespace}.{action}
    - 内置能力命名空间: llm, memory, db, platform, http, metadata, provider, llm_tool, agent, registry
    - 保留命名空间前缀: handler., system., internal.

使用示例：
    router = CapabilityRouter()

    # 注册同步能力
    router.register(
        CapabilityDescriptor(
            name="my_plugin.calculate",
            description="执行计算",
            input_schema={"type": "object", "properties": {"x": {"type": "number"}}},
            output_schema={"type": "object", "properties": {"result": {"type": "number"}}},
        ),
        call_handler=my_calculate,
    )

    # 注册流式能力
    async def stream_data(request_id, payload, token):
        for i in range(10):
            yield {"index": i}

    router.register(
        CapabilityDescriptor(
            name="my_plugin.stream",
            description="流式数据",
            supports_stream=True,
            cancelable=True,
        ),
        stream_handler=stream_data,
        finalize=lambda chunks: {"count": len(chunks)},
    )

    # 执行能力
    result = await router.execute("my_plugin.calculate", {"x": 42}, stream=False, ...)
    stream_result = await router.execute("my_plugin.stream", {}, stream=True, ...)
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .._invocation_context import current_caller_plugin_id
from ..errors import AstrBotError
from ..protocol.descriptors import (
    RESERVED_CAPABILITY_PREFIXES,
    CapabilityDescriptor,
)
from ._capability_router_builtins import BuiltinCapabilityRouterMixin
from ._streaming import StreamExecution

CallHandler = Callable[[str, dict[str, Any], object], Awaitable[dict[str, Any]]]
FinalizeHandler = Callable[[list[dict[str, Any]]], dict[str, Any]]
CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$")


StreamHandler = Callable[
    [str, dict[str, Any], object],
    AsyncIterator[dict[str, Any]]
    | StreamExecution
    | Awaitable[AsyncIterator[dict[str, Any]] | StreamExecution],
]


@dataclass(slots=True)
class _CapabilityRegistration:
    descriptor: CapabilityDescriptor
    call_handler: CallHandler | None = None
    stream_handler: StreamHandler | None = None
    finalize: FinalizeHandler | None = None
    exposed: bool = True


@dataclass(slots=True)
class _RegisteredPlugin:
    metadata: dict[str, Any]
    config: dict[str, Any]
    handlers: list[dict[str, Any]]
    llm_tools: dict[str, dict[str, Any]] = field(default_factory=dict)
    active_llm_tools: set[str] = field(default_factory=set)
    agents: dict[str, dict[str, Any]] = field(default_factory=dict)


class CapabilityRouter(BuiltinCapabilityRouterMixin):
    def __init__(self) -> None:
        self._registrations: dict[str, _CapabilityRegistration] = {}
        self.db_store: dict[str, Any] = {}
        self.memory_store: dict[str, dict[str, Any]] = {}
        self.sent_messages: list[dict[str, Any]] = []
        self.event_actions: list[dict[str, Any]] = []
        self._event_streams: dict[str, dict[str, Any]] = {}
        self.http_api_store: list[dict[str, Any]] = []
        self._plugins: dict[str, _RegisteredPlugin] = {}
        self._request_overlays: dict[str, dict[str, Any]] = {}
        self._provider_catalog: dict[str, list[dict[str, Any]]] = {
            "chat": [
                {
                    "id": "mock-chat-provider",
                    "model": "mock-chat-model",
                    "type": "mock",
                    "provider_type": "chat_completion",
                }
            ],
            "tts": [
                {
                    "id": "mock-tts-provider",
                    "model": "mock-tts-model",
                    "type": "mock",
                    "provider_type": "text_to_speech",
                }
            ],
            "stt": [
                {
                    "id": "mock-stt-provider",
                    "model": "mock-stt-model",
                    "type": "mock",
                    "provider_type": "speech_to_text",
                }
            ],
            "embedding": [
                {
                    "id": "mock-embedding-provider",
                    "model": "mock-embedding-model",
                    "type": "mock",
                    "provider_type": "embedding",
                }
            ],
            "rerank": [
                {
                    "id": "mock-rerank-provider",
                    "model": "mock-rerank-model",
                    "type": "mock",
                    "provider_type": "rerank",
                }
            ],
        }
        self._provider_configs: dict[str, dict[str, Any]] = {
            str(item["id"]): {**item, "enable": True}
            for providers in self._provider_catalog.values()
            for item in providers
        }
        self._active_provider_ids: dict[str, str | None] = {
            kind: providers[0]["id"] if providers else None
            for kind, providers in self._provider_catalog.items()
        }
        self._provider_change_subscriptions: dict[
            str, asyncio.Queue[dict[str, Any]]
        ] = {}
        self._system_data_root = Path.cwd() / ".astrbot_sdk_testing" / "plugin_data"
        self._session_waiters: dict[str, set[str]] = {}
        self._db_watch_subscriptions: dict[
            str, tuple[str | None, asyncio.Queue[dict[str, Any]]]
        ] = {}
        self._session_plugin_configs: dict[str, dict[str, Any]] = {}
        self._session_service_configs: dict[str, dict[str, Any]] = {}
        self._dynamic_command_routes: dict[str, list[dict[str, Any]]] = {}
        self._file_token_store: dict[str, str] = {}
        self._persona_store: dict[str, dict[str, Any]] = {}
        self._conversation_store: dict[str, dict[str, Any]] = {}
        self._session_current_conversation_ids: dict[str, str] = {}
        self._kb_store: dict[str, dict[str, Any]] = {}
        self._platform_instances: list[dict[str, Any]] = [
            {
                "id": "mock-platform",
                "name": "Mock Platform",
                "type": "mock",
                "status": "running",
            }
        ]
        self._register_builtin_capabilities()

    def upsert_plugin(
        self,
        *,
        metadata: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> None:
        name = str(metadata.get("name", "")).strip()
        if not name:
            raise ValueError("plugin metadata must include a non-empty name")
        normalized_metadata = dict(metadata)
        normalized_metadata.setdefault("display_name", name)
        normalized_metadata.setdefault("description", "")
        normalized_metadata.setdefault("author", "")
        normalized_metadata.setdefault("version", "0.0.0")
        normalized_metadata.setdefault("enabled", True)
        normalized_metadata.setdefault("reserved", False)
        normalized_metadata.setdefault("support_platforms", [])
        normalized_metadata.setdefault("astrbot_version", None)
        self._plugins[name] = _RegisteredPlugin(
            metadata=normalized_metadata,
            config=dict(config or {}),
            handlers=[],
        )

    def set_plugin_handlers(
        self,
        name: str,
        handlers: list[dict[str, Any]],
    ) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            return
        plugin.handlers = [dict(item) for item in handlers]
        valid_handlers = {
            str(item.get("handler_full_name", "")).strip()
            for item in plugin.handlers
            if isinstance(item, dict)
        }
        if not valid_handlers:
            self._dynamic_command_routes.pop(name, None)
            return
        routes = self._dynamic_command_routes.get(name)
        if routes is None:
            return
        self._dynamic_command_routes[name] = [
            dict(item)
            for item in routes
            if str(item.get("handler_full_name", "")).strip() in valid_handlers
        ]
        if not self._dynamic_command_routes[name]:
            self._dynamic_command_routes.pop(name, None)

    def set_plugin_enabled(self, name: str, enabled: bool) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            return
        plugin.metadata["enabled"] = enabled

    def register_dynamic_command_route(
        self,
        *,
        plugin_id: str,
        command_name: str,
        handler_full_name: str,
        desc: str = "",
        priority: int = 0,
        use_regex: bool = False,
    ) -> None:
        command_text = str(command_name).strip()
        if not command_text:
            raise AstrBotError.invalid_input("command_name must not be empty")
        handler_text = str(handler_full_name).strip()
        if not handler_text:
            raise AstrBotError.invalid_input("handler_full_name must not be empty")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            raise AstrBotError.invalid_input(f"Unknown plugin: {plugin_id}")
        if not self._plugin_has_handler(plugin_id, handler_text):
            raise AstrBotError.invalid_input(
                "handler_full_name must belong to the caller plugin and exist"
            )
        route = {
            "plugin_name": plugin_id,
            "command_name": command_text,
            "handler_full_name": handler_text,
            "desc": str(desc),
            "priority": int(priority),
            "use_regex": bool(use_regex),
        }
        routes = [
            item
            for item in self._dynamic_command_routes.get(plugin_id, [])
            if str(item.get("command_name", "")).strip() != command_text
            or bool(item.get("use_regex", False)) != bool(use_regex)
        ]
        routes.append(route)
        self._dynamic_command_routes[plugin_id] = routes

    def list_dynamic_command_routes(self, plugin_id: str) -> list[dict[str, Any]]:
        return [dict(item) for item in self._dynamic_command_routes.get(plugin_id, [])]

    def remove_dynamic_command_routes_for_plugin(self, plugin_id: str) -> None:
        self._dynamic_command_routes.pop(plugin_id, None)

    def set_platform_instances(self, instances: list[dict[str, Any]]) -> None:
        normalized: list[dict[str, Any]] = []
        for item in instances:
            if not isinstance(item, dict):
                continue
            platform_id = str(item.get("id", "")).strip()
            platform_type = str(item.get("type", "")).strip()
            if not platform_id or not platform_type:
                continue
            errors = item.get("errors")
            last_error = item.get("last_error")
            stats = item.get("stats")
            meta = item.get("meta")
            normalized.append(
                {
                    "id": platform_id,
                    "name": str(item.get("name", platform_id)),
                    "type": platform_type,
                    "status": str(item.get("status", "unknown")),
                    "errors": [
                        dict(error) for error in errors if isinstance(error, dict)
                    ]
                    if isinstance(errors, list)
                    else [],
                    "last_error": (
                        dict(last_error) if isinstance(last_error, dict) else None
                    ),
                    "unified_webhook": bool(item.get("unified_webhook", False)),
                    "stats": dict(stats) if isinstance(stats, dict) else None,
                    "meta": dict(meta) if isinstance(meta, dict) else {},
                    "started_at": item.get("started_at"),
                }
            )
        self._platform_instances = normalized

    def get_platform_instances(self) -> list[dict[str, Any]]:
        return [dict(item) for item in self._platform_instances]

    def _plugin_has_handler(self, plugin_id: str, handler_full_name: str) -> bool:
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return False
        handler_name = str(handler_full_name).strip()
        if not handler_name:
            return False
        for handler in plugin.handlers:
            if not isinstance(handler, dict):
                continue
            if str(handler.get("handler_full_name", "")).strip() == handler_name:
                return True
        return False

    def set_plugin_llm_tools(
        self,
        name: str,
        tools: list[dict[str, Any]],
    ) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            return
        plugin.llm_tools = {
            str(item.get("name", "")): dict(item)
            for item in tools
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }
        plugin.active_llm_tools = {
            tool_name
            for tool_name, item in plugin.llm_tools.items()
            if bool(item.get("active", True))
        }

    def set_plugin_agents(
        self,
        name: str,
        agents: list[dict[str, Any]],
    ) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            return
        plugin.agents = {
            str(item.get("name", "")): dict(item)
            for item in agents
            if isinstance(item, dict) and str(item.get("name", "")).strip()
        }

    def set_provider_catalog(
        self,
        kind: str,
        providers: list[dict[str, Any]],
        *,
        active_id: str | None = None,
    ) -> None:
        self._provider_catalog[kind] = [
            dict(item)
            for item in providers
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ]
        for item in self._provider_catalog[kind]:
            provider_id = str(item.get("id", "")).strip()
            if not provider_id:
                continue
            self._provider_configs[provider_id] = {**item, "enable": True}
        if active_id is not None:
            self._active_provider_ids[kind] = active_id
        else:
            catalog = self._provider_catalog[kind]
            self._active_provider_ids[kind] = catalog[0]["id"] if catalog else None

    def emit_provider_change(
        self,
        provider_id: str,
        provider_type: str,
        umo: str | None = None,
    ) -> None:
        event = {
            "provider_id": str(provider_id),
            "provider_type": str(provider_type),
            "umo": str(umo) if umo is not None else None,
        }
        for queue in list(self._provider_change_subscriptions.values()):
            queue.put_nowait(dict(event))

    def record_platform_error(
        self,
        platform_id: str,
        message: str,
        *,
        traceback: str | None = None,
    ) -> None:
        for item in self._platform_instances:
            if str(item.get("id", "")) != str(platform_id):
                continue
            error = {
                "message": str(message),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "traceback": str(traceback) if traceback is not None else None,
            }
            errors = item.setdefault("errors", [])
            if isinstance(errors, list):
                errors.append(error)
            item["last_error"] = error
            item["status"] = "error"
            return

    def set_platform_stats(self, platform_id: str, stats: dict[str, Any]) -> None:
        for item in self._platform_instances:
            if str(item.get("id", "")) != str(platform_id):
                continue
            item["stats"] = dict(stats)
            return

    def set_session_plugin_config(
        self,
        session_id: str,
        *,
        enabled_plugins: list[str] | None = None,
        disabled_plugins: list[str] | None = None,
    ) -> None:
        config: dict[str, Any] = {}
        if enabled_plugins is not None:
            config["enabled_plugins"] = [str(item) for item in enabled_plugins]
        if disabled_plugins is not None:
            config["disabled_plugins"] = [str(item) for item in disabled_plugins]
        self._session_plugin_configs[str(session_id)] = config

    def set_session_service_config(
        self,
        session_id: str,
        *,
        llm_enabled: bool | None = None,
        tts_enabled: bool | None = None,
    ) -> None:
        config: dict[str, Any] = {}
        if llm_enabled is not None:
            config["llm_enabled"] = bool(llm_enabled)
        if tts_enabled is not None:
            config["tts_enabled"] = bool(tts_enabled)
        self._session_service_configs[str(session_id)] = config

    def remove_http_apis_for_plugin(self, plugin_id: str) -> None:
        self.http_api_store = [
            entry
            for entry in self.http_api_store
            if entry.get("plugin_id") != plugin_id
        ]

    @staticmethod
    def _require_caller_plugin_id(capability_name: str) -> str:
        caller_plugin_id = current_caller_plugin_id()
        if caller_plugin_id:
            return caller_plugin_id
        raise AstrBotError.invalid_input(
            f"{capability_name} 只能在插件运行时上下文中调用"
        )

    def _emit_db_change(self, *, op: str, key: str, value: Any | None) -> None:
        event = {"op": op, "key": key, "value": value}
        for prefix, queue in list(self._db_watch_subscriptions.values()):
            if prefix is not None and not key.startswith(prefix):
                continue
            queue.put_nowait(event)

    def descriptors(self) -> list[CapabilityDescriptor]:
        return [entry.descriptor for entry in self._registrations.values()]

    def contains(self, name: str) -> bool:
        return name in self._registrations

    def unregister(self, name: str) -> None:
        self._registrations.pop(name, None)

    def register(
        self,
        descriptor: CapabilityDescriptor,
        *,
        call_handler: CallHandler | None = None,
        stream_handler: StreamHandler | None = None,
        finalize: FinalizeHandler | None = None,
        exposed: bool = True,
    ) -> None:
        is_internal_reserved = not exposed and descriptor.name.startswith(
            RESERVED_CAPABILITY_PREFIXES
        )
        if (
            not CAPABILITY_NAME_PATTERN.fullmatch(descriptor.name)
            and not is_internal_reserved
        ):
            raise ValueError(
                f"capability 名称必须匹配 {{namespace}}.{{method}}：{descriptor.name}"
            )
        if exposed and descriptor.name.startswith(RESERVED_CAPABILITY_PREFIXES):
            raise ValueError(
                f"保留 capability 命名空间仅供框架内部使用：{descriptor.name}"
            )
        self._registrations[descriptor.name] = _CapabilityRegistration(
            descriptor=descriptor,
            call_handler=call_handler,
            stream_handler=stream_handler,
            finalize=finalize,
            exposed=exposed,
        )

    async def execute(
        self,
        capability: str,
        payload: dict[str, Any],
        *,
        stream: bool,
        cancel_token,
        request_id: str,
    ) -> dict[str, Any] | StreamExecution:
        registration = self._registrations.get(capability)
        if registration is None:
            raise AstrBotError.capability_not_found(capability)

        self._validate_schema_with_context(
            capability=capability,
            phase="输入",
            schema=registration.descriptor.input_schema,
            payload=payload,
        )
        if stream:
            if registration.stream_handler is None:
                raise AstrBotError.invalid_input(f"{capability} 不支持 stream=true")
            raw_execution = registration.stream_handler(
                request_id, payload, cancel_token
            )
            if inspect.isawaitable(raw_execution):
                raw_execution = await raw_execution
            if isinstance(raw_execution, StreamExecution):
                return self._wrap_stream_execution(
                    registration.descriptor,
                    raw_execution,
                )
            finalize = registration.finalize or (lambda chunks: {"items": chunks})
            return self._wrap_stream_execution(
                registration.descriptor,
                StreamExecution(
                    iterator=raw_execution,
                    finalize=finalize,
                ),
            )

        if registration.call_handler is None:
            raise AstrBotError.invalid_input(
                f"{capability} 只能以 stream=true 调用，registration.call_handler 为 None"
            )
        output = await registration.call_handler(request_id, payload, cancel_token)
        self._validate_schema_with_context(
            capability=capability,
            phase="输出",
            schema=registration.descriptor.output_schema,
            payload=output,
        )
        return output

    def _wrap_stream_execution(
        self,
        descriptor: CapabilityDescriptor,
        execution: StreamExecution,
    ) -> StreamExecution:
        def validated_finalize(chunks: list[dict[str, Any]]) -> dict[str, Any]:
            output = execution.finalize(chunks)
            self._validate_schema_with_context(
                capability=descriptor.name,
                phase="输出",
                schema=descriptor.output_schema,
                payload=output,
            )
            return output

        return StreamExecution(
            iterator=execution.iterator,
            finalize=validated_finalize,
            collect_chunks=execution.collect_chunks,
        )

    # ------------------------------------------------------------------
    # Schema validation
    # ------------------------------------------------------------------

    def _validate_schema(
        self,
        schema: dict[str, Any] | None,
        payload: Any,
    ) -> None:
        if not isinstance(schema, dict) or not schema:
            return
        self._validate_value(schema, payload, path="")

    def _validate_schema_with_context(
        self,
        *,
        capability: str,
        phase: str,
        schema: dict[str, Any] | None,
        payload: Any,
    ) -> None:
        try:
            self._validate_schema(schema, payload)
        except AstrBotError as exc:
            if exc.code != "invalid_input":
                raise
            raise AstrBotError.invalid_input(
                f"capability '{capability}' 的{phase}校验失败：{exc.message}",
                hint=(
                    f"请检查 capability '{capability}' 的{phase.lower()}是否符合声明的 schema"
                ),
            ) from exc

    def _validate_value(
        self,
        schema: dict[str, Any],
        value: Any,
        *,
        path: str,
    ) -> None:
        any_of = schema.get("anyOf")
        if isinstance(any_of, list):
            for candidate in any_of:
                if not isinstance(candidate, dict):
                    continue
                try:
                    self._validate_value(candidate, value, path=path)
                    return
                except AstrBotError:
                    continue
            raise AstrBotError.invalid_input(
                f"{self._field_label(path)} 不符合允许的 schema 约束，"
                f"实际收到 {self._value_type_name(value)}"
            )

        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            raise AstrBotError.invalid_input(
                f"{self._field_label(path)} 必须是 {enum}，实际收到 {value!r}"
            )

        schema_type = schema.get("type")
        if schema_type == "object":
            if not isinstance(value, dict):
                if not path:
                    raise AstrBotError.invalid_input(
                        f"输入必须是 object，实际收到 {self._value_type_name(value)}"
                    )
                raise AstrBotError.invalid_input(
                    f"{self._field_label(path)} 必须是 object，"
                    f"实际收到 {self._value_type_name(value)}"
                )
            properties = schema.get("properties", {})
            required_fields = schema.get("required", [])
            for field_name in required_fields:
                field_path = self._join_path(path, str(field_name))
                if field_name not in value:
                    raise AstrBotError.invalid_input(f"缺少必填字段：{field_path}")
                field_schema = self._property_schema(properties, field_name)
                if value[field_name] is None and not self._schema_allows_null(
                    field_schema
                ):
                    raise AstrBotError.invalid_input(f"缺少必填字段：{field_path}")
                self._validate_value(
                    field_schema,
                    value[field_name],
                    path=field_path,
                )
            for field_name, field_value in value.items():
                field_schema = properties.get(field_name)
                if isinstance(field_schema, dict):
                    self._validate_value(
                        field_schema,
                        field_value,
                        path=self._join_path(path, str(field_name)),
                    )
            return

        if schema_type == "array":
            if not isinstance(value, list):
                raise AstrBotError.invalid_input(
                    f"{self._field_label(path)} 必须是 array，"
                    f"实际收到 {self._value_type_name(value)}"
                )
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                for index, item in enumerate(value):
                    self._validate_value(
                        item_schema,
                        item,
                        path=self._index_path(path, index),
                    )
            return

        if schema_type == "string":
            if not isinstance(value, str):
                raise AstrBotError.invalid_input(
                    f"{self._field_label(path)} 必须是 string，"
                    f"实际收到 {self._value_type_name(value)}"
                )
            return

        if schema_type == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise AstrBotError.invalid_input(
                    f"{self._field_label(path)} 必须是 integer，"
                    f"实际收到 {self._value_type_name(value)}"
                )
            return

        if schema_type == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise AstrBotError.invalid_input(
                    f"{self._field_label(path)} 必须是 number，"
                    f"实际收到 {self._value_type_name(value)}"
                )
            return

        if schema_type == "boolean":
            if not isinstance(value, bool):
                raise AstrBotError.invalid_input(
                    f"{self._field_label(path)} 必须是 boolean，"
                    f"实际收到 {self._value_type_name(value)}"
                )
            return

        if schema_type == "null":
            if value is not None:
                raise AstrBotError.invalid_input(
                    f"{self._field_label(path)} 必须是 null，"
                    f"实际收到 {self._value_type_name(value)}"
                )
            return

    @staticmethod
    def _field_label(path: str) -> str:
        if not path:
            return "输入"
        return f"字段 {path}"

    @staticmethod
    def _join_path(path: str, field_name: str) -> str:
        if not path:
            return field_name
        return f"{path}.{field_name}"

    @staticmethod
    def _index_path(path: str, index: int) -> str:
        return f"{path}[{index}]" if path else f"[{index}]"

    @staticmethod
    def _property_schema(
        properties: Any,
        field_name: str,
    ) -> dict[str, Any]:
        if not isinstance(properties, dict):
            return {}
        field_schema = properties.get(field_name)
        if isinstance(field_schema, dict):
            return field_schema
        return {}

    @staticmethod
    def _schema_allows_null(field_schema: Any) -> bool:
        if not isinstance(field_schema, dict):
            return False
        if field_schema.get("type") == "null":
            return True
        any_of = field_schema.get("anyOf")
        if not isinstance(any_of, list):
            return False
        return any(
            isinstance(candidate, dict) and candidate.get("type") == "null"
            for candidate in any_of
        )

    @staticmethod
    def _value_type_name(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "boolean"
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            return "number"
        if isinstance(value, str):
            return "string"
        if isinstance(value, list):
            return "array"
        if isinstance(value, dict):
            return "object"
        return type(value).__name__
