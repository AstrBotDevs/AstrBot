"""Built-in capability registration and handlers for CapabilityRouter.

本模块为 CapabilityRouter 提供内置能力的注册逻辑和处理函数实现。
内置能力涵盖以下类别：
- LLM: 对话、流式对话等大语言模型能力
- Memory: 记忆存储、搜索、带 TTL 的键值对
- DB: 持久化键值存储及变更监听
- Platform: 跨平台消息发送、图片、消息链
- HTTP: 动态 API 路由注册与管理
- Metadata: 插件元数据查询
- System: 数据目录、文本转图片、HTML 渲染、会话等待器等

设计模式：
通过 Mixin 类 (BuiltinCapabilityRouterMixin) 将内置能力注入到 CapabilityRouter，
使其与用户自定义能力共享相同的注册和调用机制。
"""

from __future__ import annotations

import asyncio
import copy
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from ..errors import AstrBotError
from ..protocol.descriptors import (
    BUILTIN_CAPABILITY_SCHEMAS,
    CapabilityDescriptor,
    SessionRef,
)
from ._streaming import StreamExecution


def _clone_target_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    return {str(key): item for key, item in value.items()}


def _clone_chain_payload(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [
        {str(key): item for key, item in chunk.items()}
        for chunk in value
        if isinstance(chunk, dict)
    ]


class _CapabilityRouterHost:
    memory_store: dict[str, dict[str, Any]]
    db_store: dict[str, Any]
    sent_messages: list[dict[str, Any]]
    event_actions: list[dict[str, Any]]
    http_api_store: list[dict[str, Any]]
    _event_streams: dict[str, dict[str, Any]]
    _plugins: dict[str, Any]
    _system_data_root: Path
    _session_waiters: dict[str, set[str]]
    _db_watch_subscriptions: dict[str, tuple[str | None, asyncio.Queue[dict[str, Any]]]]

    def register(
        self,
        descriptor: CapabilityDescriptor,
        *,
        call_handler=None,
        stream_handler=None,
        finalize=None,
        exposed: bool = True,
    ) -> None:
        raise NotImplementedError

    def _emit_db_change(self, *, op: str, key: str, value: Any | None) -> None:
        raise NotImplementedError

    @staticmethod
    def _require_caller_plugin_id(capability_name: str) -> str:
        raise NotImplementedError


class BuiltinCapabilityRouterMixin(_CapabilityRouterHost):
    def _register_builtin_capabilities(self) -> None:
        self._register_llm_capabilities()
        self._register_memory_capabilities()
        self._register_db_capabilities()
        self._register_platform_capabilities()
        self._register_http_capabilities()
        self._register_metadata_capabilities()
        self._register_system_capabilities()

    def _builtin_descriptor(
        self,
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

    def _resolve_target(
        self, payload: dict[str, Any]
    ) -> tuple[str, dict[str, Any] | None]:
        target_payload = payload.get("target")
        if isinstance(target_payload, dict):
            target = SessionRef.model_validate(target_payload)
            return target.session, target.to_payload()
        return str(payload.get("session", "")), None

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
    ) -> AsyncIterator[dict[str, Any]]:
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
        key = str(payload.get("key", ""))
        value = payload.get("value")
        ttl_seconds = payload.get("ttl_seconds", 0)
        if not isinstance(value, dict):
            raise AstrBotError.invalid_input(
                "memory.save_with_ttl 的 value 必须是 object"
            )
        self.memory_store[key] = {"value": value, "ttl_seconds": ttl_seconds}
        return {}

    async def _memory_get_many(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, (list, tuple)):
            raise AstrBotError.invalid_input("memory.get_many 的 keys 必须是数组")
        keys = [str(item) for item in keys_payload]
        items = []
        for key in keys:
            stored = self.memory_store.get(key)
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
        total_items = len(self.memory_store)
        total_bytes = sum(
            len(str(key)) + len(str(value)) for key, value in self.memory_store.items()
        )
        ttl_entries = sum(
            1
            for value in self.memory_store.values()
            if isinstance(value, dict) and "value" in value and "ttl_seconds" in value
        )
        return {
            "total_items": total_items,
            "total_bytes": total_bytes,
            "plugin_id": self._require_caller_plugin_id("memory.stats"),
            "ttl_entries": ttl_entries,
        }

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
            self._builtin_descriptor("db.get", "读取 KV"), call_handler=self._db_get
        )
        self.register(
            self._builtin_descriptor("db.set", "写入 KV"), call_handler=self._db_set
        )
        self.register(
            self._builtin_descriptor("db.delete", "删除 KV"),
            call_handler=self._db_delete,
        )
        self.register(
            self._builtin_descriptor("db.list", "列出 KV"), call_handler=self._db_list
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

    async def _platform_send(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, target = self._resolve_target(payload)
        text = str(payload.get("text", ""))
        message_id = f"msg_{len(self.sent_messages) + 1}"
        sent: dict[str, Any] = {
            "message_id": message_id,
            "session": session,
            "text": text,
        }
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
        sent: dict[str, Any] = {
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
        sent: dict[str, Any] = {
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
        entry: dict[str, Any] = {
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

    def _register_system_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("system.get_data_dir", "获取插件数据目录"),
            call_handler=self._system_get_data_dir,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.text_to_image", "文本转图片"),
            call_handler=self._system_text_to_image,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.html_render", "渲染 HTML 模板"),
            call_handler=self._system_html_render,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.register",
                "注册会话等待器",
            ),
            call_handler=self._system_session_waiter_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.unregister",
                "注销会话等待器",
            ),
            call_handler=self._system_session_waiter_unregister,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.react", "发送事件表情回应"),
            call_handler=self._system_event_react,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.send_typing", "发送输入中状态"),
            call_handler=self._system_event_send_typing,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming",
                "发送事件流式消息",
            ),
            call_handler=self._system_event_send_streaming,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_chunk",
                "推送事件流式消息分片",
            ),
            call_handler=self._system_event_send_streaming_chunk,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_close",
                "关闭事件流式消息会话",
            ),
            call_handler=self._system_event_send_streaming_close,
            exposed=False,
        )

    async def _system_get_data_dir(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("system.get_data_dir")
        data_dir = self._system_data_root / plugin_id
        data_dir.mkdir(parents=True, exist_ok=True)
        return {"path": str(data_dir)}

    async def _system_text_to_image(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        text = str(payload.get("text", ""))
        if bool(payload.get("return_url", True)):
            return {"result": f"mock://text_to_image/{text}"}
        return {"result": f"<image>{text}</image>"}

    async def _system_html_render(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        tmpl = str(payload.get("tmpl", ""))
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AstrBotError.invalid_input("system.html_render requires object data")
        if bool(payload.get("return_url", True)):
            return {"result": f"mock://html_render/{tmpl}"}
        return {"result": json.dumps({"tmpl": tmpl, "data": data}, ensure_ascii=False)}

    async def _system_session_waiter_register(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("system.session_waiter.register")
        session_key = str(payload.get("session_key", "")).strip()
        if not session_key:
            raise AstrBotError.invalid_input(
                "system.session_waiter.register requires session_key"
            )
        self._session_waiters.setdefault(plugin_id, set()).add(session_key)
        return {}

    async def _system_session_waiter_unregister(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("system.session_waiter.unregister")
        session_key = str(payload.get("session_key", "")).strip()
        plugin_waiters = self._session_waiters.get(plugin_id)
        if plugin_waiters is None:
            return {}
        plugin_waiters.discard(session_key)
        if not plugin_waiters:
            self._session_waiters.pop(plugin_id, None)
        return {}

    async def _system_event_react(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self.event_actions.append(
            {
                "action": "react",
                "emoji": str(payload.get("emoji", "")),
                "target": _clone_target_payload(payload.get("target")),
            }
        )
        return {"supported": True}

    async def _system_event_send_typing(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self.event_actions.append(
            {
                "action": "send_typing",
                "target": _clone_target_payload(payload.get("target")),
            }
        )
        return {"supported": True}

    async def _system_event_send_streaming(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        stream_id = f"mock-stream-{len(self._event_streams) + 1}"
        stream_state: dict[str, Any] = {
            "target": _clone_target_payload(payload.get("target")),
            "chunks": [],
            "use_fallback": bool(payload.get("use_fallback", False)),
        }
        self._event_streams[stream_id] = stream_state
        return {"supported": True, "stream_id": stream_id}

    async def _system_event_send_streaming_chunk(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        stream = self._event_streams.get(str(payload.get("stream_id", "")))
        if stream is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        chain = payload.get("chain")
        if not isinstance(chain, list):
            raise AstrBotError.invalid_input(
                "system.event.send_streaming_chunk requires a chain array"
            )
        stream["chunks"].append({"chain": _clone_chain_payload(chain)})
        return {}

    async def _system_event_send_streaming_close(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        stream_id = str(payload.get("stream_id", ""))
        stream = self._event_streams.pop(stream_id, None)
        if stream is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        self.event_actions.append(
            {
                "action": "send_streaming",
                "target": stream["target"],
                "chunks": list(stream["chunks"]),
                "use_fallback": bool(stream["use_fallback"]),
            }
        )
        return {"supported": True}


__all__ = ["BuiltinCapabilityRouterMixin"]
