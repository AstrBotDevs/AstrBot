from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any, cast

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.entities import LLMToolSpec, ProviderMeta, ToolCallsResult
from astrbot_sdk.llm.entities import ProviderType as SDKProviderType
from astrbot_sdk.runtime.capability_router import StreamExecution

from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ..bridge_base import _get_runtime_provider_types, _get_runtime_tool_types
from ._host import CapabilityMixinHost


class ProviderCapabilityMixin(CapabilityMixinHost):
    def _register_provider_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("provider.get_using", "Get active provider"),
            call_handler=self._provider_get_using,
        )
        self.register(
            self._builtin_descriptor("provider.get_by_id", "Get provider by id"),
            call_handler=self._provider_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "provider.get_current_chat_provider_id",
                "Get active chat provider id",
            ),
            call_handler=self._provider_get_current_chat_provider_id,
        )
        self.register(
            self._builtin_descriptor("provider.list_all", "List chat providers"),
            call_handler=self._provider_list_all,
        )
        self.register(
            self._builtin_descriptor("provider.list_all_tts", "List tts providers"),
            call_handler=self._provider_list_all_tts,
        )
        self.register(
            self._builtin_descriptor("provider.list_all_stt", "List stt providers"),
            call_handler=self._provider_list_all_stt,
        )
        self.register(
            self._builtin_descriptor(
                "provider.list_all_embedding",
                "List embedding providers",
            ),
            call_handler=self._provider_list_all_embedding,
        )
        self.register(
            self._builtin_descriptor(
                "provider.list_all_rerank",
                "List rerank providers",
            ),
            call_handler=self._provider_list_all_rerank,
        )
        self.register(
            self._builtin_descriptor(
                "provider.get_using_tts",
                "Get active tts provider",
            ),
            call_handler=self._provider_get_using_tts,
        )
        self.register(
            self._builtin_descriptor(
                "provider.get_using_stt",
                "Get active stt provider",
            ),
            call_handler=self._provider_get_using_stt,
        )
        self.register(
            self._builtin_descriptor(
                "provider.stt.get_text",
                "Transcribe audio with STT provider",
            ),
            call_handler=self._provider_stt_get_text,
        )
        self.register(
            self._builtin_descriptor(
                "provider.tts.get_audio",
                "Synthesize audio with TTS provider",
            ),
            call_handler=self._provider_tts_get_audio,
        )
        self.register(
            self._builtin_descriptor(
                "provider.tts.support_stream",
                "Check whether TTS provider supports native streaming",
            ),
            call_handler=self._provider_tts_support_stream,
        )
        self.register(
            self._builtin_descriptor(
                "provider.tts.get_audio_stream",
                "Stream audio with TTS provider",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._provider_tts_get_audio_stream,
        )
        self.register(
            self._builtin_descriptor(
                "provider.embedding.get_embedding",
                "Get embedding vector",
            ),
            call_handler=self._provider_embedding_get_embedding,
        )
        self.register(
            self._builtin_descriptor(
                "provider.embedding.get_embeddings",
                "Get embedding vectors in batch",
            ),
            call_handler=self._provider_embedding_get_embeddings,
        )
        self.register(
            self._builtin_descriptor(
                "provider.embedding.get_dim",
                "Get embedding dimension",
            ),
            call_handler=self._provider_embedding_get_dim,
        )
        self.register(
            self._builtin_descriptor(
                "provider.rerank.rerank",
                "Rerank documents",
            ),
            call_handler=self._provider_rerank_rerank,
        )
        self.register(
            self._builtin_descriptor(
                "llm_tool.manager.get",
                "Get registered and active sdk llm tools",
            ),
            call_handler=self._llm_tool_manager_get,
        )
        self.register(
            self._builtin_descriptor(
                "llm_tool.manager.activate",
                "Activate sdk llm tool",
            ),
            call_handler=self._llm_tool_manager_activate,
        )
        self.register(
            self._builtin_descriptor(
                "llm_tool.manager.deactivate",
                "Deactivate sdk llm tool",
            ),
            call_handler=self._llm_tool_manager_deactivate,
        )
        self.register(
            self._builtin_descriptor(
                "llm_tool.manager.add",
                "Register sdk llm tool metadata",
            ),
            call_handler=self._llm_tool_manager_add,
        )
        self.register(
            self._builtin_descriptor(
                "llm_tool.manager.remove",
                "Unregister sdk llm tool metadata",
            ),
            call_handler=self._llm_tool_manager_remove,
        )
        self.register(
            self._builtin_descriptor("agent.tool_loop.run", "Run sdk tool loop agent"),
            call_handler=self._agent_tool_loop_run,
        )
        self.register(
            self._builtin_descriptor("agent.registry.list", "List sdk agents"),
            call_handler=self._agent_registry_list,
        )
        self.register(
            self._builtin_descriptor("agent.registry.get", "Get sdk agent"),
            call_handler=self._agent_registry_get,
        )

    def _register_provider_manager_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("provider.manager.set", "Set active provider"),
            call_handler=self._provider_manager_set,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.get_by_id",
                "Get managed provider record by id",
            ),
            call_handler=self._provider_manager_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.get_merged_provider_config",
                "Get merged managed provider config by id",
            ),
            call_handler=self._provider_manager_get_merged_provider_config,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.load",
                "Load a provider instance without persisting config",
            ),
            call_handler=self._provider_manager_load,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.terminate",
                "Terminate a loaded provider instance",
            ),
            call_handler=self._provider_manager_terminate,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.create",
                "Create and load a provider config",
            ),
            call_handler=self._provider_manager_create,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.update",
                "Update and reload a provider config",
            ),
            call_handler=self._provider_manager_update,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.delete",
                "Delete a provider config",
            ),
            call_handler=self._provider_manager_delete,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.get_insts",
                "List loaded chat provider instances",
            ),
            call_handler=self._provider_manager_get_insts,
        )
        self.register(
            self._builtin_descriptor(
                "provider.manager.watch_changes",
                "Stream provider change events",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._provider_manager_watch_changes,
        )

    @staticmethod
    def _provider_to_payload(provider: Any | None) -> dict[str, Any] | None:
        if provider is None:
            return None
        meta = provider.meta()
        return ProviderCapabilityMixin._provider_meta_to_payload(meta)

    @staticmethod
    def _normalize_sdk_provider_type(value: Any) -> SDKProviderType:
        if isinstance(value, SDKProviderType):
            return value
        raw_provider_type = getattr(value, "provider_type", value)
        provider_type_value = (
            str(raw_provider_type.value)
            if hasattr(raw_provider_type, "value")
            else str(raw_provider_type)
        )
        try:
            return SDKProviderType(provider_type_value)
        except ValueError:
            return SDKProviderType.CHAT_COMPLETION

    @classmethod
    def _provider_meta_to_payload(cls, meta: Any) -> dict[str, Any]:
        provider_type = cls._normalize_sdk_provider_type(meta)
        return ProviderMeta(
            id=str(getattr(meta, "id", "")),
            model=(
                str(getattr(meta, "model", ""))
                if getattr(meta, "model", None) is not None
                else None
            ),
            type=str(getattr(meta, "type", "")),
            provider_type=provider_type,
        ).to_payload()

    @classmethod
    def _managed_provider_from_config(
        cls,
        provider_config: dict[str, Any] | None,
        *,
        loaded: bool,
    ) -> dict[str, Any] | None:
        if not isinstance(provider_config, dict):
            return None
        provider_id = str(provider_config.get("id", "")).strip()
        provider_type_text = str(provider_config.get("type", "")).strip()
        if not provider_id or not provider_type_text:
            return None
        provider_type = cls._normalize_sdk_provider_type(
            provider_config.get("provider_type", SDKProviderType.CHAT_COMPLETION.value)
        )
        return {
            "id": provider_id,
            "model": (
                str(provider_config.get("model"))
                if provider_config.get("model") is not None
                else None
            ),
            "type": provider_type_text,
            "provider_type": provider_type.value,
            "loaded": bool(loaded),
            "enabled": bool(provider_config.get("enable", True)),
            "provider_source_id": (
                str(provider_config.get("provider_source_id"))
                if provider_config.get("provider_source_id") is not None
                else None
            ),
        }

    @classmethod
    def _managed_provider_to_payload(
        cls, provider: Any | None
    ) -> dict[str, Any] | None:
        if provider is None:
            return None
        meta_payload = cls._provider_to_payload(provider)
        if meta_payload is None:
            return None
        provider_config = getattr(provider, "provider_config", None)
        return {
            **meta_payload,
            "loaded": True,
            "enabled": bool(
                provider_config.get("enable", True)
                if isinstance(provider_config, dict)
                else True
            ),
            "provider_source_id": (
                str(provider_config.get("provider_source_id"))
                if isinstance(provider_config, dict)
                and provider_config.get("provider_source_id") is not None
                else None
            ),
        }

    def _find_provider_config_by_id(self, provider_id: str) -> dict[str, Any] | None:
        provider_manager = getattr(self._star_context, "provider_manager", None)
        providers_config = getattr(provider_manager, "providers_config", None)
        if not isinstance(providers_config, list):
            return None
        for item in providers_config:
            if not isinstance(item, dict):
                continue
            if str(item.get("id", "")).strip() == provider_id:
                return dict(item)
        return None

    def _managed_provider_payload_by_id(
        self,
        provider_id: str,
        *,
        fallback_config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        normalized_provider_id = str(provider_id).strip()
        if not normalized_provider_id:
            return None
        provider = self._star_context.get_provider_by_id(normalized_provider_id)
        payload = self._managed_provider_to_payload(provider)
        if payload is not None:
            return payload
        provider_config = self._find_provider_config_by_id(normalized_provider_id)
        if provider_config is None:
            provider_config = (
                dict(fallback_config) if isinstance(fallback_config, dict) else None
            )
        return self._managed_provider_from_config(provider_config, loaded=False)

    def _resolve_current_chat_provider_id(
        self,
        request_context: Any | None,
    ) -> str | None:
        if request_context is None:
            return None
        provider = self._star_context.get_using_provider(
            request_context.event.unified_msg_origin
        )
        if provider is None:
            return None
        meta = provider.meta()
        return str(getattr(meta, "id", "") or "")

    async def _provider_get_using(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        provider = self._star_context.get_using_provider(payload.get("umo"))
        return {"provider": self._provider_to_payload(provider)}

    async def _provider_get_current_chat_provider_id(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        provider = self._star_context.get_using_provider(payload.get("umo"))
        if provider is None:
            return {"provider_id": None}
        return {"provider_id": str(provider.meta().id)}

    async def _provider_get_by_id(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        provider = self._get_provider_by_id(payload, "provider.get_by_id")
        return {"provider": self._provider_to_payload(provider)}

    def _provider_list_payload(self, providers: list[Any]) -> dict[str, Any]:
        return {
            "providers": [
                payload
                for payload in (
                    self._provider_to_payload(provider) for provider in providers
                )
                if payload is not None
            ]
        }

    async def _provider_list_all(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return self._provider_list_payload(self._star_context.get_all_providers())

    async def _provider_list_all_tts(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return self._provider_list_payload(self._star_context.get_all_tts_providers())

    async def _provider_list_all_stt(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return self._provider_list_payload(self._star_context.get_all_stt_providers())

    async def _provider_list_all_embedding(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return self._provider_list_payload(
            self._star_context.get_all_embedding_providers()
        )

    async def _provider_list_all_rerank(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return self._provider_list_payload(
            self._star_context.get_all_rerank_providers()
        )

    async def _provider_get_using_tts(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        provider = self._star_context.get_using_tts_provider(payload.get("umo"))
        return {"provider": self._provider_to_payload(provider)}

    async def _provider_get_using_stt(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        provider = self._star_context.get_using_stt_provider(payload.get("umo"))
        return {"provider": self._provider_to_payload(provider)}

    @staticmethod
    def _tts_stream_texts_from_payload(payload: dict[str, Any]) -> list[str]:
        text = payload.get("text")
        if isinstance(text, str):
            return [text]
        text_chunks = payload.get("text_chunks")
        if isinstance(text_chunks, list):
            chunks = [str(item) for item in text_chunks]
            if chunks:
                return chunks
        raise AstrBotError.invalid_input(
            "provider.tts.get_audio_stream requires text or text_chunks"
        )

    def _get_provider_by_id(
        self,
        payload: dict[str, Any],
        capability_name: str,
    ) -> Any:
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            raise AstrBotError.invalid_input(
                f"{capability_name} requires provider_id",
            )
        provider = self._star_context.get_provider_by_id(provider_id)
        if provider is None:
            raise AstrBotError.invalid_input(
                f"{capability_name} unknown provider_id: {provider_id}",
            )
        return provider

    def _get_typed_provider(
        self,
        payload: dict[str, Any],
        capability_name: str,
        provider_label: str,
        expected_type: type[Any],
    ) -> Any:
        provider = self._get_provider_by_id(payload, capability_name)
        if not isinstance(provider, expected_type):
            raise AstrBotError.invalid_input(
                f"{capability_name} requires a {provider_label} provider",
            )
        return provider

    async def _provider_stt_get_text(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        stt_provider_cls, _, _, _ = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.stt.get_text",
            "speech_to_text",
            stt_provider_cls,
        )
        return {"text": await provider.get_text(str(payload.get("audio_url", "")))}

    async def _provider_tts_get_audio(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        _, tts_provider_cls, _, _ = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.tts.get_audio",
            "text_to_speech",
            tts_provider_cls,
        )
        return {"audio_path": await provider.get_audio(str(payload.get("text", "")))}

    async def _provider_tts_support_stream(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        _, tts_provider_cls, _, _ = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.tts.support_stream",
            "text_to_speech",
            tts_provider_cls,
        )
        return {"supported": bool(provider.support_stream())}

    async def _provider_tts_get_audio_stream(
        self,
        _request_id: str,
        payload: dict[str, Any],
        token,
    ) -> StreamExecution:
        _, tts_provider_cls, _, _ = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.tts.get_audio_stream",
            "text_to_speech",
            tts_provider_cls,
        )
        texts = self._tts_stream_texts_from_payload(payload)
        text_queue: asyncio.Queue[str | None] = asyncio.Queue()
        audio_queue: asyncio.Queue[bytes | tuple[str, bytes] | None] = asyncio.Queue()
        for text in texts:
            await text_queue.put(text)
        await text_queue.put(None)
        state: dict[str, BaseException] = {}

        async def producer() -> None:
            try:
                await provider.get_audio_stream(text_queue, audio_queue)
            except Exception as exc:  # pragma: no cover - provider-specific failures
                state["error"] = exc
            finally:
                await audio_queue.put(None)

        task = asyncio.create_task(producer())

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            try:
                while True:
                    token.raise_if_cancelled()
                    item = await audio_queue.get()
                    if item is None:
                        break
                    chunk_text: str | None = None
                    chunk_audio: bytes | bytearray
                    if isinstance(item, tuple):
                        chunk_text = str(item[0])
                        chunk_audio = item[1]
                    else:
                        chunk_audio = item
                    yield {
                        "audio_base64": base64.b64encode(bytes(chunk_audio)).decode(
                            "ascii"
                        ),
                        "text": chunk_text,
                    }
                error = state.get("error")
                if error is not None:
                    raise error
            finally:
                if not task.done():
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task
                else:
                    with contextlib.suppress(Exception):
                        await task

        def finalize(chunks: list[dict[str, Any]]) -> dict[str, Any]:
            return chunks[-1] if chunks else {"audio_base64": "", "text": None}

        return StreamExecution(iterator=iterator(), finalize=finalize)

    async def _provider_embedding_get_embedding(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        _, _, embedding_provider_cls, _ = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.embedding.get_embedding",
            "embedding",
            embedding_provider_cls,
        )
        return {"embedding": await provider.get_embedding(str(payload.get("text", "")))}

    async def _provider_embedding_get_embeddings(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        _, _, embedding_provider_cls, _ = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.embedding.get_embeddings",
            "embedding",
            embedding_provider_cls,
        )
        texts = payload.get("texts")
        if not isinstance(texts, list):
            raise AstrBotError.invalid_input(
                "provider.embedding.get_embeddings requires texts",
            )
        return {
            "embeddings": await provider.get_embeddings([str(item) for item in texts])
        }

    async def _provider_embedding_get_dim(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        _, _, embedding_provider_cls, _ = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.embedding.get_dim",
            "embedding",
            embedding_provider_cls,
        )
        return {"dim": int(provider.get_dim())}

    async def _provider_rerank_rerank(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        _, _, _, rerank_provider_cls = _get_runtime_provider_types()
        provider = self._get_typed_provider(
            payload,
            "provider.rerank.rerank",
            "rerank",
            rerank_provider_cls,
        )
        documents = payload.get("documents")
        if not isinstance(documents, list):
            raise AstrBotError.invalid_input(
                "provider.rerank.rerank requires documents",
            )
        normalized_documents = [str(item) for item in documents]
        top_n = payload.get("top_n")
        results = await provider.rerank(
            str(payload.get("query", "")),
            normalized_documents,
            int(top_n) if top_n is not None else None,
        )
        serialized = []
        for item in results:
            index = int(getattr(item, "index", 0))
            serialized.append(
                {
                    "index": index,
                    "score": float(getattr(item, "relevance_score", 0.0)),
                    "document": normalized_documents[index]
                    if 0 <= index < len(normalized_documents)
                    else "",
                }
            )
        return {"results": serialized}

    @staticmethod
    def _normalize_provider_config_payload(
        payload: Any,
        capability_name: str,
        field_name: str,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise AstrBotError.invalid_input(
                f"{capability_name} requires {field_name} object"
            )
        return dict(payload)

    @staticmethod
    def _core_provider_type(value: Any, capability_name: str):
        from astrbot.core.provider.entities import ProviderType as CoreProviderType

        normalized = str(value).strip()
        try:
            return CoreProviderType(normalized)
        except ValueError as exc:
            raise AstrBotError.invalid_input(
                f"{capability_name} requires a valid provider_type"
            ) from exc

    async def _provider_manager_set(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.set")
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.set requires provider_id"
            )
        await self._star_context.provider_manager.set_provider(
            provider_id=provider_id,
            provider_type=self._core_provider_type(
                payload.get("provider_type"),
                "provider.manager.set",
            ),
            umo=(
                str(payload.get("umo"))
                if payload.get("umo") is not None and str(payload.get("umo")).strip()
                else None
            ),
        )
        return {}

    async def _provider_manager_get_by_id(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.get_by_id")
        provider_id = str(payload.get("provider_id", "")).strip()
        return {"provider": self._managed_provider_payload_by_id(provider_id)}

    async def _provider_manager_get_merged_provider_config(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(
            request_id,
            "provider.manager.get_merged_provider_config",
        )
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.get_merged_provider_config requires provider_id"
            )
        provider_manager = getattr(self._star_context, "provider_manager", None)
        get_merged_provider_config = getattr(
            provider_manager,
            "get_merged_provider_config",
            None,
        )
        if provider_manager is None or not callable(get_merged_provider_config):
            raise AstrBotError.invalid_input(
                "Provider manager does not support merged config lookup"
            )
        provider_config = self._find_provider_config_by_id(provider_id)
        if provider_config is None:
            raise AstrBotError.invalid_input(
                "provider.manager.get_merged_provider_config unknown provider_id"
            )
        merged_config = cast(
            dict[str, Any], get_merged_provider_config(provider_config)
        )
        return {"config": dict(merged_config)}

    async def _provider_manager_load(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.load")
        provider_config = self._normalize_provider_config_payload(
            payload.get("provider_config"),
            "provider.manager.load",
            "provider_config",
        )
        await self._star_context.provider_manager.load_provider(provider_config)
        provider_id = str(provider_config.get("id", "")).strip()
        return {
            "provider": self._managed_provider_payload_by_id(
                provider_id,
                fallback_config=provider_config,
            )
        }

    async def _provider_manager_terminate(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.terminate")
        provider_id = str(payload.get("provider_id", "")).strip()
        if not provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.terminate requires provider_id"
            )
        await self._star_context.provider_manager.terminate_provider(provider_id)
        return {}

    async def _provider_manager_create(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.create")
        provider_config = self._normalize_provider_config_payload(
            payload.get("provider_config"),
            "provider.manager.create",
            "provider_config",
        )
        await self._star_context.provider_manager.create_provider(provider_config)
        provider_id = str(provider_config.get("id", "")).strip()
        return {"provider": self._managed_provider_payload_by_id(provider_id)}

    async def _provider_manager_update(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.update")
        origin_provider_id = str(payload.get("origin_provider_id", "")).strip()
        if not origin_provider_id:
            raise AstrBotError.invalid_input(
                "provider.manager.update requires origin_provider_id"
            )
        new_config = self._normalize_provider_config_payload(
            payload.get("new_config"),
            "provider.manager.update",
            "new_config",
        )
        await self._star_context.provider_manager.update_provider(
            origin_provider_id,
            new_config,
        )
        target_provider_id = str(new_config.get("id") or origin_provider_id).strip()
        return {"provider": self._managed_provider_payload_by_id(target_provider_id)}

    async def _provider_manager_delete(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.delete")
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
        await self._star_context.provider_manager.delete_provider(
            provider_id=provider_id or None,
            provider_source_id=provider_source_id or None,
        )
        return {}

    async def _provider_manager_get_insts(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(request_id, "provider.manager.get_insts")
        provider_manager = getattr(self._star_context, "provider_manager", None)
        if provider_manager is None or not hasattr(provider_manager, "get_insts"):
            return {"providers": []}
        return {
            "providers": [
                payload
                for payload in (
                    self._managed_provider_to_payload(provider)
                    for provider in list(provider_manager.get_insts())
                )
                if payload is not None
            ]
        }

    async def _provider_manager_watch_changes(
        self,
        request_id: str,
        _payload: dict[str, Any],
        token,
    ) -> StreamExecution:
        self._require_reserved_plugin(request_id, "provider.manager.watch_changes")
        provider_manager = getattr(self._star_context, "provider_manager", None)
        if provider_manager is None or not hasattr(
            provider_manager, "register_provider_change_hook"
        ):
            raise AstrBotError.invalid_input("Provider manager does not support hooks")
        unregister_hook = getattr(
            provider_manager,
            "unregister_provider_change_hook",
            None,
        )
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def hook(provider_id: str, provider_type: Any, umo: str | None) -> None:
            event = {
                "provider_id": str(provider_id),
                "provider_type": self._normalize_sdk_provider_type(provider_type).value,
                "umo": str(umo) if umo is not None else None,
            }
            loop.call_soon_threadsafe(queue.put_nowait, event)

        provider_manager.register_provider_change_hook(hook)

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            try:
                while True:
                    token.raise_if_cancelled()
                    yield await queue.get()
            finally:
                if callable(unregister_hook):
                    unregister_hook(hook)

        return StreamExecution(
            iterator=iterator(),
            finalize=lambda _chunks: {},
            collect_chunks=False,
        )

    async def _llm_tool_manager_get(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {
            "registered": [
                item.to_payload()
                for item in self._plugin_bridge.get_registered_llm_tools(plugin_id)
            ],
            "active": [
                item.to_payload()
                for item in self._plugin_bridge.get_active_llm_tools(plugin_id)
            ],
        }

    async def _llm_tool_manager_activate(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {
            "activated": self._plugin_bridge.activate_llm_tool(
                plugin_id, str(payload.get("name", ""))
            )
        }

    async def _llm_tool_manager_deactivate(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {
            "deactivated": self._plugin_bridge.deactivate_llm_tool(
                plugin_id, str(payload.get("name", ""))
            )
        }

    async def _llm_tool_manager_add(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        tools_payload = payload.get("tools")
        if not isinstance(tools_payload, list):
            raise AstrBotError.invalid_input("llm_tool.manager.add requires tools list")
        tools = [
            LLMToolSpec.from_payload(item)
            for item in tools_payload
            if isinstance(item, dict)
        ]
        return {"names": self._plugin_bridge.add_llm_tools(plugin_id, tools)}

    async def _llm_tool_manager_remove(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {
            "removed": self._plugin_bridge.remove_llm_tool(
                plugin_id,
                str(payload.get("name", "")),
            )
        }

    async def _agent_registry_list(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        return {
            "agents": [
                item.to_payload()
                for item in self._plugin_bridge.get_registered_agents(plugin_id)
            ]
        }

    async def _agent_registry_get(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        agent = self._plugin_bridge.get_registered_agent(
            plugin_id, str(payload.get("name", ""))
        )
        return {"agent": agent.to_payload() if agent is not None else None}

    def _select_llm_tools_for_request(
        self,
        plugin_id: str,
        payload: dict[str, Any],
    ) -> list[LLMToolSpec]:
        active_specs = {
            item.name: item
            for item in self._plugin_bridge.get_request_tool_specs(plugin_id)
        }
        requested = payload.get("tool_names")
        if not isinstance(requested, list) or not requested:
            return list(active_specs.values())
        names = [str(item) for item in requested if str(item).strip()]
        return [active_specs[name] for name in names if name in active_specs]

    def _make_sdk_tool_handler(
        self,
        *,
        plugin_id: str,
        tool_spec: LLMToolSpec,
        tool_call_timeout: int,
    ):
        async def _handler(event: AstrMessageEvent, **tool_args: Any) -> str | None:
            record = self._plugin_bridge._records.get(plugin_id)
            if record is None or record.session is None:
                return json.dumps(
                    ToolCallsResult(
                        tool_name=tool_spec.name,
                        content="SDK plugin worker is unavailable",
                        success=False,
                    ).to_payload(),
                    ensure_ascii=False,
                )
            request_id = f"sdk_tool_{plugin_id}_{uuid.uuid4().hex}"
            dispatch_token = (
                self._plugin_bridge._get_dispatch_token(event) or uuid.uuid4().hex
            )
            get_overlay = getattr(
                self._plugin_bridge,
                "get_request_overlay_by_token",
                lambda _dispatch_token: None,
            )
            event_payload = self._plugin_bridge._build_sdk_event_payload(
                event,
                dispatch_token=dispatch_token,
                plugin_id=plugin_id,
                request_id=request_id,
                overlay=get_overlay(dispatch_token),
            )
            call_payload = {
                "plugin_id": plugin_id,
                "tool_name": tool_spec.name,
                "handler_ref": tool_spec.handler_ref,
                "tool_args": json.loads(
                    json.dumps(tool_args, ensure_ascii=False, default=str)
                ),
                "event": event_payload,
            }
            try:
                if tool_spec.handler_capability == "internal.mcp.local.execute":
                    handler_ref = json.loads(tool_spec.handler_ref or "{}")
                    output = await asyncio.wait_for(
                        self.execute(
                            "internal.mcp.local.execute",
                            {
                                "plugin_id": plugin_id,
                                "server_name": str(
                                    handler_ref.get("server_name", "")
                                ).strip(),
                                "tool_name": str(
                                    handler_ref.get("tool_name", "")
                                ).strip(),
                                "tool_args": call_payload["tool_args"],
                            },
                            stream=False,
                            cancel_token=None,
                            request_id=request_id,
                        ),
                        timeout=tool_call_timeout,
                    )
                elif tool_spec.handler_capability:
                    output = await asyncio.wait_for(
                        record.session.invoke_capability(
                            tool_spec.handler_capability,
                            call_payload,
                            request_id=request_id,
                        ),
                        timeout=tool_call_timeout,
                    )
                else:
                    output = await asyncio.wait_for(
                        record.session.invoke_capability(
                            "internal.llm_tool.execute",
                            call_payload,
                            request_id=request_id,
                        ),
                        timeout=tool_call_timeout,
                    )
            except TimeoutError:
                return json.dumps(
                    ToolCallsResult(
                        tool_name=tool_spec.name,
                        content=(
                            f"Tool execution timeout after {tool_call_timeout} seconds"
                        ),
                        success=False,
                    ).to_payload(),
                    ensure_ascii=False,
                )
            except Exception as exc:
                return json.dumps(
                    ToolCallsResult(
                        tool_name=tool_spec.name,
                        content=f"Tool execution failed: {exc}",
                        success=False,
                    ).to_payload(),
                    ensure_ascii=False,
                )
            if not isinstance(output, dict):
                return str(output)
            content = output.get("content")
            if output.get("success", True):
                # Keep None distinct from an empty string so tools can signal
                # "no content" without fabricating a textual result.
                return None if content is None else str(content)
            return json.dumps(
                ToolCallsResult(
                    tool_name=tool_spec.name,
                    content=str(content or ""),
                    success=False,
                ).to_payload(),
                ensure_ascii=False,
            )

        return _handler

    def _build_sdk_toolset(
        self,
        *,
        plugin_id: str,
        payload: dict[str, Any],
        tool_call_timeout: int,
    ) -> Any | None:
        tool_specs = self._select_llm_tools_for_request(plugin_id, payload)
        if not tool_specs:
            return None
        function_tool_cls, tool_set_cls = _get_runtime_tool_types()
        tool_set = tool_set_cls()
        for tool_spec in tool_specs:
            tool_set.add_tool(
                function_tool_cls(
                    name=tool_spec.name,
                    description=tool_spec.description,
                    parameters=tool_spec.parameters_schema,
                    handler=self._make_sdk_tool_handler(
                        plugin_id=plugin_id,
                        tool_spec=tool_spec,
                        tool_call_timeout=tool_call_timeout,
                    ),
                )
            )
        return tool_set

    def _llm_response_to_payload(self, response: Any) -> dict[str, Any]:
        usage = None
        if response.usage is not None:
            usage = {
                "input_tokens": response.usage.input,
                "output_tokens": response.usage.output,
                "total_tokens": response.usage.total,
            }
        return {
            "text": response.completion_text,
            "usage": usage,
            "finish_reason": "tool_calls" if response.tools_call_ids else "stop",
            "tool_calls": response.to_openai_tool_calls(),
            "role": response.role,
            "reasoning_content": response.reasoning_content or None,
            "reasoning_signature": response.reasoning_signature,
        }

    async def _agent_tool_loop_run(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None:
            raise AstrBotError.invalid_input(
                "tool_loop_agent currently requires a message-bound SDK request"
            )
        provider_id = str(
            payload.get("provider_id") or ""
        ).strip() or self._resolve_current_chat_provider_id(request_context)
        if not provider_id:
            raise AstrBotError.invalid_input("No active chat provider is available")
        tool_call_timeout = int(payload.get("tool_call_timeout") or 60)
        llm_resp = await self._star_context.tool_loop_agent(
            event=request_context.event,
            chat_provider_id=provider_id,
            prompt=(
                str(payload.get("prompt"))
                if payload.get("prompt") is not None
                else None
            ),
            image_urls=[
                str(item)
                for item in payload.get("image_urls", [])
                if isinstance(item, str)
            ],
            tools=self._build_sdk_toolset(
                plugin_id=plugin_id,
                payload=payload,
                tool_call_timeout=tool_call_timeout,
            ),
            system_prompt=str(payload.get("system_prompt") or ""),
            contexts=[
                dict(item)
                for item in payload.get("contexts", [])
                if isinstance(item, dict)
            ],
            max_steps=int(payload.get("max_steps") or 30),
            tool_call_timeout=tool_call_timeout,
        )
        return self._llm_response_to_payload(llm_resp)
