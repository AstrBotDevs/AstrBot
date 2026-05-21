from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator
from typing import Any

from ....errors import AstrBotError
from ..._streaming import StreamExecution
from ..bridge_base import (
    _MOCK_EMBEDDING_DIM,
    CapabilityRouterBridgeBase,
    _mock_embedding_vector,
)


class ProviderCapabilityMixin(CapabilityRouterBridgeBase):
    def _provider_payload(
        self, kind: str, provider_id: str | None
    ) -> dict[str, Any] | None:
        if not provider_id:
            return None
        for item in self._provider_catalog.get(kind, []):
            if str(item.get("id", "")) == provider_id:
                return dict(item)
        return None

    def _provider_payload_by_id(self, provider_id: str) -> dict[str, Any] | None:
        normalized = str(provider_id).strip()
        if not normalized:
            return None
        for items in self._provider_catalog.values():
            for item in items:
                if str(item.get("id", "")) == normalized:
                    return dict(item)
        return None

    @staticmethod
    def _provider_kind_from_type(provider_type: str) -> str:
        mapping = {
            "chat_completion": "chat",
            "text_to_speech": "tts",
            "speech_to_text": "stt",
            "embedding": "embedding",
            "rerank": "rerank",
        }
        normalized = str(provider_type).strip().lower()
        if normalized not in mapping:
            raise AstrBotError.invalid_input(f"unknown provider_type: {provider_type}")
        return mapping[normalized]

    def _provider_config_by_id(self, provider_id: str) -> dict[str, Any] | None:
        record = self._provider_configs.get(str(provider_id).strip())
        return dict(record) if isinstance(record, dict) else None

    @staticmethod
    def _managed_provider_record(
        payload: dict[str, Any],
        *,
        loaded: bool,
    ) -> dict[str, Any]:
        return {
            "id": str(payload.get("id", "")),
            "model": (
                str(payload.get("model")) if payload.get("model") is not None else None
            ),
            "type": str(payload.get("type", "")),
            "provider_type": str(payload.get("provider_type", "chat_completion")),
            "loaded": bool(loaded),
            "enabled": bool(payload.get("enable", True)),
            "provider_source_id": (
                str(payload.get("provider_source_id"))
                if payload.get("provider_source_id") is not None
                else None
            ),
        }

    def _managed_provider_record_by_id(self, provider_id: str) -> dict[str, Any] | None:
        provider = self._provider_payload_by_id(provider_id)
        if provider is not None:
            config = self._provider_config_by_id(provider_id) or provider
            merged = dict(provider)
            merged.update(
                {
                    "enable": config.get("enable", True),
                    "provider_source_id": config.get("provider_source_id"),
                }
            )
            return self._managed_provider_record(merged, loaded=True)
        config = self._provider_config_by_id(provider_id)
        if config is None:
            return None
        return self._managed_provider_record(config, loaded=False)

    def _emit_provider_change(
        self,
        provider_id: str,
        provider_type: str,
        umo: str | None,
    ) -> None:
        event = {
            "provider_id": str(provider_id),
            "provider_type": str(provider_type),
            "umo": str(umo) if umo is not None else None,
        }
        for queue in list(self._provider_change_subscriptions.values()):
            queue.put_nowait(dict(event))

    def _require_reserved_plugin(self, capability_name: str) -> str:
        plugin_id = self._require_caller_plugin_id(capability_name)
        plugin = self._plugins.get(plugin_id)
        if plugin is not None and bool(plugin.metadata.get("reserved", False)):
            return plugin_id
        if plugin_id in {"system", "__system__"}:
            return plugin_id
        raise AstrBotError.invalid_input(
            f"{capability_name} is restricted to reserved/system plugins"
        )

    def _provider_entry(
        self,
        payload: dict[str, Any],
        capability_name: str,
        expected_kind: str | None = None,
    ) -> dict[str, Any]:
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            raise AstrBotError.invalid_input(
                f"{capability_name} requires provider_id",
            )
        provider = self._provider_payload_by_id(provider_id)
        if provider is None:
            raise AstrBotError.invalid_input(
                f"{capability_name} unknown provider_id: {provider_id}",
            )
        if (
            expected_kind is not None
            and str(provider.get("provider_type")) != expected_kind
        ):
            raise AstrBotError.invalid_input(
                f"{capability_name} requires a {expected_kind} provider",
            )
        return provider

    async def _provider_get_using(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider_id = self._active_provider_ids.get("chat")
        return {"provider": self._provider_payload("chat", provider_id)}

    async def _provider_get_by_id(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return {
            "provider": self._provider_payload_by_id(
                str(payload.get("provider_id", ""))
            )
        }

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

    async def _provider_list_all_rerank(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return self._provider_list_payload("rerank")

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

    async def _provider_stt_get_text(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._provider_entry(
            payload,
            "provider.stt.get_text",
            "speech_to_text",
        )
        return {"text": f"Mock transcript: {str(payload.get('audio_url', ''))}"}

    async def _provider_tts_get_audio(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider = self._provider_entry(
            payload,
            "provider.tts.get_audio",
            "text_to_speech",
        )
        return {
            "audio_path": (
                f"mock://tts/{provider.get('id', '')}/{str(payload.get('text', ''))}"
            )
        }

    async def _provider_tts_support_stream(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider = self._provider_entry(
            payload,
            "provider.tts.support_stream",
            "text_to_speech",
        )
        return {"supported": bool(provider.get("support_stream", True))}

    async def _provider_tts_get_audio_stream(
        self,
        _request_id: str,
        payload: dict[str, Any],
        token,
    ) -> StreamExecution:
        self._provider_entry(
            payload,
            "provider.tts.get_audio_stream",
            "text_to_speech",
        )
        text = payload.get("text")
        text_chunks = payload.get("text_chunks")
        if isinstance(text, str):
            chunks = [text]
        elif isinstance(text_chunks, list) and text_chunks:
            chunks = [str(item) for item in text_chunks]
        else:
            raise AstrBotError.invalid_input(
                "provider.tts.get_audio_stream requires text or text_chunks"
            )

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            for chunk in chunks:
                token.raise_if_cancelled()
                await asyncio.sleep(0)
                yield {
                    "audio_base64": base64.b64encode(
                        f"mock-audio:{chunk}".encode()
                    ).decode("ascii"),
                    "text": chunk,
                }

        return StreamExecution(
            iterator=iterator(),
            finalize=lambda items: (
                items[-1] if items else {"audio_base64": "", "text": None}
            ),
        )

    async def _provider_embedding_get_embedding(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider = self._provider_entry(
            payload,
            "provider.embedding.get_embedding",
            "embedding",
        )
        return {
            "embedding": _mock_embedding_vector(
                str(payload.get("text", "")),
                provider_id=str(provider.get("id", "")),
            )
        }

    async def _provider_embedding_get_embeddings(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        provider = self._provider_entry(
            payload,
            "provider.embedding.get_embeddings",
            "embedding",
        )
        texts = payload.get("texts")
        if not isinstance(texts, list):
            raise AstrBotError.invalid_input(
                "provider.embedding.get_embeddings requires texts",
            )
        return {
            "embeddings": [
                _mock_embedding_vector(
                    str(text),
                    provider_id=str(provider.get("id", "")),
                )
                for text in texts
            ],
        }

    async def _provider_embedding_get_dim(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._provider_entry(
            payload,
            "provider.embedding.get_dim",
            "embedding",
        )
        return {"dim": _MOCK_EMBEDDING_DIM}

    async def _provider_rerank_rerank(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._provider_entry(
            payload,
            "provider.rerank.rerank",
            "rerank",
        )
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise AstrBotError.invalid_input(
                "provider.rerank.rerank requires documents",
            )
        scored = [
            {
                "index": index,
                "score": 1.0,
                "document": str(raw_document),
            }
            for index, raw_document in enumerate(documents)
        ]
        top_n = payload.get("top_n")
        if top_n is not None:
            scored = scored[: max(int(top_n), 0)]
        return {"results": scored}

    async def _provider_manager_set(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.set")
        provider_id = str(payload.get("provider_id", "")).strip()
        provider_type = str(payload.get("provider_type", "")).strip()
        kind = self._provider_kind_from_type(provider_type)
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.set requires provider_id"
            )
        if self._provider_payload(kind, provider_id) is None:
            raise AstrBotError.invalid_input(
                f"provider.manager.set unknown provider_id: {provider_id}"
            )
        self._active_provider_ids[kind] = provider_id
        self._emit_provider_change(
            provider_id,
            provider_type,
            str(payload.get("umo")) if payload.get("umo") is not None else None,
        )
        return {}

    async def _provider_manager_get_by_id(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.get_by_id")
        return {
            "provider": self._managed_provider_record_by_id(
                str(payload.get("provider_id", ""))
            )
        }

    async def _provider_manager_get_merged_provider_config(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.get_merged_provider_config")
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.get_merged_provider_config requires provider_id"
            )
        provider = self._provider_payload_by_id(provider_id)
        config = self._provider_config_by_id(provider_id)
        if provider is None and config is None:
            raise AstrBotError.invalid_input(
                "provider.manager.get_merged_provider_config "
                f"unknown provider_id: {provider_id}"
            )
        if provider is None:
            return {"config": dict(config) if isinstance(config, dict) else config}
        if config is None:
            return {"config": dict(provider)}
        merged_config = dict(provider)
        merged_config.update(config)
        return {"config": merged_config}

    @staticmethod
    def _normalize_provider_config_object(
        payload: Any,
        capability_name: str,
        field_name: str,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise AstrBotError.invalid_input(
                f"{capability_name} requires {field_name} object"
            )
        return dict(payload)

    async def _provider_manager_load(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.load")
        provider_config = self._normalize_provider_config_object(
            payload.get("provider_config"),
            "provider.manager.load",
            "provider_config",
        )
        provider_id = str(provider_config.get("id", "")).strip()
        provider_type = str(provider_config.get("provider_type", "")).strip()
        kind = self._provider_kind_from_type(provider_type)
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.load requires provider id"
            )
        if bool(provider_config.get("enable", True)):
            record = {
                "id": provider_id,
                "model": (
                    str(provider_config.get("model"))
                    if provider_config.get("model") is not None
                    else None
                ),
                "type": str(provider_config.get("type", "")),
                "provider_type": provider_type,
            }
            self._provider_catalog[kind] = [
                item
                for item in self._provider_catalog.get(kind, [])
                if str(item.get("id", "")) != provider_id
            ]
            self._provider_catalog[kind].append(record)
            self._emit_provider_change(provider_id, provider_type, None)
        return {
            "provider": self._managed_provider_record(
                provider_config,
                loaded=bool(provider_config.get("enable", True)),
            )
        }

    async def _provider_manager_terminate(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.terminate")
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.terminate requires provider_id"
            )
        managed = self._managed_provider_record_by_id(provider_id)
        if managed is None:
            raise AstrBotError.invalid_input(
                f"provider.manager.terminate unknown provider_id: {provider_id}"
            )
        kind = self._provider_kind_from_type(str(managed.get("provider_type", "")))
        self._provider_catalog[kind] = [
            item
            for item in self._provider_catalog.get(kind, [])
            if str(item.get("id", "")) != provider_id
        ]
        if self._active_provider_ids.get(kind) == provider_id:
            catalog = self._provider_catalog.get(kind, [])
            self._active_provider_ids[kind] = (
                str(catalog[0].get("id")) if catalog else None
            )
        self._emit_provider_change(
            provider_id, str(managed.get("provider_type", "")), None
        )
        return {}

    async def _provider_manager_create(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.create")
        provider_config = self._normalize_provider_config_object(
            payload.get("provider_config"),
            "provider.manager.create",
            "provider_config",
        )
        provider_id = str(provider_config.get("id", "")).strip()
        provider_type = str(provider_config.get("provider_type", "")).strip()
        kind = self._provider_kind_from_type(provider_type)
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.create requires provider id"
            )
        self._provider_configs[provider_id] = dict(provider_config)
        if bool(provider_config.get("enable", True)):
            self._provider_catalog[kind] = [
                item
                for item in self._provider_catalog.get(kind, [])
                if str(item.get("id", "")) != provider_id
            ]
            self._provider_catalog[kind].append(
                {
                    "id": provider_id,
                    "model": (
                        str(provider_config.get("model"))
                        if provider_config.get("model") is not None
                        else None
                    ),
                    "type": str(provider_config.get("type", "")),
                    "provider_type": provider_type,
                }
            )
        self._emit_provider_change(provider_id, provider_type, None)
        return {"provider": self._managed_provider_record_by_id(provider_id)}

    async def _provider_manager_update(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.update")
        origin_provider_id = str(payload.get("origin_provider_id", "")).strip()
        new_config = self._normalize_provider_config_object(
            payload.get("new_config"),
            "provider.manager.update",
            "new_config",
        )
        if not origin_provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.update requires origin_provider_id"
            )
        current = self._provider_config_by_id(origin_provider_id)
        if current is None:
            current = self._managed_provider_record_by_id(origin_provider_id)
        if current is None:
            raise AstrBotError.invalid_input(
                f"provider.manager.update unknown provider_id: {origin_provider_id}"
            )
        target_provider_id = str(new_config.get("id") or origin_provider_id).strip()
        provider_type = str(
            new_config.get("provider_type") or current.get("provider_type", "")
        ).strip()
        kind = self._provider_kind_from_type(provider_type)
        self._provider_configs.pop(origin_provider_id, None)
        merged = dict(current)
        merged.update(new_config)
        merged["id"] = target_provider_id
        merged["provider_type"] = provider_type
        self._provider_configs[target_provider_id] = merged
        for catalog_kind, items in list(self._provider_catalog.items()):
            self._provider_catalog[catalog_kind] = [
                item for item in items if str(item.get("id", "")) != origin_provider_id
            ]
        if bool(merged.get("enable", True)):
            self._provider_catalog[kind].append(
                {
                    "id": target_provider_id,
                    "model": (
                        str(merged.get("model"))
                        if merged.get("model") is not None
                        else None
                    ),
                    "type": str(merged.get("type", "")),
                    "provider_type": provider_type,
                }
            )
        for active_kind, active_id in list(self._active_provider_ids.items()):
            if active_id == origin_provider_id:
                self._active_provider_ids[active_kind] = (
                    target_provider_id if active_kind == kind else None
                )
        self._emit_provider_change(target_provider_id, provider_type, None)
        return {"provider": self._managed_provider_record_by_id(target_provider_id)}

    async def _provider_manager_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.delete")
        provider_id = (
            str(payload.get("provider_id")).strip()
            if payload.get("provider_id") is not None
            else None
        )
        provider_source_id = (
            str(payload.get("provider_source_id")).strip()
            if payload.get("provider_source_id") is not None
            else None
        )
        if not provider_id and not provider_source_id:
            raise AstrBotError.invalid_input(
                "provider.manager.delete requires provider_id or provider_source_id"
            )
        deleted: list[dict[str, Any]] = []
        if provider_id:
            record = self._managed_provider_record_by_id(provider_id)
            if record is not None:
                deleted.append(record)
            self._provider_configs.pop(provider_id, None)
        else:
            for record_id, record in list(self._provider_configs.items()):
                if (
                    str(record.get("provider_source_id", "")).strip()
                    != provider_source_id
                ):
                    continue
                deleted_record = self._managed_provider_record_by_id(record_id)
                if deleted_record is not None:
                    deleted.append(deleted_record)
                self._provider_configs.pop(record_id, None)
        deleted_ids = {str(item.get("id", "")) for item in deleted}
        for kind, items in list(self._provider_catalog.items()):
            self._provider_catalog[kind] = [
                item for item in items if str(item.get("id", "")) not in deleted_ids
            ]
            if self._active_provider_ids.get(kind) in deleted_ids:
                catalog = self._provider_catalog.get(kind, [])
                self._active_provider_ids[kind] = (
                    str(catalog[0].get("id")) if catalog else None
                )
        for record in deleted:
            self._emit_provider_change(
                str(record.get("id", "")),
                str(record.get("provider_type", "")),
                None,
            )
        return {}

    async def _provider_manager_get_insts(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("provider.manager.get_insts")
        return {
            "providers": [
                self._managed_provider_record(item, loaded=True)
                for item in self._provider_catalog.get("chat", [])
            ]
        }

    async def _provider_manager_watch_changes(
        self, request_id: str, _payload: dict[str, Any], _token
    ) -> StreamExecution:
        self._require_reserved_plugin("provider.manager.watch_changes")
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._provider_change_subscriptions[request_id] = queue

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            try:
                while True:
                    yield await queue.get()
            finally:
                self._provider_change_subscriptions.pop(request_id, None)

        return StreamExecution(
            iterator=iterator(),
            finalize=lambda _chunks: {},
            collect_chunks=False,
        )

    async def _platform_manager_get_by_id(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("platform.manager.get_by_id")
        platform_id = str(payload.get("platform_id", "")).strip()
        platform = next(
            (
                dict(item)
                for item in self._platform_instances
                if str(item.get("id", "")) == platform_id
            ),
            None,
        )
        return {"platform": platform}

    async def _platform_manager_clear_errors(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("platform.manager.clear_errors")
        platform_id = str(payload.get("platform_id", "")).strip()
        for item in self._platform_instances:
            if str(item.get("id", "")) != platform_id:
                continue
            item["errors"] = []
            item["last_error"] = None
            if str(item.get("status", "")) == "error":
                item["status"] = "running"
            break
        return {}

    async def _platform_manager_get_stats(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._require_reserved_plugin("platform.manager.get_stats")
        platform_id = str(payload.get("platform_id", "")).strip()
        for item in self._platform_instances:
            if str(item.get("id", "")) != platform_id:
                continue
            stats = item.get("stats")
            if isinstance(stats, dict):
                return {"stats": dict(stats)}
            errors = item.get("errors")
            last_error = item.get("last_error")
            meta = item.get("meta")
            return {
                "stats": {
                    "id": platform_id,
                    "type": str(item.get("type", "")),
                    "display_name": str(item.get("name", platform_id)),
                    "status": str(item.get("status", "pending")),
                    "started_at": item.get("started_at"),
                    "error_count": len(errors) if isinstance(errors, list) else 0,
                    "last_error": dict(last_error)
                    if isinstance(last_error, dict)
                    else None,
                    "unified_webhook": bool(item.get("unified_webhook", False)),
                    "meta": dict(meta) if isinstance(meta, dict) else {},
                }
            }
        return {"stats": None}

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

    async def _llm_tool_manager_remove(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        plugin_id = self._require_caller_plugin_id("llm_tool.manager.remove")
        plugin = self._plugins.get(plugin_id)
        if plugin is None:
            return {"removed": False}
        name = str(payload.get("name", "")).strip()
        removed = plugin.llm_tools.pop(name, None) is not None
        plugin.active_llm_tools.discard(name)
        return {"removed": removed}

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

    def _register_provider_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("provider.get_using", "获取当前聊天 Provider"),
            call_handler=self._provider_get_using,
        )
        self.register(
            self._builtin_descriptor("provider.get_by_id", "按 ID 获取 Provider"),
            call_handler=self._provider_get_by_id,
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
            self._builtin_descriptor(
                "provider.list_all_rerank",
                "列出 Rerank Providers",
            ),
            call_handler=self._provider_list_all_rerank,
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
            self._builtin_descriptor("provider.stt.get_text", "STT 转写"),
            call_handler=self._provider_stt_get_text,
        )
        self.register(
            self._builtin_descriptor("provider.tts.get_audio", "TTS 合成音频"),
            call_handler=self._provider_tts_get_audio,
        )
        self.register(
            self._builtin_descriptor(
                "provider.tts.support_stream",
                "检查 TTS 流式支持",
            ),
            call_handler=self._provider_tts_support_stream,
        )
        self.register(
            self._builtin_descriptor(
                "provider.tts.get_audio_stream",
                "流式 TTS 音频输出",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._provider_tts_get_audio_stream,
        )
        self.register(
            self._builtin_descriptor(
                "provider.embedding.get_embedding",
                "获取单条向量",
            ),
            call_handler=self._provider_embedding_get_embedding,
        )
        self.register(
            self._builtin_descriptor(
                "provider.embedding.get_embeddings",
                "批量获取向量",
            ),
            call_handler=self._provider_embedding_get_embeddings,
        )
        self.register(
            self._builtin_descriptor(
                "provider.embedding.get_dim",
                "获取向量维度",
            ),
            call_handler=self._provider_embedding_get_dim,
        )
        self.register(
            self._builtin_descriptor("provider.rerank.rerank", "文档重排序"),
            call_handler=self._provider_rerank_rerank,
        )

    def _register_provider_manager_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("provider.manager.set", "设置当前 Provider"),
            call_handler=self._provider_manager_set,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.get_by_id",
                "按 ID 获取 Provider 管理记录",
            ),
            call_handler=self._provider_manager_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.get_merged_provider_config",
                "获取 Provider 合并配置",
            ),
            call_handler=self._provider_manager_get_merged_provider_config,
        )
        self.register(
            self._builtin_descriptor("provider.manager.load", "运行时加载 Provider"),
            call_handler=self._provider_manager_load,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.terminate",
                "终止已加载的 Provider",
            ),
            call_handler=self._provider_manager_terminate,
        )
        self.register(
            self._builtin_descriptor("provider.manager.create", "创建 Provider"),
            call_handler=self._provider_manager_create,
        )
        self.register(
            self._builtin_descriptor("provider.manager.update", "更新 Provider"),
            call_handler=self._provider_manager_update,
        )
        self.register(
            self._builtin_descriptor("provider.manager.delete", "删除 Provider"),
            call_handler=self._provider_manager_delete,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.get_insts",
                "列出已加载聊天 Provider",
            ),
            call_handler=self._provider_manager_get_insts,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.watch_changes",
                "订阅 Provider 变更",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._provider_manager_watch_changes,
        )

    def _register_agent_tool_capabilities(self) -> None:
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
            self._builtin_descriptor("llm_tool.manager.remove", "动态移除 LLM 工具"),
            call_handler=self._llm_tool_manager_remove,
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
