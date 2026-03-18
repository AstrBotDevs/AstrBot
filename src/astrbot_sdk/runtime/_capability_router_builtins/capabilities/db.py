from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from ....errors import AstrBotError
from ..._streaming import StreamExecution
from ..bridge_base import CapabilityRouterBridgeBase


class DBCapabilityMixin(CapabilityRouterBridgeBase):
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
