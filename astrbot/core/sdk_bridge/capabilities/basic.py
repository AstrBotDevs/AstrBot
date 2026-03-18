from __future__ import annotations

import json
from typing import Any

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.runtime.capability_router import StreamExecution

from ..bridge_base import _get_runtime_sp
from ._host import CapabilityMixinHost


class BasicCapabilityMixin(CapabilityMixinHost):
    def _register_db_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("db.get", "Read plugin kv"),
            call_handler=self._db_get,
        )
        self.register(
            self._builtin_descriptor("db.set", "Write plugin kv"),
            call_handler=self._db_set,
        )
        self.register(
            self._builtin_descriptor("db.delete", "Delete plugin kv"),
            call_handler=self._db_delete,
        )
        self.register(
            self._builtin_descriptor("db.list", "List plugin kv"),
            call_handler=self._db_list,
        )
        self.register(
            self._builtin_descriptor("db.get_many", "Read plugin kv in batch"),
            call_handler=self._db_get_many,
        )
        self.register(
            self._builtin_descriptor("db.set_many", "Write plugin kv in batch"),
            call_handler=self._db_set_many,
        )
        self.register(
            self._builtin_descriptor(
                "db.watch",
                "Watch plugin kv",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._db_watch,
        )

    async def _db_get(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {
            "value": await _get_runtime_sp().get_async(
                "plugin",
                plugin_id,
                str(payload.get("key", "")),
                None,
            )
        }

    async def _db_set(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        await _get_runtime_sp().put_async(
            "plugin",
            plugin_id,
            str(payload.get("key", "")),
            payload.get("value"),
        )
        return {}

    async def _db_delete(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        await _get_runtime_sp().remove_async(
            "plugin",
            plugin_id,
            str(payload.get("key", "")),
        )
        return {}

    async def _db_list(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        prefix = payload.get("prefix")
        prefix_value = str(prefix) if isinstance(prefix, str) else None
        items = await _get_runtime_sp().range_get_async("plugin", plugin_id, None)
        keys = sorted(
            item.key
            for item in items
            if prefix_value is None or item.key.startswith(prefix_value)
        )
        return {"keys": keys}

    async def _db_get_many(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, list):
            raise AstrBotError.invalid_input("db.get_many requires a keys array")
        items = []
        for key in keys_payload:
            key_text = str(key)
            items.append(
                {
                    "key": key_text,
                    "value": await _get_runtime_sp().get_async(
                        "plugin",
                        plugin_id,
                        key_text,
                        None,
                    ),
                }
            )
        return {"items": items}

    async def _db_set_many(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        items_payload = payload.get("items")
        if not isinstance(items_payload, list):
            raise AstrBotError.invalid_input("db.set_many requires an items array")
        for item in items_payload:
            if not isinstance(item, dict):
                raise AstrBotError.invalid_input("db.set_many items must be objects")
            await _get_runtime_sp().put_async(
                "plugin",
                plugin_id,
                str(item.get("key", "")),
                item.get("value"),
            )
        return {}

    async def _db_watch(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> StreamExecution:
        raise AstrBotError.invalid_input(
            "db.watch is unsupported in AstrBot SDK MVP",
            hint="Use db.get/list polling in MVP",
        )

    def _register_memory_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("memory.search", "Search plugin memory"),
            call_handler=self._memory_search,
        )
        self.register(
            self._builtin_descriptor("memory.save", "Save plugin memory"),
            call_handler=self._memory_save,
        )
        self.register(
            self._builtin_descriptor("memory.get", "Get plugin memory"),
            call_handler=self._memory_get,
        )
        self.register(
            self._builtin_descriptor("memory.delete", "Delete plugin memory"),
            call_handler=self._memory_delete,
        )
        self.register(
            self._builtin_descriptor(
                "memory.save_with_ttl",
                "Save plugin memory with ttl metadata",
            ),
            call_handler=self._memory_save_with_ttl,
        )
        self.register(
            self._builtin_descriptor("memory.get_many", "Get plugin memories"),
            call_handler=self._memory_get_many,
        )
        self.register(
            self._builtin_descriptor("memory.delete_many", "Delete plugin memories"),
            call_handler=self._memory_delete_many,
        )
        self.register(
            self._builtin_descriptor("memory.stats", "Get plugin memory stats"),
            call_handler=self._memory_stats,
        )

    async def _memory_search(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        query = str(payload.get("query", ""))
        entries = await self._load_memory_entries(plugin_id)
        items = [
            {"key": key, "value": value}
            for key, value in entries.items()
            if query in key or query in json.dumps(value, ensure_ascii=False)
        ]
        return {"items": items}

    async def _memory_save(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        value = payload.get("value")
        if not isinstance(value, dict):
            raise AstrBotError.invalid_input("memory.save requires an object value")
        await _get_runtime_sp().put_async(
            self.MEMORY_SCOPE,
            plugin_id,
            str(payload.get("key", "")),
            value,
        )
        return {}

    async def _memory_get(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        value = await _get_runtime_sp().get_async(
            self.MEMORY_SCOPE,
            plugin_id,
            str(payload.get("key", "")),
            None,
        )
        return {"value": value}

    async def _memory_delete(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        await _get_runtime_sp().remove_async(
            self.MEMORY_SCOPE,
            plugin_id,
            str(payload.get("key", "")),
        )
        return {}

    async def _memory_save_with_ttl(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        value = payload.get("value")
        if not isinstance(value, dict):
            raise AstrBotError.invalid_input(
                "memory.save_with_ttl requires an object value"
            )
        ttl_seconds = int(payload.get("ttl_seconds", 0))
        await _get_runtime_sp().put_async(
            self.MEMORY_SCOPE,
            plugin_id,
            str(payload.get("key", "")),
            {"value": value, "ttl_seconds": ttl_seconds},
        )
        return {}

    async def _memory_get_many(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, list):
            raise AstrBotError.invalid_input("memory.get_many requires a keys array")
        items = []
        for key in keys_payload:
            key_text = str(key)
            stored = await _get_runtime_sp().get_async(
                self.MEMORY_SCOPE,
                plugin_id,
                key_text,
                None,
            )
            if (
                isinstance(stored, dict)
                and "value" in stored
                and "ttl_seconds" in stored
            ):
                stored = stored["value"]
            items.append({"key": key_text, "value": stored})
        return {"items": items}

    async def _memory_delete_many(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        keys_payload = payload.get("keys")
        if not isinstance(keys_payload, list):
            raise AstrBotError.invalid_input("memory.delete_many requires a keys array")
        deleted_count = 0
        for key in keys_payload:
            key_text = str(key)
            existing = await _get_runtime_sp().get_async(
                self.MEMORY_SCOPE,
                plugin_id,
                key_text,
                None,
            )
            if existing is None:
                continue
            await _get_runtime_sp().remove_async(
                self.MEMORY_SCOPE,
                plugin_id,
                key_text,
            )
            deleted_count += 1
        return {"deleted_count": deleted_count}

    async def _memory_stats(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        entries = await self._load_memory_entries(plugin_id)
        ttl_entries = sum(
            1
            for value in entries.values()
            if isinstance(value, dict) and "value" in value and "ttl_seconds" in value
        )
        total_bytes = sum(
            len(str(key)) + len(str(value)) for key, value in entries.items()
        )
        return {
            "total_items": len(entries),
            "total_bytes": total_bytes,
            "plugin_id": plugin_id,
            "ttl_entries": ttl_entries,
        }

    async def _load_memory_entries(self, plugin_id: str) -> dict[str, Any]:
        items = await _get_runtime_sp().range_get_async(
            self.MEMORY_SCOPE,
            plugin_id,
            None,
        )
        entries: dict[str, Any] = {}
        for item in items:
            key = str(getattr(item, "key", ""))
            if not key:
                continue
            entries[key] = await _get_runtime_sp().get_async(
                self.MEMORY_SCOPE,
                plugin_id,
                key,
                None,
            )
        return entries

    def _register_http_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("http.register_api", "Register http route"),
            call_handler=self._http_register_api,
        )
        self.register(
            self._builtin_descriptor("http.unregister_api", "Unregister http route"),
            call_handler=self._http_unregister_api,
        )
        self.register(
            self._builtin_descriptor("http.list_apis", "List http routes"),
            call_handler=self._http_list_apis,
        )

    async def _http_register_api(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        methods = payload.get("methods")
        if not isinstance(methods, list) or not all(
            isinstance(item, str) for item in methods
        ):
            raise AstrBotError.invalid_input(
                "http.register_api requires a string methods array"
            )
        self._plugin_bridge.register_http_api(
            plugin_id=plugin_id,
            route=str(payload.get("route", "")),
            methods=methods,
            handler_capability=str(payload.get("handler_capability", "")),
            description=str(payload.get("description", "")),
        )
        return {}

    async def _http_unregister_api(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        methods = payload.get("methods")
        if not isinstance(methods, list) or not all(
            isinstance(item, str) for item in methods
        ):
            raise AstrBotError.invalid_input(
                "http.unregister_api requires a string methods array"
            )
        self._plugin_bridge.unregister_http_api(
            plugin_id=plugin_id,
            route=str(payload.get("route", "")),
            methods=methods,
        )
        return {}

    async def _http_list_apis(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {"apis": self._plugin_bridge.list_http_apis(plugin_id)}

    def _register_metadata_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("metadata.get_plugin", "Get plugin metadata"),
            call_handler=self._metadata_get_plugin,
        )
        self.register(
            self._builtin_descriptor("metadata.list_plugins", "List plugins metadata"),
            call_handler=self._metadata_list_plugins,
        )
        self.register(
            self._builtin_descriptor(
                "metadata.get_plugin_config",
                "Get current plugin config",
            ),
            call_handler=self._metadata_get_plugin_config,
        )

    async def _metadata_get_plugin(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin = self._plugin_bridge.get_plugin_metadata(str(payload.get("name", "")))
        return {"plugin": plugin}

    async def _metadata_list_plugins(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return {"plugins": self._plugin_bridge.list_plugin_metadata()}

    async def _metadata_get_plugin_config(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        requested = str(payload.get("name", ""))
        if requested != plugin_id:
            return {"config": None}
        return {"config": self._plugin_bridge.get_plugin_config(plugin_id)}
