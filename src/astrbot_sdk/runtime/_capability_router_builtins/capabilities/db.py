from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from ....errors import AstrBotError
from ..._streaming import StreamExecution
from ..bridge_base import CapabilityRouterBridgeBase


class DBCapabilityMixin(CapabilityRouterBridgeBase):
    def _db_scoped_key(self, plugin_id: str, key: str) -> str:
        """将用户提供的 key 加上插件命名空间前缀，防止跨插件越权访问。"""
        return f"{plugin_id}:{key}"

    def _db_strip_scope(self, plugin_id: str, scoped_key: str) -> str:
        """去掉命名空间前缀，返回插件视角的原始 key。"""
        prefix = f"{plugin_id}:"
        return scoped_key[len(prefix):] if scoped_key.startswith(prefix) else scoped_key

    def _db_public_event(
        self, plugin_id: str, raw_event: dict[str, Any]
    ) -> dict[str, Any]:
        """将内部事件转换回插件可见的 key 视图。"""
        event = dict(raw_event)
        key = event.get("key")
        if isinstance(key, str):
            event["key"] = self._db_strip_scope(plugin_id, key)
        return event

    async def _db_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("db.get")
        key = self._db_scoped_key(plugin_id, str(payload.get("key", "")))
        return {"value": self.db_store.get(key)}

    async def _db_set(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("db.set")
        key = self._db_scoped_key(plugin_id, str(payload.get("key", "")))
        value = payload.get("value")
        self.db_store[key] = value
        self._emit_db_change(op="set", key=key, value=value)
        return {}

    async def _db_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("db.delete")
        key = self._db_scoped_key(plugin_id, str(payload.get("key", "")))
        self.db_store.pop(key, None)
        self._emit_db_change(op="delete", key=key, value=None)
        return {}

    async def _db_list(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("db.list")
        ns_prefix = f"{plugin_id}:"
        # 只列出属于当前插件命名空间的 key，并去掉命名空间前缀返回给插件
        user_prefix = payload.get("prefix")
        all_keys = sorted(
            key for key in self.db_store.keys() if key.startswith(ns_prefix)
        )
        stripped = [self._db_strip_scope(plugin_id, k) for k in all_keys]
        if isinstance(user_prefix, str):
            stripped = [k for k in stripped if k.startswith(user_prefix)]
        return {"keys": stripped}

    async def _db_get_many(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("db.get_many")
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, (list, tuple)):
            raise AstrBotError.invalid_input("db.get_many 的 keys 必须是数组")
        items = [
            {
                "key": str(k),
                "value": self.db_store.get(self._db_scoped_key(plugin_id, str(k))),
            }
            for k in keys_payload
        ]
        return {"items": items}

    async def _db_set_many(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("db.set_many")
        items_payload = payload.get("items")
        if not isinstance(items_payload, (list, tuple)):
            raise AstrBotError.invalid_input("db.set_many 的 items 必须是数组")
        for entry in items_payload:
            if not isinstance(entry, dict):
                raise AstrBotError.invalid_input(
                    "db.set_many 的 items 必须是 object 数组"
                )
            key = self._db_scoped_key(plugin_id, str(entry.get("key", "")))
            value = entry.get("value")
            self.db_store[key] = value
            self._emit_db_change(op="set", key=key, value=value)
        return {}

    async def _db_watch(
        self, request_id: str, payload: dict[str, Any], _token
    ) -> StreamExecution:
        plugin_id = self._require_caller_plugin_id("db.watch")
        prefix = payload.get("prefix")
        prefix_value: str | None
        if isinstance(prefix, str):
            # 将用户传入的前缀也加上命名空间，只监听本插件的 key 变更
            prefix_value = self._db_scoped_key(plugin_id, prefix)
        elif prefix is None:
            # 无前缀时默认监听整个命名空间
            prefix_value = f"{plugin_id}:"
        else:
            raise AstrBotError.invalid_input("db.watch 的 prefix 必须是 string 或 null")

        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._db_watch_subscriptions[request_id] = (prefix_value, queue)

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            try:
                while True:
                    yield self._db_public_event(plugin_id, await queue.get())
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
