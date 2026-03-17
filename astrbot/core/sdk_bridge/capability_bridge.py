from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import uuid
from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from astrbot_sdk._invocation_context import current_caller_plugin_id
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.llm.entities import (
    LLMToolSpec,
    ProviderMeta,
    ToolCallsResult,
)
from astrbot_sdk.llm.entities import (
    ProviderType as SDKProviderType,
)
from astrbot_sdk.runtime.capability_router import CapabilityRouter, StreamExecution

from astrbot.core.file_token_service import FileTokenService
from astrbot.core.message.components import ComponentTypes, Image, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .event_converter import EventConverter

if TYPE_CHECKING:
    from astrbot.core.agent.tool import ToolSet
    from astrbot.core.provider.entities import LLMResponse
    from astrbot.core.star.context import Context as StarContext


def _get_runtime_sp():
    from astrbot.core import sp

    return sp


def _get_runtime_html_renderer():
    from astrbot.core import html_renderer

    return html_renderer


def _get_runtime_astrbot_config():
    from astrbot.core import astrbot_config

    return astrbot_config


def _get_runtime_file_token_service() -> FileTokenService:
    from astrbot.core import file_token_service

    return cast(FileTokenService, file_token_service)


def _get_runtime_tool_types():
    from astrbot.core.agent.tool import FunctionTool, ToolSet

    return FunctionTool, ToolSet


def _get_runtime_provider_types():
    from astrbot.core.provider.provider import (
        EmbeddingProvider,
        RerankProvider,
        STTProvider,
        TTSProvider,
    )

    return STTProvider, TTSProvider, EmbeddingProvider, RerankProvider


@dataclass(slots=True)
class _EventStreamState:
    request_context: Any
    queue: asyncio.Queue[MessageChain | None]
    task: asyncio.Task[None]


class CoreCapabilityBridge(CapabilityRouter):
    MEMORY_SCOPE = "sdk_memory"

    def __init__(self, *, star_context: StarContext, plugin_bridge) -> None:
        self._star_context = star_context
        self._plugin_bridge = plugin_bridge
        self._event_streams: dict[str, _EventStreamState] = {}
        # CapabilityRouter.__init__() calls _register_builtin_capabilities(),
        # which reaches the override methods on this class, including P1.2.
        super().__init__()
        self._register_p0_5_capabilities()
        self._register_system_capabilities()

    def _register_llm_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("llm.chat", "Send chat request"),
            call_handler=self._llm_chat,
        )
        self.register(
            self._builtin_descriptor(
                "llm.chat_raw",
                "Send chat request and return raw response",
            ),
            call_handler=self._llm_chat_raw,
        )
        self.register(
            self._builtin_descriptor(
                "llm.stream_chat",
                "Stream chat response",
                supports_stream=True,
                cancelable=True,
            ),
            stream_handler=self._llm_stream_chat,
        )

    async def _llm_chat(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        response = await self._call_llm(payload, request_id=request_id)
        return {"text": response.completion_text}

    async def _llm_chat_raw(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        response = await self._call_llm(payload, request_id=request_id)
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

    async def _llm_stream_chat(
        self,
        request_id: str,
        payload: dict[str, Any],
        token,
    ) -> StreamExecution:
        provider, request_kwargs = self._resolve_llm_request(
            payload,
            request_id=request_id,
        )

        async def fallback_iterator() -> AsyncIterator[dict[str, Any]]:
            response = await provider.text_chat(**request_kwargs)
            for char in response.completion_text:
                token.raise_if_cancelled()
                await asyncio.sleep(0)
                yield {"text": char}

        async def iterator() -> AsyncIterator[dict[str, Any]]:
            try:
                stream = provider.text_chat_stream(**request_kwargs)
                yielded_text = False
                async for response in stream:
                    token.raise_if_cancelled()
                    text = response.completion_text
                    if response.is_chunk:
                        if text:
                            yielded_text = True
                            yield {"text": text}
                        continue
                    if text:
                        if yielded_text:
                            yield {"_final_text": text}
                        else:
                            yielded_text = True
                            yield {"text": text, "_final_text": text}
                    else:
                        yield {"_final_text": text}
            except NotImplementedError:
                async for item in fallback_iterator():
                    yield item

        def finalize(chunks: list[dict[str, Any]]) -> dict[str, Any]:
            final_text = None
            for item in reversed(chunks):
                if "_final_text" in item:
                    final_text = str(item.get("_final_text", ""))
                    break
            if final_text is None:
                final_text = "".join(str(item.get("text", "")) for item in chunks)
            return {"text": final_text}

        return StreamExecution(
            iterator=iterator(),
            finalize=finalize,
        )

    async def _call_llm(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> LLMResponse:
        provider, request_kwargs = self._resolve_llm_request(
            payload,
            request_id=request_id,
        )
        return await provider.text_chat(**request_kwargs)

    def _resolve_llm_request(
        self,
        payload: dict[str, Any],
        *,
        request_id: str,
    ) -> tuple[Any, dict[str, Any]]:
        request_context = self._plugin_bridge.resolve_request_session(request_id)
        provider_id = payload.get("provider_id")
        if provider_id:
            provider = self._star_context.get_provider_by_id(str(provider_id))
        else:
            provider = self._star_context.get_using_provider(
                request_context.event.unified_msg_origin
                if request_context is not None
                else None,
            )
        if provider is None:
            raise AstrBotError.internal_error(
                "No active chat provider is available",
                hint="Please configure a chat provider in AstrBot first",
            )
        return provider, self._normalize_llm_payload(payload)

    @staticmethod
    def _normalize_llm_payload(payload: dict[str, Any]) -> dict[str, Any]:
        contexts_payload = payload.get("contexts")
        if contexts_payload is None:
            contexts_payload = payload.get("history")
        contexts = (
            [dict(item) for item in contexts_payload]
            if isinstance(contexts_payload, list)
            else None
        )
        image_urls = payload.get("image_urls")
        tool_calls_result = payload.get("tool_calls_result")
        tools_payload = payload.get("tools")
        request_kwargs: dict[str, Any] = {
            "prompt": str(payload.get("prompt", "")),
            "image_urls": (
                [str(item) for item in image_urls]
                if isinstance(image_urls, list)
                else None
            ),
            "func_tool": (
                CoreCapabilityBridge._build_toolset(tools_payload)
                if isinstance(tools_payload, list)
                else None
            ),
            "contexts": contexts,
            "tool_calls_result": (
                [dict(item) for item in tool_calls_result]
                if isinstance(tool_calls_result, list)
                else None
            ),
            "system_prompt": str(payload.get("system", "")),
            "model": (str(payload["model"]) if payload.get("model") else None),
            "temperature": payload.get("temperature"),
        }
        return request_kwargs

    @staticmethod
    def _to_iso_datetime(value: Any) -> str | None:
        if value is None:
            return None
        isoformat = getattr(value, "isoformat", None)
        if callable(isoformat):
            return str(isoformat())
        if isinstance(value, (int, float)) and value > 0:
            return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
        return None

    @staticmethod
    def _normalize_history_items(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, dict)]
        if isinstance(value, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError, ValueError):
                decoded = json.loads(value)
                if isinstance(decoded, list):
                    return [dict(item) for item in decoded if isinstance(item, dict)]
        return []

    @staticmethod
    def _normalize_persona_dialogs(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if isinstance(item, str)]
        if isinstance(value, str):
            with contextlib.suppress(json.JSONDecodeError, TypeError, ValueError):
                decoded = json.loads(value)
                if isinstance(decoded, list):
                    return [str(item) for item in decoded if isinstance(item, str)]
        return []

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _serialize_persona(self, persona: Any) -> dict[str, Any] | None:
        if persona is None:
            return None
        return {
            "persona_id": str(getattr(persona, "persona_id", "") or ""),
            "system_prompt": str(getattr(persona, "system_prompt", "") or ""),
            "begin_dialogs": self._normalize_persona_dialogs(
                getattr(persona, "begin_dialogs", None)
            ),
            "tools": (
                [str(item) for item in getattr(persona, "tools", [])]
                if isinstance(getattr(persona, "tools", None), list)
                else None
            ),
            "skills": (
                [str(item) for item in getattr(persona, "skills", [])]
                if isinstance(getattr(persona, "skills", None), list)
                else None
            ),
            "custom_error_message": (
                str(getattr(persona, "custom_error_message", ""))
                if getattr(persona, "custom_error_message", None) is not None
                else None
            ),
            "folder_id": (
                str(getattr(persona, "folder_id", ""))
                if getattr(persona, "folder_id", None) is not None
                else None
            ),
            "sort_order": int(getattr(persona, "sort_order", 0) or 0),
            "created_at": self._to_iso_datetime(getattr(persona, "created_at", None)),
            "updated_at": self._to_iso_datetime(getattr(persona, "updated_at", None)),
        }

    def _serialize_conversation(self, conversation: Any) -> dict[str, Any] | None:
        if conversation is None:
            return None
        return {
            "conversation_id": str(getattr(conversation, "cid", "") or ""),
            "session": str(getattr(conversation, "user_id", "") or ""),
            "platform_id": str(getattr(conversation, "platform_id", "") or ""),
            "history": self._normalize_history_items(
                getattr(conversation, "history", None)
            ),
            "title": (
                str(getattr(conversation, "title", ""))
                if getattr(conversation, "title", None) is not None
                else None
            ),
            "persona_id": (
                str(getattr(conversation, "persona_id", ""))
                if getattr(conversation, "persona_id", None) is not None
                else None
            ),
            "created_at": self._to_iso_datetime(
                getattr(conversation, "created_at", None)
            ),
            "updated_at": self._to_iso_datetime(
                getattr(conversation, "updated_at", None)
            ),
            "token_usage": (
                int(getattr(conversation, "token_usage"))
                if getattr(conversation, "token_usage", None) is not None
                else None
            ),
        }

    def _serialize_kb(self, kb_helper_or_record: Any) -> dict[str, Any] | None:
        # KnowledgeBaseManager returns KBHelper for get/create, while some tests
        # pass the knowledge-base record directly. Accept both shapes here.
        kb = getattr(kb_helper_or_record, "kb", kb_helper_or_record)
        if kb is None:
            return None
        return {
            "kb_id": str(getattr(kb, "kb_id", "") or ""),
            "kb_name": str(getattr(kb, "kb_name", "") or ""),
            "description": (
                str(getattr(kb, "description", ""))
                if getattr(kb, "description", None) is not None
                else None
            ),
            "emoji": (
                str(getattr(kb, "emoji", ""))
                if getattr(kb, "emoji", None) is not None
                else None
            ),
            "embedding_provider_id": str(
                getattr(kb, "embedding_provider_id", "") or ""
            ),
            "rerank_provider_id": (
                str(getattr(kb, "rerank_provider_id", ""))
                if getattr(kb, "rerank_provider_id", None) is not None
                else None
            ),
            "chunk_size": (
                int(getattr(kb, "chunk_size"))
                if getattr(kb, "chunk_size", None) is not None
                else None
            ),
            "chunk_overlap": (
                int(getattr(kb, "chunk_overlap"))
                if getattr(kb, "chunk_overlap", None) is not None
                else None
            ),
            "top_k_dense": (
                int(getattr(kb, "top_k_dense"))
                if getattr(kb, "top_k_dense", None) is not None
                else None
            ),
            "top_k_sparse": (
                int(getattr(kb, "top_k_sparse"))
                if getattr(kb, "top_k_sparse", None) is not None
                else None
            ),
            "top_m_final": (
                int(getattr(kb, "top_m_final"))
                if getattr(kb, "top_m_final", None) is not None
                else None
            ),
            "doc_count": int(getattr(kb, "doc_count", 0) or 0),
            "chunk_count": int(getattr(kb, "chunk_count", 0) or 0),
            "created_at": self._to_iso_datetime(getattr(kb, "created_at", None)),
            "updated_at": self._to_iso_datetime(getattr(kb, "updated_at", None)),
        }

    @staticmethod
    def _build_toolset(tools_payload: list[Any]) -> ToolSet:
        function_tool_cls, tool_set_cls = _get_runtime_tool_types()
        tool_set = tool_set_cls()
        for item in tools_payload:
            if not isinstance(item, dict):
                raise AstrBotError.invalid_input("llm tools items must be objects")
            if str(item.get("type", "function")) != "function":
                raise AstrBotError.invalid_input(
                    "Only function tools are supported in AstrBot SDK MVP"
                )
            function_payload = item.get("function")
            if not isinstance(function_payload, dict):
                raise AstrBotError.invalid_input(
                    "llm tools items must contain a function object"
                )
            name = str(function_payload.get("name", "")).strip()
            if not name:
                raise AstrBotError.invalid_input(
                    "llm function tool name must not be empty"
                )
            description = str(function_payload.get("description", "") or "")
            parameters = function_payload.get("parameters")
            if not isinstance(parameters, dict):
                parameters = {"type": "object", "properties": {}}
            tool_set.add_tool(
                function_tool_cls(
                    name=name,
                    description=description,
                    parameters=parameters,
                    handler=None,
                )
            )
        return tool_set

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

    def _register_platform_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("platform.send", "Send plain text"),
            call_handler=self._platform_send,
        )
        self.register(
            self._builtin_descriptor("platform.send_image", "Send image"),
            call_handler=self._platform_send_image,
        )
        self.register(
            self._builtin_descriptor("platform.send_chain", "Send message chain"),
            call_handler=self._platform_send_chain,
        )
        self.register(
            self._builtin_descriptor(
                "platform.send_by_session",
                "Send message chain to a specific session",
            ),
            call_handler=self._platform_send_by_session,
        )
        self.register(
            self._builtin_descriptor("platform.get_group", "Get current group data"),
            call_handler=self._platform_get_group,
        )
        self.register(
            self._builtin_descriptor("platform.get_members", "Get group members"),
            call_handler=self._platform_get_members,
        )
        self.register(
            self._builtin_descriptor(
                "platform.list_instances",
                "List available platform instances",
            ),
            call_handler=self._platform_list_instances,
        )

    async def _platform_send(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session, dispatch_token = self._resolve_dispatch_target(request_id, payload)
        self._plugin_bridge.before_platform_send(dispatch_token)
        await self._star_context.send_message(
            session,
            MessageChain([Plain(str(payload.get("text", "")), convert=False)]),
        )
        return {"message_id": self._plugin_bridge.mark_platform_send(dispatch_token)}

    async def _platform_send_image(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session, dispatch_token = self._resolve_dispatch_target(request_id, payload)
        self._plugin_bridge.before_platform_send(dispatch_token)
        image_url = str(payload.get("image_url", ""))
        component = (
            Image.fromURL(image_url)
            if image_url.startswith(("http://", "https://"))
            else Image.fromFileSystem(image_url)
        )
        await self._star_context.send_message(session, MessageChain([component]))
        return {"message_id": self._plugin_bridge.mark_platform_send(dispatch_token)}

    async def _platform_send_chain(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session, dispatch_token = self._resolve_dispatch_target(request_id, payload)
        self._plugin_bridge.before_platform_send(dispatch_token)
        chain_payload = payload.get("chain")
        if not isinstance(chain_payload, list):
            raise AstrBotError.invalid_input(
                "platform.send_chain requires a chain array"
            )
        await self._star_context.send_message(
            session,
            self._build_core_message_chain(chain_payload),
        )
        return {"message_id": self._plugin_bridge.mark_platform_send(dispatch_token)}

    async def _platform_send_by_session(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        chain_payload = payload.get("chain")
        if not isinstance(chain_payload, list):
            raise AstrBotError.invalid_input(
                "platform.send_by_session requires a chain array"
            )
        session = str(payload.get("session", ""))
        if not session:
            raise AstrBotError.invalid_input(
                "platform.send_by_session requires a session"
            )
        request_context = self._resolve_event_request_context(request_id, payload)
        dispatch_token = None
        if request_context is not None and not request_context.cancelled:
            dispatch_token = request_context.dispatch_token
            self._plugin_bridge.before_platform_send(dispatch_token)
        await self._star_context.send_message(
            session,
            self._build_core_message_chain(chain_payload),
        )
        if dispatch_token is not None:
            return {
                "message_id": self._plugin_bridge.mark_platform_send(dispatch_token)
            }
        return {"message_id": f"sdk_proactive_{uuid.uuid4().hex}"}

    async def _platform_get_group(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_current_group_request_context(
            request_id, payload
        )
        if request_context is None:
            return {"group": None}
        group = await request_context.event.get_group()
        return {"group": self._serialize_group(group)}

    async def _platform_get_members(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_current_group_request_context(
            request_id, payload
        )
        if request_context is None:
            return {"members": []}
        group = await request_context.event.get_group()
        serialized_group = self._serialize_group(group)
        if serialized_group is None:
            return {"members": []}
        members = serialized_group.get("members")
        return {"members": list(members) if isinstance(members, list) else []}

    async def _platform_list_instances(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        platform_manager = getattr(self._star_context, "platform_manager", None)
        if platform_manager is None or not hasattr(platform_manager, "get_insts"):
            return {"platforms": []}
        platforms_payload: list[dict[str, Any]] = []
        for platform in list(platform_manager.get_insts()):
            meta = None
            try:
                meta = platform.meta()
            except Exception:
                continue
            platform_id = str(getattr(meta, "id", "")).strip()
            platform_type = str(getattr(meta, "name", "")).strip()
            if not platform_id or not platform_type:
                continue
            status = getattr(platform, "status", None)
            status_value = getattr(status, "value", status)
            display_name = str(
                getattr(meta, "adapter_display_name", None) or platform_type
            )
            platforms_payload.append(
                {
                    "id": platform_id,
                    "name": display_name,
                    "type": platform_type,
                    "status": str(status_value or "unknown"),
                }
            )
        return {"platforms": platforms_payload}

    async def _platform_manager_get_by_id(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(
            request_id,
            "platform.manager.get_by_id",
        )
        platform = self._get_platform_inst_by_id(str(payload.get("platform_id", "")))
        return {"platform": self._serialize_platform_snapshot(platform)}

    async def _platform_manager_clear_errors(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(
            request_id,
            "platform.manager.clear_errors",
        )
        platform = self._get_platform_inst_by_id(str(payload.get("platform_id", "")))
        if platform is None:
            raise AstrBotError.invalid_input("Unknown platform_id")
        clear_errors = getattr(platform, "clear_errors", None)
        if callable(clear_errors):
            clear_errors()
        return {}

    async def _platform_manager_get_stats(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._require_reserved_plugin(
            request_id,
            "platform.manager.get_stats",
        )
        platform = self._get_platform_inst_by_id(str(payload.get("platform_id", "")))
        if platform is None:
            return {"stats": None}
        get_stats = getattr(platform, "get_stats", None)
        if not callable(get_stats):
            return {"stats": None}
        return {"stats": self._serialize_platform_stats(get_stats())}

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

    @staticmethod
    def _provider_to_payload(provider: Any | None) -> dict[str, Any] | None:
        if provider is None:
            return None
        meta = provider.meta()
        return CoreCapabilityBridge._provider_meta_to_payload(meta)

    @staticmethod
    def _normalize_sdk_provider_type(value: Any) -> SDKProviderType:
        if isinstance(value, SDKProviderType):
            return value
        raw_provider_type = getattr(
            value,
            "provider_type",
            value,
        )
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

    @staticmethod
    def _serialize_platform_error(error: Any) -> dict[str, Any] | None:
        if error is None:
            return None
        message = getattr(error, "message", None)
        timestamp = getattr(error, "timestamp", None)
        traceback_value = getattr(error, "traceback", None)
        if isinstance(error, dict):
            message = error.get("message", message)
            timestamp = error.get("timestamp", timestamp)
            traceback_value = error.get("traceback", traceback_value)
        if not message:
            return None
        return {
            "message": str(message),
            "timestamp": CoreCapabilityBridge._to_iso_datetime(timestamp)
            or str(timestamp or ""),
            "traceback": (
                str(traceback_value) if traceback_value is not None else None
            ),
        }

    @classmethod
    def _serialize_platform_snapshot(cls, platform: Any) -> dict[str, Any] | None:
        if platform is None:
            return None
        meta = None
        try:
            meta = platform.meta()
        except Exception:
            meta = None
        platform_id = str(
            getattr(meta, "id", None) or getattr(platform, "config", {}).get("id", "")
        ).strip()
        platform_type = str(getattr(meta, "name", "") or "").strip()
        if not platform_id or not platform_type:
            return None
        status = getattr(platform, "status", None)
        errors = getattr(platform, "errors", [])
        status_value = getattr(status, "value", status)
        return {
            "id": platform_id,
            "name": str(getattr(meta, "adapter_display_name", None) or platform_type),
            "type": platform_type,
            "status": str(status_value or "pending"),
            "errors": [
                payload
                for payload in (
                    cls._serialize_platform_error(item)
                    for item in (errors if isinstance(errors, list) else [])
                )
                if payload is not None
            ],
            "last_error": cls._serialize_platform_error(
                getattr(platform, "last_error", None)
            ),
            "unified_webhook": bool(
                platform.unified_webhook()
                if hasattr(platform, "unified_webhook")
                else False
            ),
        }

    @classmethod
    def _serialize_platform_stats(cls, stats: Any) -> dict[str, Any] | None:
        if not isinstance(stats, dict):
            return None
        payload = dict(stats)
        payload["last_error"] = cls._serialize_platform_error(stats.get("last_error"))
        meta = stats.get("meta")
        payload["meta"] = dict(meta) if isinstance(meta, dict) else {}
        return payload

    def _get_platform_inst_by_id(self, platform_id: str) -> Any | None:
        platform_manager = getattr(self._star_context, "platform_manager", None)
        if platform_manager is None or not hasattr(platform_manager, "get_insts"):
            return None
        normalized_platform_id = str(platform_id).strip()
        if not normalized_platform_id:
            return None
        for platform in list(platform_manager.get_insts()):
            meta = None
            try:
                meta = platform.meta()
            except Exception:
                continue
            if str(getattr(meta, "id", "")).strip() == normalized_platform_id:
                return platform
        return None

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
            for item in self._plugin_bridge.get_active_llm_tools(plugin_id)
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
            event_payload = EventConverter.core_to_sdk(
                event,
                dispatch_token=dispatch_token,
                plugin_id=plugin_id,
                request_id=request_id,
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
                if tool_spec.handler_capability:
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

    def _resolve_plugin_id(self, request_id: str) -> str:
        plugin_id = current_caller_plugin_id()
        if plugin_id:
            return plugin_id
        return self._plugin_bridge.resolve_request_plugin_id(request_id)

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

    def _register_system_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("system.get_data_dir", "Get plugin data dir"),
            call_handler=self._system_get_data_dir,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.text_to_image", "Render text to image"),
            call_handler=self._system_text_to_image,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.html_render", "Render html template"),
            call_handler=self._system_html_render,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.file.register", "Register file token"),
            call_handler=self._system_file_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.file.handle", "Resolve file token"),
            call_handler=self._system_file_handle,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.register",
                "Register sdk session waiter",
            ),
            call_handler=self._system_session_waiter_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.session_waiter.unregister",
                "Unregister sdk session waiter",
            ),
            call_handler=self._system_session_waiter_unregister,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.event.react", "Send sdk event reaction"),
            call_handler=self._system_event_react,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_typing",
                "Send sdk event typing state",
            ),
            call_handler=self._system_event_send_typing,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming",
                "Send sdk event streaming chunks",
            ),
            call_handler=self._system_event_send_streaming,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_chunk",
                "Push sdk event streaming chunk",
            ),
            call_handler=self._system_event_send_streaming_chunk,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.send_streaming_close",
                "Close sdk event streaming session",
            ),
            call_handler=self._system_event_send_streaming_close,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.llm.get_state",
                "Read sdk request llm state",
            ),
            call_handler=self._system_event_llm_get_state,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.llm.request",
                "Request default llm for current sdk request",
            ),
            call_handler=self._system_event_llm_request,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.result.get",
                "Read sdk request result",
            ),
            call_handler=self._system_event_result_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.result.set",
                "Write sdk request result",
            ),
            call_handler=self._system_event_result_set,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.result.clear",
                "Clear sdk request result",
            ),
            call_handler=self._system_event_result_clear,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.get",
                "Read sdk request handler whitelist",
            ),
            call_handler=self._system_event_handler_whitelist_get,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "system.event.handler_whitelist.set",
                "Write sdk request handler whitelist",
            ),
            call_handler=self._system_event_handler_whitelist_set,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor(
                "registry.get_handlers_by_event_type",
                "List SDK handlers by event type",
            ),
            call_handler=self._registry_get_handlers_by_event_type,
        )
        self.register(
            self._builtin_descriptor(
                "registry.get_handler_by_full_name",
                "Get SDK handler metadata by full name",
            ),
            call_handler=self._registry_get_handler_by_full_name,
        )
        self.register(
            self._builtin_descriptor(
                "registry.command.register",
                "Register dynamic command route",
            ),
            call_handler=self._registry_command_register,
        )

    def _register_p0_5_capabilities(self) -> None:
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

    def _register_p0_6_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor(
                "session.plugin.is_enabled",
                "Get session plugin enabled state",
            ),
            call_handler=self._session_plugin_is_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.plugin.filter_handlers",
                "Filter handler metadata by session plugin config",
            ),
            call_handler=self._session_plugin_filter_handlers,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_llm_enabled",
                "Get session LLM enabled state",
            ),
            call_handler=self._session_service_is_llm_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_llm_status",
                "Set session LLM enabled state",
            ),
            call_handler=self._session_service_set_llm_status,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.is_tts_enabled",
                "Get session TTS enabled state",
            ),
            call_handler=self._session_service_is_tts_enabled,
        )
        self.register(
            self._builtin_descriptor(
                "session.service.set_tts_status",
                "Set session TTS enabled state",
            ),
            call_handler=self._session_service_set_tts_status,
        )

    def _register_p1_2_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("persona.get", "Get persona"),
            call_handler=self._persona_get,
        )
        self.register(
            self._builtin_descriptor("persona.list", "List personas"),
            call_handler=self._persona_list,
        )
        self.register(
            self._builtin_descriptor("persona.create", "Create persona"),
            call_handler=self._persona_create,
        )
        self.register(
            self._builtin_descriptor("persona.update", "Update persona"),
            call_handler=self._persona_update,
        )
        self.register(
            self._builtin_descriptor("persona.delete", "Delete persona"),
            call_handler=self._persona_delete,
        )
        self.register(
            self._builtin_descriptor("conversation.new", "Create conversation"),
            call_handler=self._conversation_new,
        )
        self.register(
            self._builtin_descriptor("conversation.switch", "Switch conversation"),
            call_handler=self._conversation_switch,
        )
        self.register(
            self._builtin_descriptor("conversation.delete", "Delete conversation"),
            call_handler=self._conversation_delete,
        )
        self.register(
            self._builtin_descriptor("conversation.get", "Get conversation"),
            call_handler=self._conversation_get,
        )
        self.register(
            self._builtin_descriptor("conversation.list", "List conversations"),
            call_handler=self._conversation_list,
        )
        self.register(
            self._builtin_descriptor("conversation.update", "Update conversation"),
            call_handler=self._conversation_update,
        )
        self.register(
            self._builtin_descriptor("kb.get", "Get knowledge base"),
            call_handler=self._kb_get,
        )
        self.register(
            self._builtin_descriptor("kb.create", "Create knowledge base"),
            call_handler=self._kb_create,
        )
        self.register(
            self._builtin_descriptor("kb.delete", "Delete knowledge base"),
            call_handler=self._kb_delete,
        )

    def _register_p1_3_capabilities(self) -> None:
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
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_by_id",
                "Get platform management snapshot by id",
            ),
            call_handler=self._platform_manager_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.clear_errors",
                "Clear platform error records",
            ),
            call_handler=self._platform_manager_clear_errors,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_stats",
                "Get platform stats by id",
            ),
            call_handler=self._platform_manager_get_stats,
        )

    @staticmethod
    def _normalize_session_scoped_config(
        raw_config: Any,
        session_id: str,
    ) -> dict[str, Any]:
        if not isinstance(raw_config, dict):
            return {}
        nested = raw_config.get(session_id)
        if isinstance(nested, dict):
            return dict(nested)
        return dict(raw_config)

    @staticmethod
    def _serialize_member(member: Any) -> dict[str, Any] | None:
        if member is None:
            return None
        user_id = getattr(member, "user_id", None)
        if user_id is None and isinstance(member, dict):
            user_id = member.get("user_id")
        if user_id is None:
            return None
        nickname = getattr(member, "nickname", None)
        if nickname is None and isinstance(member, dict):
            nickname = member.get("nickname")
        role = getattr(member, "role", None)
        if role is None and isinstance(member, dict):
            role = member.get("role")
        return {
            "user_id": str(user_id),
            "nickname": str(nickname or ""),
            "role": str(role or ""),
        }

    @classmethod
    def _serialize_group(cls, group: Any) -> dict[str, Any] | None:
        if group is None:
            return None
        members_payload = []
        raw_members = getattr(group, "members", None)
        if raw_members is None:
            raw_members = getattr(group, "member_list", None)
        if raw_members is None and isinstance(group, dict):
            raw_members = group.get("members") or group.get("member_list")
        if isinstance(raw_members, list):
            for member in raw_members:
                serialized_member = cls._serialize_member(member)
                if serialized_member is not None:
                    members_payload.append(serialized_member)
        group_id = getattr(group, "group_id", None)
        if group_id is None and isinstance(group, dict):
            group_id = group.get("group_id")
        group_name = getattr(group, "group_name", None)
        if group_name is None and isinstance(group, dict):
            group_name = group.get("group_name")
        group_avatar = getattr(group, "group_avatar", None)
        if group_avatar is None and isinstance(group, dict):
            group_avatar = group.get("group_avatar")
        group_owner = getattr(group, "group_owner", None)
        if group_owner is None and isinstance(group, dict):
            group_owner = group.get("group_owner")
        group_admins = getattr(group, "group_admins", None)
        if group_admins is None and isinstance(group, dict):
            group_admins = group.get("group_admins")
        return {
            "group_id": str(group_id or ""),
            "group_name": str(group_name or ""),
            "group_avatar": str(group_avatar or ""),
            "group_owner": str(group_owner or ""),
            "group_admins": (
                [str(item) for item in group_admins]
                if isinstance(group_admins, list)
                else []
            ),
            "members": members_payload,
        }

    def _resolve_current_group_request_context(
        self,
        request_id: str,
        payload: dict[str, Any],
    ):
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None:
            return None
        payload_session = str(payload.get("session", "")).strip()
        if payload_session and payload_session != str(
            request_context.event.unified_msg_origin
        ):
            raise AstrBotError.invalid_input(
                "platform.get_group/get_members only support the current event session"
            )
        return request_context

    async def _load_session_plugin_config(self, session_id: str) -> dict[str, Any]:
        raw_config = await _get_runtime_sp().get_async(
            scope="umo",
            scope_id=session_id,
            key="session_plugin_config",
            default={},
        )
        return self._normalize_session_scoped_config(raw_config, session_id)

    async def _load_session_service_config(self, session_id: str) -> dict[str, Any]:
        raw_config = await _get_runtime_sp().get_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            default={},
        )
        return self._normalize_session_scoped_config(raw_config, session_id)

    def _reserved_plugin_names(self) -> set[str]:
        reserved: set[str] = set()
        get_all_stars = getattr(self._star_context, "get_all_stars", None)
        if not callable(get_all_stars):
            return reserved
        stars = get_all_stars()
        if not isinstance(stars, Iterable):
            return reserved
        for star in stars:
            name = getattr(star, "name", None)
            if name and bool(getattr(star, "reserved", False)):
                reserved.add(str(name))
        return reserved

    def _require_reserved_plugin(
        self,
        request_id: str,
        capability_name: str,
    ) -> str:
        plugin_id = self._resolve_plugin_id(request_id)
        if plugin_id in {"system", "__system__"}:
            return plugin_id
        if plugin_id in self._reserved_plugin_names():
            return plugin_id
        raise AstrBotError.invalid_input(
            f"{capability_name} is restricted to reserved/system plugins"
        )

    async def _session_plugin_is_enabled(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        plugin_name = str(payload.get("plugin_name", "")).strip()
        config = await self._load_session_plugin_config(session_id)
        enabled_plugins = {
            str(item) for item in config.get("enabled_plugins", []) if str(item).strip()
        }
        disabled_plugins = {
            str(item)
            for item in config.get("disabled_plugins", [])
            if str(item).strip()
        }
        if (
            plugin_name in disabled_plugins
            and plugin_name not in self._reserved_plugin_names()
        ):
            return {"enabled": False}
        if plugin_name in enabled_plugins:
            return {"enabled": True}
        return {"enabled": True}

    async def _session_plugin_filter_handlers(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        handlers = payload.get("handlers")
        if not isinstance(handlers, list):
            raise AstrBotError.invalid_input(
                "session.plugin.filter_handlers requires a handlers array"
            )
        config = await self._load_session_plugin_config(session_id)
        disabled_plugins = {
            str(item)
            for item in config.get("disabled_plugins", [])
            if str(item).strip()
        }
        reserved_plugins = self._reserved_plugin_names()
        filtered = []
        for item in handlers:
            if not isinstance(item, dict):
                continue
            plugin_name = str(item.get("plugin_name", "")).strip()
            if (
                plugin_name
                and plugin_name in disabled_plugins
                and plugin_name not in reserved_plugins
            ):
                continue
            filtered.append(dict(item))
        return {"handlers": filtered}

    async def _session_service_is_llm_enabled(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        return {"enabled": bool(config.get("llm_enabled", True))}

    async def _session_service_set_llm_status(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        config["llm_enabled"] = bool(payload.get("enabled", False))
        await _get_runtime_sp().put_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            value=config,
        )
        return {}

    async def _session_service_is_tts_enabled(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        return {"enabled": bool(config.get("tts_enabled", True))}

    async def _session_service_set_tts_status(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session_id = str(payload.get("session", "")).strip()
        config = await self._load_session_service_config(session_id)
        config["tts_enabled"] = bool(payload.get("enabled", False))
        await _get_runtime_sp().put_async(
            scope="umo",
            scope_id=session_id,
            key="session_service_config",
            value=config,
        )
        return {}

    async def _persona_get(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        try:
            persona = await self._star_context.persona_manager.get_persona(persona_id)
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"persona": self._serialize_persona(persona)}

    async def _persona_list(
        self,
        _request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        personas = await self._star_context.persona_manager.get_all_personas()
        return {
            "personas": [
                payload
                for payload in (
                    self._serialize_persona(persona) for persona in personas
                )
                if payload is not None
            ]
        }

    async def _persona_create(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.create requires persona object")
        try:
            persona = await self._star_context.persona_manager.create_persona(
                persona_id=str(raw_persona.get("persona_id", "")),
                system_prompt=str(raw_persona.get("system_prompt", "")),
                begin_dialogs=self._normalize_persona_dialogs(
                    raw_persona.get("begin_dialogs")
                ),
                tools=(
                    [str(item) for item in raw_persona.get("tools", [])]
                    if isinstance(raw_persona.get("tools"), list)
                    else None
                ),
                skills=(
                    [str(item) for item in raw_persona.get("skills", [])]
                    if isinstance(raw_persona.get("skills"), list)
                    else None
                ),
                custom_error_message=(
                    str(raw_persona.get("custom_error_message"))
                    if raw_persona.get("custom_error_message") is not None
                    else None
                ),
                folder_id=(
                    str(raw_persona.get("folder_id"))
                    if raw_persona.get("folder_id") is not None
                    else None
                ),
                sort_order=int(raw_persona.get("sort_order", 0)),
            )
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"persona": self._serialize_persona(persona)}

    async def _persona_update(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.update requires persona object")
        persona = await self._star_context.persona_manager.update_persona(
            persona_id=str(payload.get("persona_id", "")),
            system_prompt=raw_persona.get("system_prompt"),
            begin_dialogs=(
                self._normalize_persona_dialogs(raw_persona.get("begin_dialogs"))
                if "begin_dialogs" in raw_persona
                else None
            ),
            tools=(
                [str(item) for item in raw_persona.get("tools", [])]
                if isinstance(raw_persona.get("tools"), list)
                else raw_persona.get("tools")
            ),
            skills=(
                [str(item) for item in raw_persona.get("skills", [])]
                if isinstance(raw_persona.get("skills"), list)
                else raw_persona.get("skills")
            ),
            custom_error_message=raw_persona.get("custom_error_message"),
        )
        return {"persona": self._serialize_persona(persona)}

    async def _persona_delete(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        try:
            await self._star_context.persona_manager.delete_persona(persona_id)
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {}

    async def _conversation_new(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        if not session:
            raise AstrBotError.invalid_input("conversation.new requires session")
        raw_conversation = payload.get("conversation")
        if raw_conversation is None:
            raw_conversation = {}
        if not isinstance(raw_conversation, dict):
            raise AstrBotError.invalid_input(
                "conversation.new requires conversation object"
            )
        conversation_id = (
            await self._star_context.conversation_manager.new_conversation(
                unified_msg_origin=session,
                platform_id=(
                    str(raw_conversation.get("platform_id"))
                    if raw_conversation.get("platform_id") is not None
                    else None
                ),
                content=self._normalize_history_items(raw_conversation.get("history")),
                title=(
                    str(raw_conversation.get("title"))
                    if raw_conversation.get("title") is not None
                    else None
                ),
                persona_id=(
                    str(raw_conversation.get("persona_id"))
                    if raw_conversation.get("persona_id") is not None
                    else None
                ),
            )
        )
        return {"conversation_id": conversation_id}

    async def _conversation_switch(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = str(payload.get("conversation_id", "")).strip()
        if not session:
            raise AstrBotError.invalid_input("conversation.switch requires session")
        if not conversation_id:
            raise AstrBotError.invalid_input(
                "conversation.switch requires conversation_id"
            )
        await self._star_context.conversation_manager.switch_conversation(
            unified_msg_origin=session,
            conversation_id=conversation_id,
        )
        return {}

    async def _conversation_delete(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        await self._star_context.conversation_manager.delete_conversation(
            unified_msg_origin=str(payload.get("session", "")),
            conversation_id=(
                str(payload.get("conversation_id"))
                if payload.get("conversation_id") is not None
                else None
            ),
        )
        return {}

    async def _conversation_get(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        conversation = await self._star_context.conversation_manager.get_conversation(
            unified_msg_origin=str(payload.get("session", "")),
            conversation_id=str(payload.get("conversation_id", "")),
            create_if_not_exists=bool(payload.get("create_if_not_exists", False)),
        )
        return {"conversation": self._serialize_conversation(conversation)}

    async def _conversation_list(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        session = payload.get("session")
        platform_id = payload.get("platform_id")
        conversations = await self._star_context.conversation_manager.get_conversations(
            unified_msg_origin=(
                str(session) if session is not None and str(session).strip() else None
            ),
            platform_id=(
                str(platform_id)
                if platform_id is not None and str(platform_id).strip()
                else None
            ),
        )
        return {
            "conversations": [
                payload
                for payload in (
                    self._serialize_conversation(conversation)
                    for conversation in conversations
                )
                if payload is not None
            ]
        }

    async def _conversation_update(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        raw_conversation = payload.get("conversation")
        if raw_conversation is None:
            raw_conversation = {}
        if not isinstance(raw_conversation, dict):
            raise AstrBotError.invalid_input(
                "conversation.update requires conversation object"
            )
        await self._star_context.conversation_manager.update_conversation(
            unified_msg_origin=str(payload.get("session", "")),
            conversation_id=(
                str(payload.get("conversation_id"))
                if payload.get("conversation_id") is not None
                else None
            ),
            history=(
                self._normalize_history_items(raw_conversation.get("history"))
                if "history" in raw_conversation
                else None
            ),
            title=(
                str(raw_conversation.get("title"))
                if raw_conversation.get("title") is not None
                else None
            ),
            persona_id=(
                str(raw_conversation.get("persona_id"))
                if raw_conversation.get("persona_id") is not None
                else None
            ),
            token_usage=(self._optional_int(raw_conversation.get("token_usage"))),
        )
        return {}

    async def _kb_get(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        kb_helper = self._star_context.kb_manager.get_kb(str(payload.get("kb_id", "")))
        return {"kb": self._serialize_kb(kb_helper)}

    async def _kb_create(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        raw_kb = payload.get("kb")
        if not isinstance(raw_kb, dict):
            raise AstrBotError.invalid_input("kb.create requires kb object")
        try:
            kb_helper = self._star_context.kb_manager.create_kb(
                kb_name=str(raw_kb.get("kb_name", "")),
                description=(
                    str(raw_kb.get("description"))
                    if raw_kb.get("description") is not None
                    else None
                ),
                emoji=(
                    str(raw_kb.get("emoji"))
                    if raw_kb.get("emoji") is not None
                    else None
                ),
                embedding_provider_id=(
                    str(raw_kb.get("embedding_provider_id"))
                    if raw_kb.get("embedding_provider_id") is not None
                    else None
                ),
                rerank_provider_id=(
                    str(raw_kb.get("rerank_provider_id"))
                    if raw_kb.get("rerank_provider_id") is not None
                    else None
                ),
                chunk_size=self._optional_int(raw_kb.get("chunk_size")),
                chunk_overlap=self._optional_int(raw_kb.get("chunk_overlap")),
                top_k_dense=self._optional_int(raw_kb.get("top_k_dense")),
                top_k_sparse=self._optional_int(raw_kb.get("top_k_sparse")),
                top_m_final=self._optional_int(raw_kb.get("top_m_final")),
            )
        except ValueError as exc:
            raise AstrBotError.invalid_input(str(exc)) from exc
        return {"kb": self._serialize_kb(kb_helper)}

    async def _kb_delete(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        deleted = self._star_context.kb_manager.delete_kb(str(payload.get("kb_id", "")))
        return {"deleted": bool(deleted)}

    async def _system_get_data_dir(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        data_dir = Path(get_astrbot_data_path()) / "plugin_data" / plugin_id
        data_dir.mkdir(parents=True, exist_ok=True)
        return {"path": str(data_dir.resolve())}

    async def _system_text_to_image(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        config_obj = self._star_context.get_config()
        template_name = None
        if hasattr(config_obj, "get"):
            try:
                template_name = config_obj.get("t2i_active_template")
            except Exception:
                template_name = None
        result = await _get_runtime_html_renderer().render_t2i(
            str(payload.get("text", "")),
            return_url=bool(payload.get("return_url", True)),
            template_name=template_name,
        )
        return {"result": result}

    async def _system_html_render(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        data = payload.get("data")
        if not isinstance(data, dict):
            raise AstrBotError.invalid_input("system.html_render requires object data")
        options = payload.get("options")
        if options is not None and not isinstance(options, dict):
            raise AstrBotError.invalid_input(
                "system.html_render options must be an object or null"
            )
        result = await _get_runtime_html_renderer().render_custom_template(
            str(payload.get("tmpl", "")),
            data,
            return_url=bool(payload.get("return_url", True)),
            options=options,
        )
        return {"result": result}

    async def _system_file_register(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        path = str(payload.get("path", "")).strip()
        if not path:
            raise AstrBotError.invalid_input("system.file.register requires path")
        raw_timeout = payload.get("timeout")
        timeout: float | None
        if raw_timeout is None:
            timeout = None
        else:
            try:
                timeout = float(raw_timeout)
            except (TypeError, ValueError) as exc:
                raise AstrBotError.invalid_input(
                    "system.file.register timeout must be a number or null"
                ) from exc
        file_token = await _get_runtime_file_token_service().register_file(
            path, timeout
        )
        callback_host = _get_runtime_astrbot_config().get("callback_api_base")
        if not callback_host:
            raise AstrBotError.invalid_input(
                "callback_api_base is required for system.file.register"
            )
        base_url = str(callback_host).rstrip("/")
        return {"token": file_token, "url": f"{base_url}/api/file/{file_token}"}

    async def _system_file_handle(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        file_token = str(payload.get("token", "")).strip()
        if not file_token:
            raise AstrBotError.invalid_input("system.file.handle requires token")
        path = await _get_runtime_file_token_service().handle_file(file_token)
        return {"path": str(path)}

    async def _system_session_waiter_register(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        self._plugin_bridge.register_session_waiter(
            plugin_id=plugin_id,
            session_key=str(payload.get("session_key", "")),
        )
        return {}

    async def _system_session_waiter_unregister(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_id = self._resolve_plugin_id(request_id)
        self._plugin_bridge.unregister_session_waiter(
            plugin_id=plugin_id,
            session_key=str(payload.get("session_key", "")),
        )
        return {}

    async def _system_event_react(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None or request_context.cancelled:
            return {"supported": False}
        self._plugin_bridge.before_platform_send(request_context.dispatch_token)
        await request_context.event.react(str(payload.get("emoji", "")))
        return {
            "supported": bool(
                self._plugin_bridge.mark_platform_send(request_context.dispatch_token)
            )
        }

    async def _system_event_send_typing(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None or request_context.cancelled:
            return {"supported": False}
        if type(request_context.event).send_typing is AstrMessageEvent.send_typing:
            return {"supported": False}
        await request_context.event.send_typing()
        return {"supported": True}

    async def _system_event_send_streaming(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        request_context = self._resolve_event_request_context(request_id, payload)
        if request_context is None or request_context.cancelled:
            return {"supported": False}
        if (
            type(request_context.event).send_streaming
            is AstrMessageEvent.send_streaming
        ):
            return {"supported": False}
        self._plugin_bridge.before_platform_send(request_context.dispatch_token)
        queue: asyncio.Queue[MessageChain | None] = asyncio.Queue()

        async def iterator() -> AsyncIterator[MessageChain]:
            while True:
                chunk = await queue.get()
                if chunk is None or request_context.cancelled:
                    return
                yield chunk
                await asyncio.sleep(0)

        stream_id = uuid.uuid4().hex
        task = asyncio.create_task(
            request_context.event.send_streaming(
                iterator(),
                use_fallback=bool(payload.get("use_fallback", False)),
            )
        )
        self._event_streams[stream_id] = _EventStreamState(
            request_context=request_context,
            queue=queue,
            task=task,
        )
        return {"supported": True, "stream_id": stream_id}

    async def _system_event_send_streaming_chunk(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        stream_state = self._event_streams.get(str(payload.get("stream_id", "")))
        if stream_state is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        if stream_state.request_context.cancelled:
            raise AstrBotError.cancelled("The SDK request has been cancelled")
        chain_payload = payload.get("chain")
        if not isinstance(chain_payload, list):
            raise AstrBotError.invalid_input(
                "system.event.send_streaming_chunk requires a chain array"
            )
        await stream_state.queue.put(self._build_core_message_chain(chain_payload))
        return {}

    async def _system_event_send_streaming_close(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        stream_id = str(payload.get("stream_id", ""))
        stream_state = self._event_streams.pop(stream_id, None)
        if stream_state is None:
            raise AstrBotError.invalid_input("Unknown sdk event streaming session")
        await stream_state.queue.put(None)
        try:
            await stream_state.task
        finally:
            self._event_streams.pop(stream_id, None)
        return {
            "supported": bool(
                self._plugin_bridge.mark_platform_send(
                    stream_state.request_context.dispatch_token
                )
            )
        }

    async def _system_event_llm_get_state(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        overlay = self._plugin_bridge.get_request_overlay_by_request_id(request_id)
        should_call_llm = self._plugin_bridge.get_should_call_llm_for_request(
            request_id
        )
        return {
            "should_call_llm": bool(should_call_llm),
            "requested_llm": bool(overlay.requested_llm)
            if overlay is not None
            else False,
        }

    async def _system_event_llm_request(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._plugin_bridge.request_llm_for_request(request_id)
        return await self._system_event_llm_get_state(request_id, {}, _token)

    async def _system_event_result_get(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        return {
            "result": self._plugin_bridge.get_result_payload_for_request(request_id)
        }

    async def _system_event_result_set(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        result_payload = payload.get("result")
        if not isinstance(result_payload, dict):
            raise AstrBotError.invalid_input(
                "system.event.result.set requires an object result payload"
            )
        if not self._plugin_bridge.set_result_for_request(request_id, result_payload):
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        return {
            "result": self._plugin_bridge.get_result_payload_for_request(request_id)
        }

    async def _system_event_result_clear(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        self._plugin_bridge.clear_result_for_request(request_id)
        return {}

    async def _system_event_handler_whitelist_get(
        self,
        request_id: str,
        _payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_names = self._plugin_bridge.get_handler_whitelist_for_request(request_id)
        if plugin_names is None:
            return {"plugin_names": None}
        return {"plugin_names": sorted(plugin_names)}

    async def _system_event_handler_whitelist_set(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        plugin_names_payload = payload.get("plugin_names")
        plugin_names: set[str] | None
        if plugin_names_payload is None:
            plugin_names = None
        elif isinstance(plugin_names_payload, list):
            plugin_names = {
                str(item) for item in plugin_names_payload if str(item).strip()
            }
        else:
            raise AstrBotError.invalid_input(
                "system.event.handler_whitelist.set requires a string array or null"
            )
        if not self._plugin_bridge.set_handler_whitelist_for_request(
            request_id, plugin_names
        ):
            raise AstrBotError.cancelled("The SDK request overlay has been closed")
        return await self._system_event_handler_whitelist_get(request_id, {}, _token)

    async def _registry_get_handlers_by_event_type(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        event_type = str(payload.get("event_type", "")).strip()
        return {"handlers": self._plugin_bridge.get_handlers_by_event_type(event_type)}

    async def _registry_get_handler_by_full_name(
        self,
        _request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        full_name = str(payload.get("full_name", "")).strip()
        return {"handler": self._plugin_bridge.get_handler_by_full_name(full_name)}

    async def _registry_command_register(
        self,
        request_id: str,
        payload: dict[str, Any],
        _token,
    ) -> dict[str, Any]:
        source_event_type = str(payload.get("source_event_type", "")).strip()
        if source_event_type not in {"astrbot_loaded", "platform_loaded"}:
            raise AstrBotError.invalid_input(
                "register_commands is only available in astrbot_loaded/platform_loaded events"
            )
        if bool(payload.get("ignore_prefix", False)):
            raise AstrBotError.invalid_input(
                "register_commands(ignore_prefix=True) is unsupported in SDK runtime"
            )
        priority_value = payload.get("priority", 0)
        if isinstance(priority_value, bool) or not isinstance(priority_value, int):
            raise AstrBotError.invalid_input(
                "registry.command.register priority must be an integer"
            )
        plugin_id = self._resolve_plugin_id(request_id)
        self._plugin_bridge.register_dynamic_command_route(
            plugin_id=plugin_id,
            command_name=str(payload.get("command_name", "")),
            handler_full_name=str(payload.get("handler_full_name", "")),
            desc=str(payload.get("desc", "")),
            priority=priority_value,
            use_regex=bool(payload.get("use_regex", False)),
        )
        return {}

    def _resolve_dispatch_target(
        self,
        request_id: str,
        payload: dict[str, Any],
    ) -> tuple[str, str]:
        target_payload = payload.get("target")
        dispatch_token = ""
        if isinstance(target_payload, dict):
            raw_payload = target_payload.get("raw")
            if isinstance(raw_payload, dict):
                dispatch_token = str(raw_payload.get("dispatch_token", ""))
                if not dispatch_token:
                    nested_raw_payload = raw_payload.get("raw")
                    if isinstance(nested_raw_payload, dict):
                        dispatch_token = str(
                            nested_raw_payload.get("dispatch_token", "")
                        )
        if not dispatch_token:
            request_context = self._plugin_bridge.resolve_request_session(request_id)
            if request_context is None:
                raise AstrBotError.invalid_input(
                    "Missing dispatch token for platform send"
                )
            dispatch_token = request_context.dispatch_token
        session = str(payload.get("session", ""))
        return session, dispatch_token

    def _resolve_event_request_context(
        self,
        request_id: str,
        payload: dict[str, Any],
    ):
        target_payload = payload.get("target")
        dispatch_token = ""
        if isinstance(target_payload, dict):
            raw_payload = target_payload.get("raw")
            if isinstance(raw_payload, dict):
                dispatch_token = str(raw_payload.get("dispatch_token", ""))
                if not dispatch_token:
                    nested_raw = raw_payload.get("raw")
                    if isinstance(nested_raw, dict):
                        dispatch_token = str(nested_raw.get("dispatch_token", ""))
        if dispatch_token:
            return self._plugin_bridge.get_request_context_by_token(dispatch_token)
        return self._plugin_bridge.resolve_request_session(request_id)

    @staticmethod
    def _build_core_message_chain(chain_payload: list[dict[str, Any]]) -> MessageChain:
        components = []
        for item in chain_payload:
            if not isinstance(item, dict):
                continue
            comp_type = str(item.get("type", "")).lower()
            data = item.get("data", {})
            if comp_type in {"text", "plain"} and isinstance(data, dict):
                components.append(Plain(str(data.get("text", "")), convert=False))
                continue
            if comp_type == "image" and isinstance(data, dict):
                file_value = str(data.get("file") or data.get("url") or "")
                if file_value.startswith(("http://", "https://")):
                    components.append(Image.fromURL(file_value))
                elif file_value:
                    file_path = (
                        file_value[8:]
                        if file_value.startswith("file:///")
                        else file_value
                    )
                    components.append(Image.fromFileSystem(file_path))
                continue
            component_cls = ComponentTypes.get(comp_type)
            if component_cls is None:
                components.append(
                    Plain(json.dumps(item, ensure_ascii=False), convert=False)
                )
                continue
            try:
                if isinstance(data, dict):
                    components.append(component_cls(**data))
                else:
                    components.append(Plain(str(item), convert=False))
            except Exception:
                components.append(
                    Plain(json.dumps(item, ensure_ascii=False), convert=False)
                )
        return MessageChain(components)
