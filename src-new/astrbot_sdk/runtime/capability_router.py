from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..errors import AstrBotError
from ..protocol.descriptors import CapabilityDescriptor

CallHandler = Callable[[str, dict[str, Any], object], Awaitable[dict[str, Any]]]
StreamHandler = Callable[[str, dict[str, Any], object], AsyncIterator[dict[str, Any]]]
FinalizeHandler = Callable[[list[dict[str, Any]]], dict[str, Any]]


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
        self.db_store: dict[str, dict[str, Any]] = {}
        self.memory_store: dict[str, dict[str, Any]] = {}
        self.sent_messages: list[dict[str, Any]] = []
        self._register_builtin_capabilities()

    def descriptors(self) -> list[CapabilityDescriptor]:
        return [
            entry.descriptor
            for entry in self._registrations.values()
            if entry.exposed
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
        def obj_schema(required: list[str], **properties: Any) -> dict[str, Any]:
            return {
                "type": "object",
                "properties": properties,
                "required": required,
            }

        async def llm_chat(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            prompt = str(payload.get("prompt", ""))
            return {"text": f"Echo: {prompt}"}

        async def llm_chat_raw(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
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

        async def memory_search(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            query = str(payload.get("query", ""))
            items = [
                {"key": key, "value": value}
                for key, value in self.memory_store.items()
                if query in key or query in json.dumps(value, ensure_ascii=False)
            ]
            return {"items": items}

        async def memory_save(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            key = str(payload.get("key", ""))
            value = payload.get("value")
            if not isinstance(value, dict):
                raise AstrBotError.invalid_input("memory.save 的 value 必须是 object")
            self.memory_store[key] = value
            return {}

        async def memory_delete(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            self.memory_store.pop(str(payload.get("key", "")), None)
            return {}

        async def db_get(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            return {"value": self.db_store.get(str(payload.get("key", "")))}

        async def db_set(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            key = str(payload.get("key", ""))
            value = payload.get("value")
            if not isinstance(value, dict):
                raise AstrBotError.invalid_input("db.set 的 value 必须是 object")
            self.db_store[key] = value
            return {}

        async def db_delete(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            self.db_store.pop(str(payload.get("key", "")), None)
            return {}

        async def db_list(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            prefix = payload.get("prefix")
            keys = sorted(self.db_store.keys())
            if isinstance(prefix, str):
                keys = [item for item in keys if item.startswith(prefix)]
            return {"keys": keys}

        async def platform_send(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
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

        async def platform_send_image(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
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

        async def platform_get_members(_request_id: str, payload: dict[str, Any], _token) -> dict[str, Any]:
            session = str(payload.get("session", ""))
            return {
                "members": [
                    {"user_id": f"{session}:member-1", "nickname": "Member 1"},
                    {"user_id": f"{session}:member-2", "nickname": "Member 2"},
                ]
            }

        self.register(
            CapabilityDescriptor(
                name="llm.chat",
                description="发送对话请求，返回文本",
                input_schema=obj_schema(["prompt"], prompt={"type": "string"}),
                output_schema=obj_schema(["text"], text={"type": "string"}),
            ),
            call_handler=llm_chat,
        )
        self.register(
            CapabilityDescriptor(
                name="llm.chat_raw",
                description="发送对话请求，返回完整响应",
                input_schema=obj_schema(["prompt"], prompt={"type": "string"}),
                output_schema=obj_schema(["text"], text={"type": "string"}),
            ),
            call_handler=llm_chat_raw,
        )
        self.register(
            CapabilityDescriptor(
                name="llm.stream_chat",
                description="流式对话",
                input_schema=obj_schema(["prompt"], prompt={"type": "string"}),
                output_schema=obj_schema(["text"], text={"type": "string"}),
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=llm_stream,
            finalize=lambda chunks: {"text": "".join(item.get("text", "") for item in chunks)},
        )
        self.register(
            CapabilityDescriptor(
                name="memory.search",
                description="搜索记忆",
                input_schema=obj_schema(["query"], query={"type": "string"}),
                output_schema=obj_schema(["items"], items={"type": "array"}),
            ),
            call_handler=memory_search,
        )
        self.register(
            CapabilityDescriptor(
                name="memory.save",
                description="保存记忆",
                input_schema=obj_schema(["key", "value"], key={"type": "string"}, value={"type": "object"}),
                output_schema=obj_schema([]),
            ),
            call_handler=memory_save,
        )
        self.register(
            CapabilityDescriptor(
                name="memory.delete",
                description="删除记忆",
                input_schema=obj_schema(["key"], key={"type": "string"}),
                output_schema=obj_schema([]),
            ),
            call_handler=memory_delete,
        )
        self.register(
            CapabilityDescriptor(
                name="db.get",
                description="读取 KV",
                input_schema=obj_schema(["key"], key={"type": "string"}),
                output_schema=obj_schema([], value={"type": "object"}),
            ),
            call_handler=db_get,
        )
        self.register(
            CapabilityDescriptor(
                name="db.set",
                description="写入 KV",
                input_schema=obj_schema(["key", "value"], key={"type": "string"}, value={"type": "object"}),
                output_schema=obj_schema([]),
            ),
            call_handler=db_set,
        )
        self.register(
            CapabilityDescriptor(
                name="db.delete",
                description="删除 KV",
                input_schema=obj_schema(["key"], key={"type": "string"}),
                output_schema=obj_schema([]),
            ),
            call_handler=db_delete,
        )
        self.register(
            CapabilityDescriptor(
                name="db.list",
                description="列出 KV",
                input_schema=obj_schema([], prefix={"type": "string"}),
                output_schema=obj_schema(["keys"], keys={"type": "array"}),
            ),
            call_handler=db_list,
        )
        self.register(
            CapabilityDescriptor(
                name="platform.send",
                description="发送消息",
                input_schema=obj_schema(["session", "text"], session={"type": "string"}, text={"type": "string"}),
                output_schema=obj_schema(["message_id"], message_id={"type": "string"}),
            ),
            call_handler=platform_send,
        )
        self.register(
            CapabilityDescriptor(
                name="platform.send_image",
                description="发送图片",
                input_schema=obj_schema(["session", "image_url"], session={"type": "string"}, image_url={"type": "string"}),
                output_schema=obj_schema(["message_id"], message_id={"type": "string"}),
            ),
            call_handler=platform_send_image,
        )
        self.register(
            CapabilityDescriptor(
                name="platform.get_members",
                description="获取群成员",
                input_schema=obj_schema(["session"], session={"type": "string"}),
                output_schema=obj_schema(["members"], members={"type": "array"}),
            ),
            call_handler=platform_get_members,
        )

    def _validate_schema(
        self,
        schema: dict[str, Any] | None,
        payload: dict[str, Any],
    ) -> None:
        if schema is None:
            return
        if schema.get("type") == "object" and not isinstance(payload, dict):
            raise AstrBotError.invalid_input("输入必须是 object")
        for field_name in schema.get("required", []):
            if field_name not in payload or payload[field_name] is None:
                raise AstrBotError.invalid_input(f"缺少必填字段：{field_name}")
