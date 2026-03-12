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
    memory.get: 读取单条记忆
    memory.delete: 删除记忆
    db.get: 读取 KV 存储
    db.set: 写入 KV 存储
    db.delete: 删除 KV 存储
    db.list: 列出 KV 键
    platform.send: 发送消息
    platform.send_image: 发送图片
    platform.send_chain: 发送消息链
    platform.get_members: 获取群成员

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
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..errors import AstrBotError
from ..protocol.descriptors import (
    BUILTIN_CAPABILITY_SCHEMAS,
    CapabilityDescriptor,
    RESERVED_CAPABILITY_PREFIXES,
)

CallHandler = Callable[[str, dict[str, Any], object], Awaitable[dict[str, Any]]]
StreamHandler = Callable[[str, dict[str, Any], object], AsyncIterator[dict[str, Any]]]
FinalizeHandler = Callable[[list[dict[str, Any]]], dict[str, Any]]
CAPABILITY_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")


@dataclass(slots=True)
class StreamExecution:
    iterator: AsyncIterator[dict[str, Any]]
    finalize: FinalizeHandler


@dataclass(slots=True)
class _CapabilityRegistration:
    descriptor: CapabilityDescriptor
    call_handler: CallHandler | None = None
    stream_handler: StreamHandler | None = None
    finalize: FinalizeHandler | None = None
    exposed: bool = True


class CapabilityRouter:
    def __init__(self) -> None:
        self._registrations: dict[str, _CapabilityRegistration] = {}
        self.db_store: dict[str, Any] = {}
        self.memory_store: dict[str, dict[str, Any]] = {}
        self.sent_messages: list[dict[str, Any]] = []
        self._register_builtin_capabilities()

    def descriptors(self) -> list[CapabilityDescriptor]:
        return [
            entry.descriptor for entry in self._registrations.values() if entry.exposed
        ]

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

        self._validate_schema(registration.descriptor.input_schema, payload)
        if stream:
            if registration.stream_handler is None:
                raise AstrBotError.invalid_input(f"{capability} 不支持 stream=true")
            finalize = registration.finalize or (lambda chunks: {"items": chunks})
            return StreamExecution(
                iterator=registration.stream_handler(request_id, payload, cancel_token),
                finalize=finalize,
            )

        if registration.call_handler is None:
            raise AstrBotError.invalid_input(f"{capability} 只能以 stream=true 调用")
        output = await registration.call_handler(request_id, payload, cancel_token)
        self._validate_schema(registration.descriptor.output_schema, output)
        return output

    def _register_builtin_capabilities(self) -> None:
        def builtin_descriptor(
            name: str,
            description: str,
            *,
            supports_stream: bool = False,
            cancelable: bool = False,
        ) -> CapabilityDescriptor:
            schema = BUILTIN_CAPABILITY_SCHEMAS[name]
            return CapabilityDescriptor(
                name=name,
                description=description,
                input_schema=copy.deepcopy(schema["input"]),
                output_schema=copy.deepcopy(schema["output"]),
                supports_stream=supports_stream,
                cancelable=cancelable,
            )

        async def llm_chat(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            prompt = str(payload.get("prompt", ""))
            return {"text": f"Echo: {prompt}"}

        async def llm_chat_raw(
            _request_id: str, payload: dict[str, Any], _token
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

        async def llm_stream(
            _request_id: str,
            payload: dict[str, Any],
            token,
        ) -> AsyncIterator[dict[str, Any]]:
            text = f"Echo: {str(payload.get('prompt', ''))}"
            for char in text:
                token.raise_if_cancelled()
                await asyncio.sleep(0)
                yield {"text": char}

        async def memory_search(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            query = str(payload.get("query", ""))
            items = [
                {"key": key, "value": value}
                for key, value in self.memory_store.items()
                if query in key or query in json.dumps(value, ensure_ascii=False)
            ]
            return {"items": items}

        async def memory_save(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            key = str(payload.get("key", ""))
            value = payload.get("value")
            if not isinstance(value, dict):
                raise AstrBotError.invalid_input("memory.save 的 value 必须是 object")
            self.memory_store[key] = value
            return {}

        async def memory_get(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            return {"value": self.memory_store.get(str(payload.get("key", "")))}

        async def memory_delete(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            self.memory_store.pop(str(payload.get("key", "")), None)
            return {}

        async def db_get(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            return {"value": self.db_store.get(str(payload.get("key", "")))}

        async def db_set(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            key = str(payload.get("key", ""))
            self.db_store[key] = payload.get("value")
            return {}

        async def db_delete(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            self.db_store.pop(str(payload.get("key", "")), None)
            return {}

        async def db_list(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            prefix = payload.get("prefix")
            keys = sorted(self.db_store.keys())
            if isinstance(prefix, str):
                keys = [item for item in keys if item.startswith(prefix)]
            return {"keys": keys}

        async def platform_send(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            session = str(payload.get("session", ""))
            text = str(payload.get("text", ""))
            message_id = f"msg_{len(self.sent_messages) + 1}"
            self.sent_messages.append(
                {
                    "message_id": message_id,
                    "session": session,
                    "text": text,
                }
            )
            return {"message_id": message_id}

        async def platform_send_image(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            session = str(payload.get("session", ""))
            image_url = str(payload.get("image_url", ""))
            message_id = f"img_{len(self.sent_messages) + 1}"
            self.sent_messages.append(
                {
                    "message_id": message_id,
                    "session": session,
                    "image_url": image_url,
                }
            )
            return {"message_id": message_id}

        async def platform_send_chain(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            session = str(payload.get("session", ""))
            chain = payload.get("chain")
            if not isinstance(chain, list) or not all(
                isinstance(item, dict) for item in chain
            ):
                raise AstrBotError.invalid_input(
                    "platform.send_chain 的 chain 必须是 object 数组"
                )
            message_id = f"chain_{len(self.sent_messages) + 1}"
            self.sent_messages.append(
                {
                    "message_id": message_id,
                    "session": session,
                    "chain": [dict(item) for item in chain],
                }
            )
            return {"message_id": message_id}

        async def platform_get_members(
            _request_id: str, payload: dict[str, Any], _token
        ) -> dict[str, Any]:
            session = str(payload.get("session", ""))
            return {
                "members": [
                    {"user_id": f"{session}:member-1", "nickname": "Member 1"},
                    {"user_id": f"{session}:member-2", "nickname": "Member 2"},
                ]
            }

        self.register(
            builtin_descriptor("llm.chat", "发送对话请求，返回文本"),
            call_handler=llm_chat,
        )
        self.register(
            builtin_descriptor("llm.chat_raw", "发送对话请求，返回完整响应"),
            call_handler=llm_chat_raw,
        )
        self.register(
            builtin_descriptor(
                "llm.stream_chat",
                "流式对话",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=llm_stream,
            finalize=lambda chunks: {
                "text": "".join(item.get("text", "") for item in chunks)
            },
        )
        self.register(
            builtin_descriptor("memory.search", "搜索记忆"),
            call_handler=memory_search,
        )
        self.register(
            builtin_descriptor("memory.save", "保存记忆"),
            call_handler=memory_save,
        )
        self.register(
            builtin_descriptor("memory.get", "读取单条记忆"),
            call_handler=memory_get,
        )
        self.register(
            builtin_descriptor("memory.delete", "删除记忆"),
            call_handler=memory_delete,
        )
        self.register(
            builtin_descriptor("db.get", "读取 KV"),
            call_handler=db_get,
        )
        self.register(
            builtin_descriptor("db.set", "写入 KV"),
            call_handler=db_set,
        )
        self.register(
            builtin_descriptor("db.delete", "删除 KV"),
            call_handler=db_delete,
        )
        self.register(
            builtin_descriptor("db.list", "列出 KV"),
            call_handler=db_list,
        )
        self.register(
            builtin_descriptor("platform.send", "发送消息"),
            call_handler=platform_send,
        )
        self.register(
            builtin_descriptor("platform.send_image", "发送图片"),
            call_handler=platform_send_image,
        )
        self.register(
            builtin_descriptor("platform.send_chain", "发送消息链"),
            call_handler=platform_send_chain,
        )
        self.register(
            builtin_descriptor("platform.get_members", "获取群成员"),
            call_handler=platform_get_members,
        )

    def _validate_schema(
        self,
        schema: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> None:
        def schema_allows_null(field_schema: Any) -> bool:
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

        if schema is None:
            return
        if schema.get("type") == "object" and not isinstance(payload, dict):
            raise AstrBotError.invalid_input("输入必须是 object")
        properties = schema.get("properties", {})
        for field_name in schema.get("required", []):
            if field_name not in payload:
                raise AstrBotError.invalid_input(f"缺少必填字段：{field_name}")
            if payload[field_name] is None and not schema_allows_null(
                properties.get(field_name)
            ):
                raise AstrBotError.invalid_input(f"缺少必填字段：{field_name}")
