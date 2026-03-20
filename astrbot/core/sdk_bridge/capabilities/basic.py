from __future__ import annotations

from pathlib import Path
from typing import Any

from astrbot_sdk._memory_backend import PluginMemoryBackend
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.runtime.capability_router import StreamExecution

from astrbot.core.utils.astrbot_path import get_astrbot_plugin_data_path

from ..bridge_base import _get_runtime_provider_types, _get_runtime_sp
from ._host import CapabilityMixinHost


class BasicCapabilityMixin(CapabilityMixinHost):
    def _memory_backend_for_plugin(self, plugin_id: str) -> PluginMemoryBackend:
        backend = self._memory_backends_by_plugin.get(plugin_id)
        if backend is None:
            backend = PluginMemoryBackend(
                Path(get_astrbot_plugin_data_path()) / plugin_id
            )
            self._memory_backends_by_plugin[plugin_id] = backend
        return backend

    def _resolve_memory_embedding_provider_id(
        self,
        payload: dict[str, Any],
        *,
        required: bool,
    ) -> str | None:
        provider_id = str(payload.get("provider_id", "")).strip()
        _, _, embedding_provider_cls, _ = _get_runtime_provider_types()
        if provider_id:
            provider = self._star_context.get_provider_by_id(provider_id)
            if provider is None or not isinstance(provider, embedding_provider_cls):
                raise AstrBotError.invalid_input(
                    f"memory.search unknown embedding provider: {provider_id}"
                )
            return provider_id
        providers = self._star_context.get_all_embedding_providers()
        if providers:
            provider = providers[0]
            provider_id = str(getattr(provider.meta(), "id", "") or "").strip()
            if provider_id:
                return provider_id
        if required:
            raise AstrBotError.invalid_input(
                "memory.search requires an embedding provider",
            )
        return None

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
        mode = str(payload.get("mode", "auto")).strip().lower() or "auto"
        limit = self._optional_int(payload.get("limit"))
        raw_min_score = payload.get("min_score")
        min_score = float(raw_min_score) if raw_min_score is not None else None
        namespace = str(payload.get("namespace")) if payload.get("namespace") else None
        include_descendants = bool(payload.get("include_descendants", True))
        provider_id = self._resolve_memory_embedding_provider_id(
            payload,
            required=mode in {"vector", "hybrid"},
        )
        effective_mode = mode
        if effective_mode == "auto":
            effective_mode = "hybrid" if provider_id is not None else "keyword"
        backend = self._memory_backend_for_plugin(plugin_id)
        items = await backend.search(
            query,
            namespace=namespace,
            include_descendants=include_descendants,
            mode=effective_mode,
            limit=limit,
            min_score=min_score,
            provider_id=provider_id,
            embed_one=(
                (
                    lambda text: self._memory_embedding_for_text(
                        request_id,
                        provider_id,
                        text,
                        _token,
                    )
                )
                if provider_id is not None and effective_mode in {"vector", "hybrid"}
                else None
            ),
            embed_many=(
                (
                    lambda texts: self._memory_embeddings_for_texts(
                        request_id,
                        provider_id,
                        texts,
                        _token,
                    )
                )
                if provider_id is not None and effective_mode in {"vector", "hybrid"}
                else None
            ),
        )
        return {"items": items}

    async def _memory_embedding_for_text(
        self,
        request_id: str,
        provider_id: str,
        text: str,
        token,
    ) -> list[float]:
        output = await self._provider_embedding_get_embedding(
            request_id,
            {"provider_id": provider_id, "text": text},
            token,
        )
        embedding = output.get("embedding")
        if not isinstance(embedding, list):
            return []
        return [float(item) for item in embedding]

    async def _memory_embeddings_for_texts(
        self,
        request_id: str,
        provider_id: str,
        texts: list[str],
        token,
    ) -> list[list[float]]:
        output = await self._provider_embedding_get_embeddings(
            request_id,
            {"provider_id": provider_id, "texts": texts},
            token,
        )
        embeddings = output.get("embeddings")
        if not isinstance(embeddings, list):
            return []
        return [
            [float(value) for value in item]
            for item in embeddings
            if isinstance(item, list)
        ]

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
        await self._memory_backend_for_plugin(plugin_id).save(
            str(payload.get("key", "")),
            value,
            namespace=(
                str(payload.get("namespace"))
                if payload.get("namespace") is not None
                else None
            ),
        )
        return {}

    async def _memory_get(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        value = await self._memory_backend_for_plugin(plugin_id).get(
            str(payload.get("key", "")),
            namespace=(
                str(payload.get("namespace"))
                if payload.get("namespace") is not None
                else None
            ),
        )
        return {"value": value}

    async def _memory_delete(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        await self._memory_backend_for_plugin(plugin_id).delete(
            str(payload.get("key", "")),
            namespace=(
                str(payload.get("namespace"))
                if payload.get("namespace") is not None
                else None
            ),
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
        await self._memory_backend_for_plugin(plugin_id).save_with_ttl(
            str(payload.get("key", "")),
            value,
            ttl_seconds,
            namespace=(
                str(payload.get("namespace"))
                if payload.get("namespace") is not None
                else None
            ),
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
        items = await self._memory_backend_for_plugin(plugin_id).get_many(
            [str(key) for key in keys_payload],
            namespace=(
                str(payload.get("namespace"))
                if payload.get("namespace") is not None
                else None
            ),
        )
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
        deleted_count = await self._memory_backend_for_plugin(plugin_id).delete_many(
            [str(key) for key in keys_payload],
            namespace=(
                str(payload.get("namespace"))
                if payload.get("namespace") is not None
                else None
            ),
        )
        return {"deleted_count": deleted_count}

    async def _memory_stats(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        stats = await self._memory_backend_for_plugin(plugin_id).stats(
            namespace=(
                str(payload.get("namespace"))
                if payload.get("namespace") is not None
                else None
            ),
            include_descendants=bool(payload.get("include_descendants", True)),
        )
        stats["plugin_id"] = plugin_id
        return stats

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
        self.register(
            self._builtin_descriptor(
                "metadata.save_plugin_config",
                "Save current plugin config",
            ),
            call_handler=self._metadata_save_plugin_config,
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

    async def _metadata_save_plugin_config(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        config = payload.get("config")
        if not isinstance(config, dict):
            raise AstrBotError.invalid_input(
                "metadata.save_plugin_config requires config object"
            )
        return {"config": self._plugin_bridge.save_plugin_config(plugin_id, config)}
