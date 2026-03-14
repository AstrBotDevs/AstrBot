"""能力路由模块。

定义 CapabilityRouter 类，负责能力的注册、发现和执行路由。
能力是核心侧提供给插件侧调用的功能，如 LLM 聊天、存储、消息发送等。

核心概念：
    CapabilityDescriptor: 能力描述符，声明能力名称、输入输出 Schema 等
    CallHandler: 同步调用处理器，签名 (request_id, payload, cancel_token) -> dict
    StreamHandler: 流式调用处理器，签名 (request_id, payload, cancel_token) -> AsyncIterator
    FinalizeHandler: 流式结果聚合器，签名 (chunks) -> dict

内置能力：
    llm.chat: 同步 LLM 聊天（内置 echo 实现）
    llm.chat_raw: 同步 LLM 聊天（完整响应）
    llm.stream_chat: 流式 LLM 聊天
    memory.search: 搜索记忆
    memory.save: 保存记忆
    memory.save_with_ttl: 保存带过期时间的记忆
    memory.get: 读取单条记忆
    memory.get_many: 批量获取多条记忆
    memory.delete: 删除记忆
    memory.delete_many: 批量删除多条记忆
    memory.stats: 获取记忆统计信息
    db.get: 读取 KV 存储
    db.set: 写入 KV 存储
    db.delete: 删除 KV 存储
    db.list: 列出 KV 键
    db.get_many: 批量读取多个 KV 键
    db.set_many: 批量写入多个 KV 键
    db.watch: 订阅 KV 变更事件
    platform.send: 发送消息
    platform.send_image: 发送图片
    platform.send_chain: 发送消息链
    platform.get_members: 获取群成员
    http.register_api: 注册 HTTP 路由到插件 capability
    http.unregister_api: 注销 HTTP 路由
    http.list_apis: 查询已注册的 HTTP 路由
    metadata.get_plugin: 获取单个插件元数据
    metadata.list_plugins: 列出所有插件元数据
    metadata.get_plugin_config: 获取当前调用插件自己的配置

与旧版对比：
    旧版:
        - 无显式的能力声明系统
        - 通过 call_context_function 调用核心功能
        - 上下文函数名硬编码
        - 无输入输出 Schema 验证
        - 不支持流式能力

    新版 CapabilityRouter:
        - 使用 CapabilityDescriptor 声明能力
        - JSON Schema 验证输入输出
        - 支持同步和流式两种调用模式
        - 统一的错误处理
        - 能力命名规范: namespace.action

能力命名规范：
    - 格式: {namespace}.{action}
    - 内置能力命名空间: llm, memory, db, platform
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
import copy
import inspect
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from .._invocation_context import current_caller_plugin_id
from ..errors import AstrBotError
from ..protocol.descriptors import (
    BUILTIN_CAPABILITY_SCHEMAS,
    RESERVED_CAPABILITY_PREFIXES,
    CapabilityDescriptor,
    SessionRef,
)

CallHandler = Callable[[str, dict[str, Any], object], Awaitable[dict[str, Any]]]
FinalizeHandler = Callable[[list[dict[str, Any]]], dict[str, Any]]
CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(slots=True)
class StreamExecution:
    iterator: AsyncIterator[dict[str, Any]]
    finalize: FinalizeHandler
    collect_chunks: bool = True


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


class CapabilityRouter:
    def __init__(self) -> None:
        self._registrations: dict[str, _CapabilityRegistration] = {}
        self.db_store: dict[str, Any] = {}
        self.memory_store: dict[str, dict[str, Any]] = {}
        self.sent_messages: list[dict[str, Any]] = []
        self.http_api_store: list[dict[str, Any]] = []
        self._plugins: dict[str, _RegisteredPlugin] = {}
        self._db_watch_subscriptions: dict[
            str, tuple[str | None, asyncio.Queue[dict[str, Any]]]
        ] = {}
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
        self._plugins[name] = _RegisteredPlugin(
            metadata=normalized_metadata,
            config=dict(config or {}),
        )

    def set_plugin_enabled(self, name: str, enabled: bool) -> None:
        plugin = self._plugins.get(name)
        if plugin is None:
            return
        plugin.metadata["enabled"] = enabled

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
        return [
            entry.descriptor for entry in self._registrations.values() if entry.exposed
        ]

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
        if not CAPABILITY_NAME_PATTERN.fullmatch(descriptor.name):
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
            raise AstrBotError.invalid_input(f"{capability} 只能以 stream=true 调用")
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
    # Built-in capability registration
    # ------------------------------------------------------------------

    def _register_builtin_capabilities(self) -> None:
        """注册全部内建 capability。"""
        self._register_llm_capabilities()
        self._register_memory_capabilities()
        self._register_db_capabilities()
        self._register_platform_capabilities()
        self._register_http_capabilities()
        self._register_metadata_capabilities()

    def _builtin_descriptor(
        self,
        name: str,
        description: str,
        *,
        supports_stream: bool = False,
        cancelable: bool = False,
    ) -> CapabilityDescriptor:
        """构建内建 capability 描述符，schema 从注册表读取。"""
        schema = BUILTIN_CAPABILITY_SCHEMAS[name]
        return CapabilityDescriptor(
            name=name,
            description=description,
            input_schema=copy.deepcopy(schema["input"]),
            output_schema=copy.deepcopy(schema["output"]),
            supports_stream=supports_stream,
            cancelable=cancelable,
        )

    def _resolve_target(
        self, payload: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        """从 payload 解析 session + target。"""
        target_payload = payload.get("target")
        if isinstance(target_payload, dict):
            target = SessionRef.model_validate(target_payload)
            return target.session, target.to_payload()
        return str(payload.get("session", "")), None

    # ------------------------------------------------------------------
    # LLM handlers
    # ------------------------------------------------------------------

    async def _llm_chat(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        prompt = str(payload.get("prompt", ""))
        return {"text": f"Echo: {prompt}"}

    async def _llm_chat_raw(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        prompt = str(payload.get("prompt", ""))
        text = f"Echo: {prompt}"
        return {
            "text": text,
            "usage": {
                "input_tokens": len(prompt),
                "output_tokens": len(text),
            },
            "finish_reason": "stop",
            "tool_calls": [],
        }

    async def _llm_stream(
        self,
        _request_id: str,
        payload: dict[str, Any],
        token,
    ) -> AsyncIterator[dict[str, Any]]:  # type: ignore[override]
        text = f"Echo: {str(payload.get('prompt', ''))}"
        for char in text:
            token.raise_if_cancelled()
            await asyncio.sleep(0)
            yield {"text": char}

    def _register_llm_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("llm.chat", "发送对话请求，返回文本"),
            call_handler=self._llm_chat,
        )
        self.register(
            self._builtin_descriptor("llm.chat_raw", "发送对话请求，返回完整响应"),
            call_handler=self._llm_chat_raw,
        )
        self.register(
            self._builtin_descriptor(
                "llm.stream_chat",
                "流式对话",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._llm_stream,
            finalize=lambda chunks: {
                "text": "".join(item.get("text", "") for item in chunks)
            },
        )

    # ------------------------------------------------------------------
    # Memory handlers
    # ------------------------------------------------------------------

    async def _memory_search(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        query = str(payload.get("query", ""))
        items = [
            {"key": key, "value": value}
            for key, value in self.memory_store.items()
            if query in key or query in json.dumps(value, ensure_ascii=False)
        ]
        return {"items": items}

    async def _memory_save(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        key = str(payload.get("key", ""))
        value = payload.get("value")
        if not isinstance(value, dict):
            raise AstrBotError.invalid_input("memory.save 的 value 必须是 object")
        self.memory_store[key] = value
        return {}

    async def _memory_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return {"value": self.memory_store.get(str(payload.get("key", "")))}

    async def _memory_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self.memory_store.pop(str(payload.get("key", "")), None)
        return {}

    async def _memory_save_with_ttl(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        """保存带 TTL 的记忆项（测试实现，TTL 仅记录但不实际过期）。"""
        key = str(payload.get("key", ""))
        value = payload.get("value")
        ttl_seconds = payload.get("ttl_seconds", 0)
        if not isinstance(value, dict):
            raise AstrBotError.invalid_input(
                "memory.save_with_ttl 的 value 必须是 object"
            )
        # 在测试实现中，我们只存储值，TTL 由实际后端实现
        self.memory_store[key] = {"value": value, "ttl_seconds": ttl_seconds}
        return {}

    async def _memory_get_many(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        """批量获取多个记忆项。"""
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, (list, tuple)):
            raise AstrBotError.invalid_input("memory.get_many 的 keys 必须是数组")
        keys = [str(item) for item in keys_payload]
        items = []
        for key in keys:
            stored = self.memory_store.get(key)
            # 如果存储的是带 TTL 的结构，提取实际值
            if (
                isinstance(stored, dict)
                and "value" in stored
                and "ttl_seconds" in stored
            ):
                value = stored["value"]
            else:
                value = stored
            items.append({"key": key, "value": value})
        return {"items": items}

    async def _memory_delete_many(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        """批量删除多个记忆项。"""
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, (list, tuple)):
            raise AstrBotError.invalid_input("memory.delete_many 的 keys 必须是数组")
        keys = [str(item) for item in keys_payload]
        deleted_count = 0
        for key in keys:
            if key in self.memory_store:
                del self.memory_store[key]
                deleted_count += 1
        return {"deleted_count": deleted_count}

    async def _memory_stats(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        """获取记忆统计信息。"""
        total_items = len(self.memory_store)
        # 简单估算字节大小
        total_bytes = sum(
            len(str(key)) + len(str(value)) for key, value in self.memory_store.items()
        )
        return {"total_items": total_items, "total_bytes": total_bytes}

    def _register_memory_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("memory.search", "搜索记忆"),
            call_handler=self._memory_search,
        )
        self.register(
            self._builtin_descriptor("memory.save", "保存记忆"),
            call_handler=self._memory_save,
        )
        self.register(
            self._builtin_descriptor("memory.get", "读取单条记忆"),
            call_handler=self._memory_get,
        )
        self.register(
            self._builtin_descriptor("memory.delete", "删除记忆"),
            call_handler=self._memory_delete,
        )
        self.register(
            self._builtin_descriptor("memory.save_with_ttl", "保存带过期时间的记忆"),
            call_handler=self._memory_save_with_ttl,
        )
        self.register(
            self._builtin_descriptor("memory.get_many", "批量获取记忆"),
            call_handler=self._memory_get_many,
        )
        self.register(
            self._builtin_descriptor("memory.delete_many", "批量删除记忆"),
            call_handler=self._memory_delete_many,
        )
        self.register(
            self._builtin_descriptor("memory.stats", "获取记忆统计信息"),
            call_handler=self._memory_stats,
        )

    # ------------------------------------------------------------------
    # DB handlers
    # ------------------------------------------------------------------

    async def _db_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return {"value": self.db_store.get(str(payload.get("key", "")))}

    async def _db_set(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        key = str(payload.get("key", ""))
        value = payload.get("value")
        self.db_store[key] = value
        self._emit_db_change(op="set", key=key, value=value)
        return {}

    async def _db_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        key = str(payload.get("key", ""))
        self.db_store.pop(key, None)
        self._emit_db_change(op="delete", key=key, value=None)
        return {}

    async def _db_list(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        prefix = payload.get("prefix")
        keys = sorted(self.db_store.keys())
        if isinstance(prefix, str):
            keys = [item for item in keys if item.startswith(prefix)]
        return {"keys": keys}

    async def _db_get_many(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, (list, tuple)):
            raise AstrBotError.invalid_input("db.get_many 的 keys 必须是数组")
        keys = [str(item) for item in keys_payload]
        items = [{"key": key, "value": self.db_store.get(key)} for key in keys]
        return {"items": items}

    async def _db_set_many(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        items_payload = payload.get("items")
        if not isinstance(items_payload, (list, tuple)):
            raise AstrBotError.invalid_input("db.set_many 的 items 必须是数组")
        for entry in items_payload:
            if not isinstance(entry, dict):
                raise AstrBotError.invalid_input(
                    "db.set_many 的 items 必须是 object 数组"
                )
            key = str(entry.get("key", ""))
            value = entry.get("value")
            self.db_store[key] = value
            self._emit_db_change(op="set", key=key, value=value)
        return {}

    async def _db_watch(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> StreamExecution:
        prefix = payload.get("prefix")
        prefix_value: str | None
        if isinstance(prefix, str):
            prefix_value = prefix
        elif prefix is None:
            prefix_value = None
        else:
            raise AstrBotError.invalid_input("db.watch 的 prefix 必须是 string 或 null")

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._db_watch_subscriptions[request_id] = (prefix_value, queue)

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            try:
                while True:
                    yield await queue.get()
            finally:
                self._db_watch_subscriptions.pop(request_id, None)

        return StreamExecution(
            iterator=iterator(),
            finalize=lambda _chunks: {},
            collect_chunks=False,
        )

    def _register_db_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("db.get", "读取 KV"),
            call_handler=self._db_get,
        )
        self.register(
            self._builtin_descriptor("db.set", "写入 KV"),
            call_handler=self._db_set,
        )
        self.register(
            self._builtin_descriptor("db.delete", "删除 KV"),
            call_handler=self._db_delete,
        )
        self.register(
            self._builtin_descriptor("db.list", "列出 KV"),
            call_handler=self._db_list,
        )
        self.register(
            self._builtin_descriptor("db.get_many", "批量读取 KV"),
            call_handler=self._db_get_many,
        )
        self.register(
            self._builtin_descriptor("db.set_many", "批量写入 KV"),
            call_handler=self._db_set_many,
        )
        self.register(
            self._builtin_descriptor(
                "db.watch",
                "订阅 KV 变更",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._db_watch,
        )

    # ------------------------------------------------------------------
    # Platform handlers
    # ------------------------------------------------------------------

    async def _platform_send(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, target = self._resolve_target(payload)
        text = str(payload.get("text", ""))
        message_id = f"msg_{len(self.sent_messages) + 1}"
        sent = {"message_id": message_id, "session": session, "text": text}
        if target is not None:
            sent["target"] = target
        self.sent_messages.append(sent)
        return {"message_id": message_id}

    async def _platform_send_image(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, target = self._resolve_target(payload)
        image_url = str(payload.get("image_url", ""))
        message_id = f"img_{len(self.sent_messages) + 1}"
        sent = {
            "message_id": message_id,
            "session": session,
            "image_url": image_url,
        }
        if target is not None:
            sent["target"] = target
        self.sent_messages.append(sent)
        return {"message_id": message_id}

    async def _platform_send_chain(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, target = self._resolve_target(payload)
        chain = payload.get("chain")
        if not isinstance(chain, list) or not all(
            isinstance(item, dict) for item in chain
        ):
            raise AstrBotError.invalid_input(
                "platform.send_chain 的 chain 必须是 object 数组"
            )
        message_id = f"chain_{len(self.sent_messages) + 1}"
        sent = {
            "message_id": message_id,
            "session": session,
            "chain": [dict(item) for item in chain],
        }
        if target is not None:
            sent["target"] = target
        self.sent_messages.append(sent)
        return {"message_id": message_id}

    async def _platform_get_members(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, _target = self._resolve_target(payload)
        return {
            "members": [
                {"user_id": f"{session}:member-1", "nickname": "Member 1"},
                {"user_id": f"{session}:member-2", "nickname": "Member 2"},
            ]
        }

    def _register_platform_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("platform.send", "发送消息"),
            call_handler=self._platform_send,
        )
        self.register(
            self._builtin_descriptor("platform.send_image", "发送图片"),
            call_handler=self._platform_send_image,
        )
        self.register(
            self._builtin_descriptor("platform.send_chain", "发送消息链"),
            call_handler=self._platform_send_chain,
        )
        self.register(
            self._builtin_descriptor("platform.get_members", "获取群成员"),
            call_handler=self._platform_get_members,
        )

    # ------------------------------------------------------------------
    # HTTP handlers
    # ------------------------------------------------------------------

    async def _http_register_api(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        methods_payload = payload.get("methods")
        if not isinstance(methods_payload, list) or not all(
            isinstance(item, str) for item in methods_payload
        ):
            raise AstrBotError.invalid_input(
                "http.register_api 的 methods 必须是 string 数组"
            )

        route = str(payload.get("route", "")).strip()
        handler_capability = str(payload.get("handler_capability", "")).strip()
        if not route or not handler_capability:
            raise AstrBotError.invalid_input(
                "http.register_api 需要 route 和 handler_capability"
            )

        plugin_name = self._require_caller_plugin_id("http.register_api")
        methods = sorted({method.upper() for method in methods_payload if method})
        entry = {
            "route": route,
            "methods": methods,
            "handler_capability": handler_capability,
            "description": str(payload.get("description", "")),
            "plugin_id": plugin_name,
        }
        self.http_api_store = [
            item
            for item in self.http_api_store
            if not (
                item.get("route") == route
                and item.get("plugin_id") == entry["plugin_id"]
                and item.get("methods") == methods
            )
        ]
        self.http_api_store.append(entry)
        return {}

    async def _http_unregister_api(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        route = str(payload.get("route", "")).strip()
        methods_payload = payload.get("methods")
        if not isinstance(methods_payload, list) or not all(
            isinstance(item, str) for item in methods_payload
        ):
            raise AstrBotError.invalid_input(
                "http.unregister_api 的 methods 必须是 string 数组"
            )

        plugin_name = self._require_caller_plugin_id("http.unregister_api")
        methods = {method.upper() for method in methods_payload if method}
        updated: list[dict[str, Any]] = []
        for entry in self.http_api_store:
            if entry.get("route") != route:
                updated.append(entry)
                continue
            if entry.get("plugin_id") != plugin_name:
                updated.append(entry)
                continue
            if not methods:
                continue
            remaining_methods = [
                method for method in entry.get("methods", []) if method not in methods
            ]
            if remaining_methods:
                updated.append({**entry, "methods": remaining_methods})
        self.http_api_store = updated
        return {}

    async def _http_list_apis(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_name = self._require_caller_plugin_id("http.list_apis")
        apis = [
            dict(entry)
            for entry in self.http_api_store
            if entry.get("plugin_id") == plugin_name
        ]
        return {"apis": apis}

    def _register_http_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("http.register_api", "注册 HTTP 路由"),
            call_handler=self._http_register_api,
        )
        self.register(
            self._builtin_descriptor("http.unregister_api", "注销 HTTP 路由"),
            call_handler=self._http_unregister_api,
        )
        self.register(
            self._builtin_descriptor("http.list_apis", "列出 HTTP 路由"),
            call_handler=self._http_list_apis,
        )

    # ------------------------------------------------------------------
    # Metadata handlers
    # ------------------------------------------------------------------

    async def _metadata_get_plugin(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"plugin": None}
        return {"plugin": dict(plugin.metadata)}

    async def _metadata_list_plugins(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugins = [
            dict(self._plugins[name].metadata) for name in sorted(self._plugins.keys())
        ]
        return {"plugins": plugins}

    async def _metadata_get_plugin_config(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        name = str(payload.get("name", "")).strip()
        caller_plugin_id = self._require_caller_plugin_id("metadata.get_plugin_config")
        if name != caller_plugin_id:
            return {"config": None}
        plugin = self._plugins.get(name)
        if plugin is None:
            return {"config": None}
        return {"config": dict(plugin.config)}

    def _register_metadata_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("metadata.get_plugin", "获取单个插件元数据"),
            call_handler=self._metadata_get_plugin,
        )
        self.register(
            self._builtin_descriptor("metadata.list_plugins", "列出插件元数据"),
            call_handler=self._metadata_list_plugins,
        )
        self.register(
            self._builtin_descriptor(
                "metadata.get_plugin_config",
                "获取插件配置",
            ),
            call_handler=self._metadata_get_plugin_config,
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
