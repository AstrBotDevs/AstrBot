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
import inspect
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
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
CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


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
        self._system_data_root = Path.cwd() / ".astrbot_sdk_testing" / "plugin_data"
        self._session_waiters: dict[str, set[str]] = {}
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
