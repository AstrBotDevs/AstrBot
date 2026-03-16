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
    _request_overlays: dict[str, dict[str, Any]]
    _provider_catalog: dict[str, list[dict[str, Any]]]
    _active_provider_ids: dict[str, str | None]
    _system_data_root: Path
    _session_waiters: dict[str, set[str]]
    _session_plugin_configs: dict[str, dict[str, Any]]
    _session_service_configs: dict[str, dict[str, Any]]
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
        self._register_p0_5_capabilities()
        self._register_p0_6_capabilities()
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

    @staticmethod
    def _is_group_session(session: str) -> bool:
        normalized = str(session).lower()
        return ":group:" in normalized or ":groupmessage:" in normalized

    @staticmethod
    def _mock_group_payload(session: str) -> dict[str, Any] | None:
        if not BuiltinCapabilityRouterMixin._is_group_session(session):
            return None
        members = [
            {
                "user_id": f"{session}:member-1",
                "nickname": "Member 1",
                "role": "member",
            },
            {
                "user_id": f"{session}:member-2",
                "nickname": "Member 2",
                "role": "admin",
            },
        ]
        return {
            "group_id": session.rsplit(":", maxsplit=1)[-1],
            "group_name": f"Mock Group {session.rsplit(':', maxsplit=1)[-1]}",
            "group_avatar": "",
            "group_owner": members[0]["user_id"],
            "group_admins": [members[1]["user_id"]],
            "members": members,
        }

    def _session_plugin_config(self, session: str) -> dict[str, Any]:
        config = self._session_plugin_configs.get(str(session), {})
        return dict(config) if isinstance(config, dict) else {}

    def _session_service_config(self, session: str) -> dict[str, Any]:
        config = self._session_service_configs.get(str(session), {})
        return dict(config) if isinstance(config, dict) else {}

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

    async def _platform_send_by_session(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        chain = payload.get("chain")
        if not isinstance(chain, list) or not all(
            isinstance(item, dict) for item in chain
        ):
            raise AstrBotError.invalid_input(
                "platform.send_by_session 的 chain 必须是 object 数组"
            )
        session = str(payload.get("session", ""))
        message_id = f"proactive_{len(self.sent_messages) + 1}"
        self.sent_messages.append(
            {
                "message_id": message_id,
                "session": session,
                "chain": [dict(item) for item in chain],
            }
        )
        return {"message_id": message_id}

    async def _platform_get_group(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, _target = self._resolve_target(payload)
        return {"group": self._mock_group_payload(session)}

    async def _platform_get_members(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session, _target = self._resolve_target(payload)
        group = self._mock_group_payload(session)
        if group is None:
            return {"members": []}
        return {"members": list(group.get("members", []))}

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
            self._builtin_descriptor(
                "platform.send_by_session", "按会话主动发送消息链"
            ),
            call_handler=self._platform_send_by_session,
        )
        self.register(
            self._builtin_descriptor("platform.get_group", "获取当前群信息"),
            call_handler=self._platform_get_group,
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

    def _provider_payload(
        self, kind: str, provider_id: str | None
    ) -> dict[str, Any] | None:
        if not provider_id:
            return None
        for item in self._provider_catalog.get(kind, []):
            if str(item.get("id", "")) == provider_id:
                return dict(item)
        return None

    async def _provider_get_using(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider_id = self._active_provider_ids.get("chat")
        return {"provider": self._provider_payload("chat", provider_id)}

    async def _provider_get_current_chat_provider_id(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return {"provider_id": self._active_provider_ids.get("chat")}

    def _provider_list_payload(self, kind: str) -> dict[str, Any]:
        return {
            "providers": [dict(item) for item in self._provider_catalog.get(kind, [])]
        }

    async def _provider_list_all(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return self._provider_list_payload("chat")

    async def _provider_list_all_tts(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return self._provider_list_payload("tts")

    async def _provider_list_all_stt(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return self._provider_list_payload("stt")

    async def _provider_list_all_embedding(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return self._provider_list_payload("embedding")

    async def _provider_get_using_tts(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider_id = self._active_provider_ids.get("tts")
        return {"provider": self._provider_payload("tts", provider_id)}

    async def _provider_get_using_stt(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider_id = self._active_provider_ids.get("stt")
        return {"provider": self._provider_payload("stt", provider_id)}

    async def _llm_tool_manager_get(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("llm_tool.manager.get")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"registered": [], "active": []}
        registered = [dict(item) for item in plugin.llm_tools.values()]
        active = [
            dict(item)
            for name, item in plugin.llm_tools.items()
            if name in plugin.active_llm_tools
        ]
        return {"registered": registered, "active": active}

    async def _llm_tool_manager_activate(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("llm_tool.manager.activate")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"activated": False}
        name = str(payload.get("name", ""))
        spec = plugin.llm_tools.get(name)
        if spec is None:
            return {"activated": False}
        spec["active"] = True
        plugin.active_llm_tools.add(name)
        return {"activated": True}

    async def _llm_tool_manager_deactivate(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("llm_tool.manager.deactivate")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"deactivated": False}
        name = str(payload.get("name", ""))
        spec = plugin.llm_tools.get(name)
        if spec is None:
            return {"deactivated": False}
        spec["active"] = False
        plugin.active_llm_tools.discard(name)
        return {"deactivated": True}

    async def _llm_tool_manager_add(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("llm_tool.manager.add")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"names": []}
        tools_payload = payload.get("tools")
        if not isinstance(tools_payload, list):
            raise AstrBotError.invalid_input("llm_tool.manager.add 的 tools 必须是数组")
        names: list[str] = []
        for item in tools_payload:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()
            if not name:
                continue
            plugin.llm_tools[name] = dict(item)
            if bool(item.get("active", True)):
                plugin.active_llm_tools.add(name)
            else:
                plugin.active_llm_tools.discard(name)
            names.append(name)
        return {"names": names}

    async def _agent_registry_list(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("agent.registry.list")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"agents": []}
        return {"agents": [dict(item) for item in plugin.agents.values()]}

    async def _agent_registry_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("agent.registry.get")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"agent": None}
        agent = plugin.agents.get(str(payload.get("name", "")))
        return {"agent": dict(agent) if isinstance(agent, dict) else None}

    async def _agent_tool_loop_run(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("agent.tool_loop.run")
        plugin = self._plugins.get(plugin_id)
        requested_tools = payload.get("tool_names")
        active_tools: list[str] = []
        if plugin is not None:
            if isinstance(requested_tools, list) and requested_tools:
                active_tools = [
                    name
                    for name in (str(item) for item in requested_tools)
                    if name in plugin.active_llm_tools
                ]
            else:
                active_tools = sorted(plugin.active_llm_tools)
        prompt = str(payload.get("prompt", "") or "")
        suffix = ""
        if active_tools:
            suffix = f" tools={','.join(active_tools)}"
        return {
            "text": f"Mock tool loop: {prompt}{suffix}".strip(),
            "usage": {
                "input_tokens": len(prompt),
                "output_tokens": len(prompt) + len(suffix),
            },
            "finish_reason": "stop",
            "tool_calls": [],
            "role": "assistant",
            "reasoning_content": None,
            "reasoning_signature": None,
        }

    def _register_p0_5_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("provider.get_using", "获取当前聊天 Provider"),
            call_handler=self._provider_get_using,
        )
        self.register(
            self._builtin_descriptor(
                "provider.get_current_chat_provider_id",
                "获取当前聊天 Provider ID",
            ),
            call_handler=self._provider_get_current_chat_provider_id,
        )
        self.register(
            self._builtin_descriptor("provider.list_all", "列出聊天 Providers"),
            call_handler=self._provider_list_all,
        )
        self.register(
            self._builtin_descriptor("provider.list_all_tts", "列出 TTS Providers"),
            call_handler=self._provider_list_all_tts,
        )
        self.register(
            self._builtin_descriptor("provider.list_all_stt", "列出 STT Providers"),
            call_handler=self._provider_list_all_stt,
        )
        self.register(
            self._builtin_descriptor(
                "provider.list_all_embedding",
                "列出 Embedding Providers",
            ),
            call_handler=self._provider_list_all_embedding,
        )
        self.register(
            self._builtin_descriptor("provider.get_using_tts", "获取当前 TTS Provider"),
            call_handler=self._provider_get_using_tts,
        )
        self.register(
            self._builtin_descriptor("provider.get_using_stt", "获取当前 STT Provider"),
            call_handler=self._provider_get_using_stt,
        )
        self.register(
            self._builtin_descriptor("llm_tool.manager.get", "获取 LLM 工具状态"),
            call_handler=self._llm_tool_manager_get,
        )
        self.register(
            self._builtin_descriptor("llm_tool.manager.activate", "激活 LLM 工具"),
            call_handler=self._llm_tool_manager_activate,
        )
        self.register(
            self._builtin_descriptor("llm_tool.manager.deactivate", "停用 LLM 工具"),
            call_handler=self._llm_tool_manager_deactivate,
        )
        self.register(
            self._builtin_descriptor("llm_tool.manager.add", "动态添加 LLM 工具"),
            call_handler=self._llm_tool_manager_add,
        )
        self.register(
            self._builtin_descriptor("agent.tool_loop.run", "运行 mock tool loop"),
            call_handler=self._agent_tool_loop_run,
        )
        self.register(
            self._builtin_descriptor("agent.registry.list", "列出 Agent 元数据"),
            call_handler=self._agent_registry_list,
        )
        self.register(
            self._builtin_descriptor("agent.registry.get", "获取 Agent 元数据"),
            call_handler=self._agent_registry_get,
        )

    async def _session_plugin_is_enabled(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        plugin_name = str(payload.get("plugin_name", ""))
        config = self._session_plugin_config(session)
        enabled_plugins = {
            str(item) for item in config.get("enabled_plugins", []) if str(item).strip()
        }
        disabled_plugins = {
            str(item)
            for item in config.get("disabled_plugins", [])
            if str(item).strip()
        }
        if plugin_name in enabled_plugins:
            return {"enabled": True}
        return {"enabled": plugin_name not in disabled_plugins}

    async def _session_plugin_filter_handlers(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        handlers = payload.get("handlers")
        if not isinstance(handlers, list):
            raise AstrBotError.invalid_input(
                "session.plugin.filter_handlers 的 handlers 必须是 object 数组"
            )
        disabled_plugins = {
            str(item)
            for item in self._session_plugin_config(session).get("disabled_plugins", [])
            if str(item).strip()
        }
        reserved_plugins = {
            str(plugin.metadata.get("name", ""))
            for plugin in self._plugins.values()
            if bool(plugin.metadata.get("reserved", False))
        }
        filtered = []
        for item in handlers:
            if not isinstance(item, dict):
                continue
            plugin_name = str(item.get("plugin_name", ""))
            if (
                plugin_name
                and plugin_name in disabled_plugins
                and plugin_name not in reserved_plugins
            ):
                continue
            filtered.append(dict(item))
        return {"handlers": filtered}

    async def _session_service_is_llm_enabled(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        return {"enabled": bool(config.get("llm_enabled", True))}

    async def _session_service_set_llm_status(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        config["llm_enabled"] = bool(payload.get("enabled", False))
        self._session_service_configs[session] = config
        return {}

    async def _session_service_is_tts_enabled(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        return {"enabled": bool(config.get("tts_enabled", True))}

    async def _session_service_set_tts_status(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", ""))
        config = self._session_service_config(session)
        config["tts_enabled"] = bool(payload.get("enabled", False))
        self._session_service_configs[session] = config
        return {}

    def _register_p0_6_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("session.plugin.is_enabled", "获取会话级插件开关"),
            call_handler=self._session_plugin_is_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.plugin.filter_handlers",
                "按会话过滤 handler 元数据",
            ),
            call_handler=self._session_plugin_filter_handlers,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_llm_enabled",
                "获取会话级 LLM 开关",
            ),
            call_handler=self._session_service_is_llm_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_llm_status",
                "写入会话级 LLM 开关",
            ),
            call_handler=self._session_service_set_llm_status,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_tts_enabled",
                "获取会话级 TTS 开关",
            ),
            call_handler=self._session_service_is_tts_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_tts_status",
                "写入会话级 TTS 开关",
            ),
            call_handler=self._session_service_set_tts_status,
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
        self.register(
            self._builtin_descriptor(
                "system.event.llm.get_state",
                "读取当前请求的默认 LLM 状态",
            ),
            call_handler=self._system_event_llm_get_state,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.llm.request",
                "请求当前事件继续进入默认 LLM 链路",
            ),
            call_handler=self._system_event_llm_request,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.result.get", "读取当前请求结果"),
            call_handler=self._system_event_result_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.result.set", "写入当前请求结果"),
            call_handler=self._system_event_result_set,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.result.clear", "清理当前请求结果"),
            call_handler=self._system_event_result_clear,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.get",
                "读取当前请求 handler 白名单",
            ),
            call_handler=self._system_event_handler_whitelist_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.set",
                "写入当前请求 handler 白名单",
            ),
            call_handler=self._system_event_handler_whitelist_set,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "registry.get_handlers_by_event_type",
                "按事件类型列出 handler 元数据",
            ),
            call_handler=self._registry_get_handlers_by_event_type,
        )
        self.register(
            self._builtin_descriptor(
                "registry.get_handler_by_full_name",
                "按 full name 查询 handler 元数据",
            ),
            call_handler=self._registry_get_handler_by_full_name,
        )

    def _ensure_request_overlay(self, request_id: str) -> dict[str, Any]:
        overlay = self._request_overlays.get(request_id)
        if overlay is None:
            overlay = {
                "should_call_llm": False,
                "requested_llm": False,
                "result": None,
                "handler_whitelist": None,
            }
            self._request_overlays[request_id] = overlay
        return overlay

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

    async def _system_event_llm_get_state(
        self, request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(request_id)
        return {
            "should_call_llm": bool(overlay["should_call_llm"]),
            "requested_llm": bool(overlay["requested_llm"]),
        }

    async def _system_event_llm_request(
        self, request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(request_id)
        overlay["requested_llm"] = True
        overlay["should_call_llm"] = True
        return await self._system_event_llm_get_state(request_id, {}, _token)

    async def _system_event_result_get(
        self, request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(request_id)
        result = overlay.get("result")
        return {"result": dict(result) if isinstance(result, dict) else None}

    async def _system_event_result_set(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        result = payload.get("result")
        if not isinstance(result, dict):
            raise AstrBotError.invalid_input(
                "system.event.result.set 的 result 必须是 object"
            )
        overlay = self._ensure_request_overlay(request_id)
        overlay["result"] = dict(result)
        return {"result": dict(result)}

    async def _system_event_result_clear(
        self, request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(request_id)
        overlay["result"] = None
        return {}

    async def _system_event_handler_whitelist_get(
        self, request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(request_id)
        whitelist = overlay.get("handler_whitelist")
        if whitelist is None:
            return {"plugin_names": None}
        return {"plugin_names": sorted(str(item) for item in whitelist)}

    async def _system_event_handler_whitelist_set(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        overlay = self._ensure_request_overlay(request_id)
        plugin_names_payload = payload.get("plugin_names")
        if plugin_names_payload is None:
            overlay["handler_whitelist"] = None
        elif isinstance(plugin_names_payload, list):
            overlay["handler_whitelist"] = {
                str(item) for item in plugin_names_payload if str(item).strip()
            }
        else:
            raise AstrBotError.invalid_input(
                "system.event.handler_whitelist.set 的 plugin_names 必须是数组或 null"
            )
        return await self._system_event_handler_whitelist_get(request_id, {}, _token)

    async def _registry_get_handlers_by_event_type(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        event_type = str(payload.get("event_type", "")).strip()
        handlers: list[dict[str, Any]] = []
        for plugin in self._plugins.values():
            handlers.extend(
                [
                    dict(handler)
                    for handler in plugin.handlers
                    if event_type in handler.get("event_types", [])
                ]
            )
        return {"handlers": handlers}

    async def _registry_get_handler_by_full_name(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        full_name = str(payload.get("full_name", "")).strip()
        for plugin in self._plugins.values():
            for handler in plugin.handlers:
                if handler.get("handler_full_name") == full_name:
                    return {"handler": dict(handler)}
        return {"handler": None}

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
