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
import base64
import copy
import hashlib
import json
import math
import re
import uuid
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
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


_MOCK_EMBEDDING_DIM = 24


def _embedding_terms(text: str) -> list[str]:
    """为 mock embedding 构造稳定的分词结果。

    Args:
        text: 待向量化的原始文本。

    Returns:
        list[str]: 用于生成 mock 向量的词项列表。
    """
    normalized = re.sub(r"\s+", " ", str(text).strip().casefold())
    compact = normalized.replace(" ", "")
    if not normalized:
        return []

    terms = [word for word in re.findall(r"\w+", normalized, flags=re.UNICODE) if word]
    if compact:
        if len(compact) == 1:
            terms.append(compact)
        else:
            terms.extend(
                compact[index : index + 2] for index in range(len(compact) - 1)
            )
            terms.append(compact)
    return terms or [normalized]


def _mock_embedding_vector(text: str, *, provider_id: str) -> list[float]:
    """生成确定性的 mock embedding 向量。

    Args:
        text: 待向量化的文本。
        provider_id: 当前使用的 embedding provider 标识。

    Returns:
        list[float]: 归一化后的 mock 向量。
    """
    values = [0.0] * _MOCK_EMBEDDING_DIM
    for term in _embedding_terms(text):
        digest = hashlib.sha256(f"{provider_id}:{term}".encode("utf-8")).digest()
        index = int.from_bytes(digest[:2], "big") % _MOCK_EMBEDDING_DIM
        values[index] += 1.0 + min(len(term), 8) * 0.05
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return values
    return [value / norm for value in values]


class _CapabilityRouterHost:
    memory_store: dict[str, dict[str, Any]]
    _memory_index: dict[str, dict[str, Any]]
    _memory_dirty_keys: set[str]
    _memory_expires_at: dict[str, datetime | None]
    db_store: dict[str, Any]
    sent_messages: list[dict[str, Any]]
    event_actions: list[dict[str, Any]]
    http_api_store: list[dict[str, Any]]
    _event_streams: dict[str, dict[str, Any]]
    _plugins: dict[str, Any]
    _request_overlays: dict[str, dict[str, Any]]
    _provider_catalog: dict[str, list[dict[str, Any]]]
    _provider_configs: dict[str, dict[str, Any]]
    _active_provider_ids: dict[str, str | None]
    _provider_change_subscriptions: dict[str, asyncio.Queue[dict[str, Any]]]
    _system_data_root: Path
    _session_waiters: dict[str, set[str]]
    _session_plugin_configs: dict[str, dict[str, Any]]
    _session_service_configs: dict[str, dict[str, Any]]
    _db_watch_subscriptions: dict[str, tuple[str | None, asyncio.Queue[dict[str, Any]]]]
    _dynamic_command_routes: dict[str, list[dict[str, Any]]]
    _file_token_store: dict[str, str]
    _platform_instances: list[dict[str, Any]]
    _persona_store: dict[str, dict[str, Any]]
    _conversation_store: dict[str, dict[str, Any]]
    _session_current_conversation_ids: dict[str, str]
    _kb_store: dict[str, dict[str, Any]]

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

    def register_dynamic_command_route(
        self,
        *,
        plugin_id: str,
        command_name: str,
        handler_full_name: str,
        desc: str = "",
        priority: int = 0,
        use_regex: bool = False,
    ) -> None:
        raise NotImplementedError

    def get_platform_instances(self) -> list[dict[str, Any]]:
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
        self._register_p1_2_capabilities()
        self._register_p1_3_capabilities()
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

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _session_platform_id(session: str) -> str:
        parts = str(session).split(":", maxsplit=1)
        if parts and parts[0].strip():
            return parts[0].strip()
        return "unknown"

    @staticmethod
    def _normalize_history_payload(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        return [dict(item) for item in value if isinstance(item, dict)]

    @staticmethod
    def _normalize_persona_dialogs_payload(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if isinstance(item, str)]

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

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

    @staticmethod
    def _is_ttl_memory_entry(value: Any) -> bool:
        """判断存储值是否使用了 TTL 包装结构。

        Args:
            value: 待检查的存储值。

        Returns:
            bool: 如果值包含 ``value`` 和 ``ttl_seconds`` 字段则返回 ``True``。
        """
        return isinstance(value, dict) and "value" in value and "ttl_seconds" in value

    @classmethod
    def _memory_value_for_search(cls, stored: Any) -> dict[str, Any] | None:
        """提取用于检索的原始 memory payload。

        Args:
            stored: memory_store 中保存的原始值。

        Returns:
            dict[str, Any] | None: 解开 TTL 包装后的字典，无法解析时返回 ``None``。
        """
        if not isinstance(stored, dict):
            return None
        if cls._is_ttl_memory_entry(stored):
            value = stored.get("value")
            return value if isinstance(value, dict) else None
        return stored

    @classmethod
    def _extract_memory_text(cls, stored: Any) -> str:
        """提取用于检索索引的首选文本。

        Args:
            stored: memory_store 中保存的原始值。

        Returns:
            str: 优先使用 ``embedding_text`` / ``content`` 等字段，兜底为 JSON 文本。
        """
        value = cls._memory_value_for_search(stored)
        if not isinstance(value, dict):
            return ""
        for field_name in ("embedding_text", "content", "summary", "title", "text"):
            item = value.get(field_name)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    @staticmethod
    def _memory_expiration_from_ttl(ttl_seconds: Any) -> datetime | None:
        """将 TTL 秒数转换为 UTC 过期时间。

        Args:
            ttl_seconds: TTL 秒数。

        Returns:
            datetime | None: 绝对过期时间；当输入无效时返回 ``None``。
        """
        try:
            ttl = int(ttl_seconds)
        except (TypeError, ValueError):
            return None
        if ttl < 1:
            return None
        return datetime.now(timezone.utc) + timedelta(seconds=ttl)

    @staticmethod
    def _memory_keyword_score(query: str, key: str, text: str) -> float:
        """计算关键词匹配分数。

        Args:
            query: 查询文本。
            key: memory 条目的键。
            text: 已索引的检索文本。

        Returns:
            float: 基于键名和文本命中的粗粒度关键词分数。
        """
        normalized_query = str(query).casefold()
        if not normalized_query:
            return 1.0
        normalized_key = str(key).casefold()
        normalized_text = str(text).casefold()
        if normalized_query in normalized_key:
            return 1.0
        if normalized_query in normalized_text:
            return 0.9
        return 0.0

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        """计算两个向量之间的余弦相似度。

        Args:
            left: 左侧向量。
            right: 右侧向量。

        Returns:
            float: 余弦相似度；输入不合法时返回 ``0.0``。
        """
        if not left or not right or len(left) != len(right):
            return 0.0
        left_norm = math.sqrt(sum(value * value for value in left))
        right_norm = math.sqrt(sum(value * value for value in right))
        if left_norm <= 0 or right_norm <= 0:
            return 0.0
        return sum(a * b for a, b in zip(left, right, strict=False)) / (
            left_norm * right_norm
        )

    def _resolve_memory_embedding_provider_id(
        self,
        provider_id: Any,
        *,
        required: bool,
    ) -> str | None:
        """解析 memory.search 要使用的 embedding provider。

        Args:
            provider_id: 调用方显式传入的 provider 标识。
            required: 当前检索模式是否强制要求 embedding provider。

        Returns:
            str | None: 最终选中的 provider 标识；在非强制场景下允许返回 ``None``。
        """
        normalized = str(provider_id).strip() if provider_id is not None else ""
        if normalized:
            self._provider_entry(
                {"provider_id": normalized},
                "memory.search",
                "embedding",
            )
            return normalized
        active_id = self._active_provider_ids.get("embedding")
        if active_id is not None:
            normalized_active = str(active_id).strip()
            if normalized_active:
                self._provider_entry(
                    {"provider_id": normalized_active},
                    "memory.search",
                    "embedding",
                )
                return normalized_active
        if required:
            raise AstrBotError.invalid_input(
                "memory.search requires an embedding provider",
            )
        return None

    @staticmethod
    def _memory_index_entry(entry: Any, *, text: str) -> dict[str, Any]:
        """将原始索引项规范化为内部统一结构。

        Args:
            entry: 当前索引表中的原始项。
            text: 当前条目的索引文本。

        Returns:
            dict[str, Any]: 统一后的索引项，包含 ``text``、``embedding``、``provider_id``。
        """
        if isinstance(entry, dict):
            return {
                "text": str(entry.get("text", text)),
                "embedding": (
                    [float(item) for item in entry.get("embedding", [])]
                    if isinstance(entry.get("embedding"), list)
                    else None
                ),
                "provider_id": (
                    str(entry.get("provider_id")).strip()
                    if entry.get("provider_id") is not None
                    else None
                ),
            }
        return {"text": text, "embedding": None, "provider_id": None}

    def _clear_memory_sidecars(self, key: str) -> None:
        """清理指定 memory 键对应的所有 sidecar 状态。

        Args:
            key: memory 条目的键。

        Returns:
            None
        """
        self._memory_index.pop(key, None)
        self._memory_expires_at.pop(key, None)
        self._memory_dirty_keys.discard(key)

    def _delete_memory_entry(self, key: str) -> bool:
        """删除 memory 条目并同步清理 sidecar 状态。

        Args:
            key: memory 条目的键。

        Returns:
            bool: 条目存在并删除成功时返回 ``True``。
        """
        deleted = self.memory_store.pop(key, None) is not None
        self._clear_memory_sidecars(key)
        return deleted

    def _upsert_memory_sidecars(
        self,
        key: str,
        stored: dict[str, Any],
        *,
        expires_at: datetime | None = None,
    ) -> None:
        """创建或更新单条 memory 的 sidecar 索引状态。

        Args:
            key: memory 条目的键。
            stored: 需要建立索引的原始存储值。
            expires_at: 可选的绝对过期时间。

        Returns:
            None
        """
        self._memory_index[key] = {
            "text": self._extract_memory_text(stored),
            "embedding": None,
            "provider_id": None,
        }
        if expires_at is None:
            self._memory_expires_at.pop(key, None)
        else:
            self._memory_expires_at[key] = expires_at
        self._memory_dirty_keys.add(key)

    def _ensure_memory_sidecars(self, key: str, stored: Any) -> None:
        """确保 sidecar 状态与当前存储值保持一致。

        Args:
            key: memory 条目的键。
            stored: memory_store 中的当前存储值。

        Returns:
            None
        """
        if not isinstance(stored, dict):
            return
        text = self._extract_memory_text(stored)
        existed = key in self._memory_index
        entry = self._memory_index_entry(self._memory_index.get(key), text=text)
        if entry["text"] != text:
            entry["text"] = text
            entry["embedding"] = None
            entry["provider_id"] = None
            self._memory_dirty_keys.add(key)
        self._memory_index[key] = entry
        if not existed:
            self._memory_dirty_keys.add(key)

    def _is_memory_expired(self, key: str) -> bool:
        """判断 memory 条目是否已过期。

        Args:
            key: memory 条目的键。

        Returns:
            bool: 如果当前时间已超过记录的过期时间则返回 ``True``。
        """
        expires_at = self._memory_expires_at.get(key)
        return expires_at is not None and expires_at <= datetime.now(timezone.utc)

    def _purge_expired_memory_entry(self, key: str) -> bool:
        """在单条 memory 已过期时立即清理它。

        Args:
            key: memory 条目的键。

        Returns:
            bool: 如果条目已过期并被成功清理则返回 ``True``。
        """
        if not self._is_memory_expired(key):
            return False
        self._delete_memory_entry(key)
        return True

    def _purge_expired_memory_entries(self) -> None:
        """批量清理所有已跟踪的过期 TTL 条目。

        Returns:
            None
        """
        for key in list(self._memory_expires_at):
            self._purge_expired_memory_entry(key)

    async def _embedding_for_text(
        self,
        *,
        provider_id: str,
        text: str,
    ) -> list[float]:
        """通过 embedding capability 获取单条文本向量。

        Args:
            provider_id: 使用的 embedding provider 标识。
            text: 待向量化的文本。

        Returns:
            list[float]: provider 返回的向量；异常场景下返回空列表。
        """
        output = await self._provider_embedding_get_embedding(
            "",
            {"provider_id": provider_id, "text": text},
            None,
        )
        embedding = output.get("embedding")
        if not isinstance(embedding, list):
            return []
        return [float(item) for item in embedding]

    async def _embeddings_for_texts(
        self,
        *,
        provider_id: str,
        texts: list[str],
    ) -> list[list[float]]:
        """批量获取多条文本的 embedding 向量。

        Args:
            provider_id: 使用的 embedding provider 标识。
            texts: 待向量化的文本列表。

        Returns:
            list[list[float]]: 与输入顺序对应的向量列表。
        """
        if not texts:
            return []
        output = await self._provider_embedding_get_embeddings(
            "",
            {"provider_id": provider_id, "texts": texts},
            None,
        )
        embeddings = output.get("embeddings")
        if not isinstance(embeddings, list):
            return []
        return [
            [float(value) for value in item]
            for item in embeddings
            if isinstance(item, list)
        ]

    async def _refresh_memory_embeddings(self, *, provider_id: str) -> None:
        """刷新当前 provider 下脏或过期的 memory 向量索引。

        Args:
            provider_id: 当前使用的 embedding provider 标识。

        Returns:
            None
        """
        keys_to_refresh: list[str] = []
        texts_to_refresh: list[str] = []
        for key, stored in self.memory_store.items():
            self._ensure_memory_sidecars(key, stored)
            entry = self._memory_index_entry(
                self._memory_index.get(key),
                text=self._extract_memory_text(stored),
            )
            should_refresh = (
                key in self._memory_dirty_keys
                or entry["embedding"] is None
                or entry["provider_id"] != provider_id
            )
            self._memory_index[key] = entry
            if should_refresh:
                keys_to_refresh.append(key)
                texts_to_refresh.append(str(entry["text"]))
        embeddings = await self._embeddings_for_texts(
            provider_id=provider_id,
            texts=texts_to_refresh,
        )
        for index, key in enumerate(keys_to_refresh):
            entry = self._memory_index_entry(
                self._memory_index.get(key),
                text=str(texts_to_refresh[index]),
            )
            entry["embedding"] = embeddings[index] if index < len(embeddings) else []
            entry["provider_id"] = provider_id
            self._memory_index[key] = entry
            self._memory_dirty_keys.discard(key)

    async def _memory_search(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        query = str(payload.get("query", ""))
        mode = str(payload.get("mode", "auto")).strip().lower() or "auto"
        limit = self._optional_int(payload.get("limit"))
        min_score = (
            float(payload.get("min_score"))
            if payload.get("min_score") is not None
            else None
        )
        self._purge_expired_memory_entries()
        provider_id = self._resolve_memory_embedding_provider_id(
            payload.get("provider_id"),
            required=mode in {"vector", "hybrid"},
        )
        effective_mode = mode
        if effective_mode == "auto":
            effective_mode = "hybrid" if provider_id is not None else "keyword"
        query_embedding: list[float] | None = None
        if effective_mode in {"vector", "hybrid"}:
            if provider_id is None:
                raise AstrBotError.invalid_input(
                    "memory.search requires an embedding provider",
                )
            await self._refresh_memory_embeddings(provider_id=provider_id)
            query_embedding = await self._embedding_for_text(
                provider_id=provider_id,
                text=query,
            )

        items: list[dict[str, Any]] = []
        for key, value in self.memory_store.items():
            self._ensure_memory_sidecars(key, value)
            entry = self._memory_index_entry(
                self._memory_index.get(key),
                text=self._extract_memory_text(value),
            )
            text = str(entry.get("text", ""))
            keyword_score = self._memory_keyword_score(query, key, text)
            vector_score = 0.0
            if query_embedding is not None:
                embedding = entry.get("embedding")
                if isinstance(embedding, list):
                    vector_score = max(
                        0.0,
                        self._cosine_similarity(query_embedding, embedding),
                    )

            if effective_mode == "keyword":
                score = keyword_score
            elif effective_mode == "vector":
                score = vector_score
            else:
                score = vector_score
                if keyword_score > 0:
                    score = max(score, 0.4 + 0.6 * vector_score)
            if score <= 0:
                continue
            if min_score is not None and score < min_score:
                continue

            if effective_mode == "keyword" or (keyword_score > 0 and vector_score <= 0):
                match_type = "keyword"
            elif effective_mode == "vector" or keyword_score <= 0:
                match_type = "vector"
            else:
                match_type = "hybrid"

            items.append(
                {
                    "key": key,
                    "value": self._memory_value_for_search(value),
                    "score": score,
                    "match_type": match_type,
                }
            )
        items.sort(key=lambda item: (-float(item["score"]), str(item["key"])))
        if limit is not None and limit >= 0:
            items = items[:limit]
        return {"items": items}

    async def _memory_save(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        key = str(payload.get("key", ""))
        value = payload.get("value")
        if not isinstance(value, dict):
            raise AstrBotError.invalid_input("memory.save 的 value 必须是 object")
        self.memory_store[key] = value
        self._upsert_memory_sidecars(key, value)
        return {}

    async def _memory_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        key = str(payload.get("key", ""))
        if self._purge_expired_memory_entry(key):
            return {"value": None}
        return {"value": self.memory_store.get(key)}

    async def _memory_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._delete_memory_entry(str(payload.get("key", "")))
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
        stored = {"value": value, "ttl_seconds": ttl_seconds}
        self.memory_store[key] = stored
        self._upsert_memory_sidecars(
            key,
            stored,
            expires_at=self._memory_expiration_from_ttl(ttl_seconds),
        )
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
            if self._purge_expired_memory_entry(key):
                items.append({"key": key, "value": None})
                continue
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
            if self._delete_memory_entry(key):
                deleted_count += 1
        return {"deleted_count": deleted_count}

    async def _memory_stats(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        self._purge_expired_memory_entries()
        total_items = len(self.memory_store)
        total_bytes = sum(
            len(str(key)) + len(str(value)) for key, value in self.memory_store.items()
        )
        ttl_entries = len(self._memory_expires_at)
        indexed_items = len(self._memory_index)
        embedded_items = sum(
            1
            for entry in self._memory_index.values()
            if isinstance(entry, dict)
            and isinstance(entry.get("embedding"), list)
            and bool(entry.get("embedding"))
        )
        dirty_items = len(self._memory_dirty_keys)
        return {
            "total_items": total_items,
            "total_bytes": total_bytes,
            "plugin_id": self._require_caller_plugin_id("memory.stats"),
            "ttl_entries": ttl_entries,
            "indexed_items": indexed_items,
            "embedded_items": embedded_items,
            "dirty_items": dirty_items,
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

    async def _platform_list_instances(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        return {
            "platforms": [
                {
                    "id": str(item.get("id", "")),
                    "name": str(item.get("name", "")),
                    "type": str(item.get("type", "")),
                    "status": str(item.get("status", "unknown")),
                }
                for item in self.get_platform_instances()
                if isinstance(item, dict)
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
        self.register(
            self._builtin_descriptor("platform.list_instances", "列出平台实例元信息"),
            call_handler=self._platform_list_instances,
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

    def _register_p0_5_capabilities(self) -> None:
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

    async def _persona_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        record = self._persona_store.get(persona_id)
        if record is None:
            raise AstrBotError.invalid_input(f"persona not found: {persona_id}")
        return {"persona": dict(record)}

    async def _persona_list(
        self, _request_id: str, _payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        personas = [
            dict(self._persona_store[persona_id])
            for persona_id in sorted(self._persona_store.keys())
        ]
        return {"personas": personas}

    async def _persona_create(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.create requires persona object")
        persona_id = str(raw_persona.get("persona_id", "")).strip()
        if not persona_id:
            raise AstrBotError.invalid_input("persona.create requires persona_id")
        if persona_id in self._persona_store:
            raise AstrBotError.invalid_input(f"persona already exists: {persona_id}")
        now = self._now_iso()
        record = {
            "persona_id": persona_id,
            "system_prompt": str(raw_persona.get("system_prompt", "")),
            "begin_dialogs": self._normalize_persona_dialogs_payload(
                raw_persona.get("begin_dialogs")
            ),
            "tools": (
                [str(item) for item in raw_persona.get("tools", [])]
                if isinstance(raw_persona.get("tools"), list)
                else None
            ),
            "skills": (
                [str(item) for item in raw_persona.get("skills", [])]
                if isinstance(raw_persona.get("skills"), list)
                else None
            ),
            "custom_error_message": (
                str(raw_persona.get("custom_error_message"))
                if raw_persona.get("custom_error_message") is not None
                else None
            ),
            "folder_id": (
                str(raw_persona.get("folder_id"))
                if raw_persona.get("folder_id") is not None
                else None
            ),
            "sort_order": int(raw_persona.get("sort_order", 0)),
            "created_at": now,
            "updated_at": now,
        }
        self._persona_store[persona_id] = record
        return {"persona": dict(record)}

    async def _persona_update(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        record = self._persona_store.get(persona_id)
        if record is None:
            return {"persona": None}
        raw_persona = payload.get("persona")
        if not isinstance(raw_persona, dict):
            raise AstrBotError.invalid_input("persona.update requires persona object")
        if (
            "system_prompt" in raw_persona
            and raw_persona.get("system_prompt") is not None
        ):
            record["system_prompt"] = str(raw_persona.get("system_prompt", ""))
        if "begin_dialogs" in raw_persona:
            begin_dialogs = raw_persona.get("begin_dialogs")
            record["begin_dialogs"] = (
                self._normalize_persona_dialogs_payload(begin_dialogs)
                if begin_dialogs is not None
                else []
            )
        if "tools" in raw_persona:
            tools = raw_persona.get("tools")
            record["tools"] = (
                [str(item) for item in tools] if isinstance(tools, list) else None
            )
        if "skills" in raw_persona:
            skills = raw_persona.get("skills")
            record["skills"] = (
                [str(item) for item in skills] if isinstance(skills, list) else None
            )
        if "custom_error_message" in raw_persona:
            custom_error_message = raw_persona.get("custom_error_message")
            record["custom_error_message"] = (
                str(custom_error_message) if custom_error_message is not None else None
            )
        record["updated_at"] = self._now_iso()
        return {"persona": dict(record)}

    async def _persona_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        persona_id = str(payload.get("persona_id", "")).strip()
        if persona_id not in self._persona_store:
            raise AstrBotError.invalid_input(f"persona not found: {persona_id}")
        del self._persona_store[persona_id]
        return {}

    async def _conversation_new(
        self, _request_id: str, payload: dict[str, Any], _token
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
        conversation_id = uuid.uuid4().hex
        now = self._now_iso()
        record = {
            "conversation_id": conversation_id,
            "session": session,
            "platform_id": (
                str(raw_conversation.get("platform_id"))
                if raw_conversation.get("platform_id") is not None
                else self._session_platform_id(session)
            ),
            "history": self._normalize_history_payload(raw_conversation.get("history")),
            "title": (
                str(raw_conversation.get("title"))
                if raw_conversation.get("title") is not None
                else None
            ),
            "persona_id": (
                str(raw_conversation.get("persona_id"))
                if raw_conversation.get("persona_id") is not None
                else None
            ),
            "created_at": now,
            "updated_at": now,
            "token_usage": None,
        }
        self._conversation_store[conversation_id] = record
        self._session_current_conversation_ids[session] = conversation_id
        return {"conversation_id": conversation_id}

    async def _conversation_switch(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = str(payload.get("conversation_id", "")).strip()
        record = self._conversation_store.get(conversation_id)
        if record is None or str(record.get("session", "")) != session:
            raise AstrBotError.invalid_input(
                "conversation.switch requires a conversation in the same session"
            )
        self._session_current_conversation_ids[session] = conversation_id
        return {}

    async def _conversation_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = payload.get("conversation_id")
        normalized_conversation_id = (
            str(conversation_id).strip() if conversation_id is not None else ""
        )
        if not normalized_conversation_id:
            normalized_conversation_id = self._session_current_conversation_ids.get(
                session, ""
            )
        if not normalized_conversation_id:
            return {}
        record = self._conversation_store.get(normalized_conversation_id)
        if record is None:
            return {}
        if str(record.get("session", "")) != session:
            raise AstrBotError.invalid_input(
                "conversation.delete requires a conversation in the same session"
            )
        del self._conversation_store[normalized_conversation_id]
        current_conversation_id = self._session_current_conversation_ids.get(session)
        if current_conversation_id == normalized_conversation_id:
            replacement = next(
                (
                    conversation_id
                    for conversation_id, item in self._conversation_store.items()
                    if str(item.get("session", "")) == session
                ),
                None,
            )
            if replacement is None:
                self._session_current_conversation_ids.pop(session, None)
            else:
                self._session_current_conversation_ids[session] = replacement
        return {}

    async def _conversation_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = str(payload.get("conversation_id", "")).strip()
        record = self._conversation_store.get(conversation_id)
        if record is None and bool(payload.get("create_if_not_exists", False)):
            created = await self._conversation_new(
                _request_id,
                {"session": session, "conversation": {}},
                _token,
            )
            record = self._conversation_store.get(
                str(created.get("conversation_id", "")).strip()
            )
        if record is None:
            return {"conversation": None}
        if str(record.get("session", "")) != session:
            return {"conversation": None}
        return {"conversation": dict(record)}

    async def _conversation_list(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = payload.get("session")
        platform_id = payload.get("platform_id")
        conversations = []
        for conversation_id in sorted(self._conversation_store.keys()):
            item = self._conversation_store[conversation_id]
            if session is not None and str(item.get("session", "")) != str(session):
                continue
            if platform_id is not None and str(item.get("platform_id", "")) != str(
                platform_id
            ):
                continue
            conversations.append(dict(item))
        return {"conversations": conversations}

    async def _conversation_update(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        session = str(payload.get("session", "")).strip()
        conversation_id = payload.get("conversation_id")
        normalized_conversation_id = (
            str(conversation_id).strip() if conversation_id is not None else ""
        )
        if not normalized_conversation_id:
            normalized_conversation_id = self._session_current_conversation_ids.get(
                session, ""
            )
        if not normalized_conversation_id:
            return {}
        record = self._conversation_store.get(normalized_conversation_id)
        if record is None:
            return {}
        if str(record.get("session", "")) != session:
            raise AstrBotError.invalid_input(
                "conversation.update requires a conversation in the same session"
            )
        raw_conversation = payload.get("conversation")
        if not isinstance(raw_conversation, dict):
            raw_conversation = {}
        if "history" in raw_conversation:
            history = raw_conversation.get("history")
            record["history"] = (
                self._normalize_history_payload(history) if history is not None else []
            )
        if "title" in raw_conversation:
            title = raw_conversation.get("title")
            record["title"] = str(title) if title is not None else None
        if "persona_id" in raw_conversation:
            persona_id = raw_conversation.get("persona_id")
            record["persona_id"] = str(persona_id) if persona_id is not None else None
        if "token_usage" in raw_conversation:
            token_usage = raw_conversation.get("token_usage")
            record["token_usage"] = (
                int(token_usage) if token_usage is not None else None
            )
        record["updated_at"] = self._now_iso()
        return {}

    async def _kb_get(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        record = self._kb_store.get(kb_id)
        return {"kb": dict(record) if isinstance(record, dict) else None}

    async def _kb_create(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        raw_kb = payload.get("kb")
        if not isinstance(raw_kb, dict):
            raise AstrBotError.invalid_input("kb.create requires kb object")
        embedding_provider_id = str(raw_kb.get("embedding_provider_id", "")).strip()
        if not embedding_provider_id:
            raise AstrBotError.invalid_input("kb.create requires embedding_provider_id")
        kb_id = uuid.uuid4().hex
        now = self._now_iso()
        record = {
            "kb_id": kb_id,
            "kb_name": str(raw_kb.get("kb_name", "")),
            "description": (
                str(raw_kb.get("description"))
                if raw_kb.get("description") is not None
                else None
            ),
            "emoji": (
                str(raw_kb.get("emoji")) if raw_kb.get("emoji") is not None else None
            ),
            "embedding_provider_id": embedding_provider_id,
            "rerank_provider_id": (
                str(raw_kb.get("rerank_provider_id"))
                if raw_kb.get("rerank_provider_id") is not None
                else None
            ),
            "chunk_size": self._optional_int(raw_kb.get("chunk_size")),
            "chunk_overlap": self._optional_int(raw_kb.get("chunk_overlap")),
            "top_k_dense": self._optional_int(raw_kb.get("top_k_dense")),
            "top_k_sparse": self._optional_int(raw_kb.get("top_k_sparse")),
            "top_m_final": self._optional_int(raw_kb.get("top_m_final")),
            "doc_count": 0,
            "chunk_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        self._kb_store[kb_id] = record
        return {"kb": dict(record)}

    async def _kb_delete(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        kb_id = str(payload.get("kb_id", "")).strip()
        deleted = self._kb_store.pop(kb_id, None) is not None
        return {"deleted": deleted}

    def _register_p1_2_capabilities(self) -> None:
        self.register(
            self._builtin_descriptor("persona.get", "获取人格"),
            call_handler=self._persona_get,
        )
        self.register(
            self._builtin_descriptor("persona.list", "列出人格"),
            call_handler=self._persona_list,
        )
        self.register(
            self._builtin_descriptor("persona.create", "创建人格"),
            call_handler=self._persona_create,
        )
        self.register(
            self._builtin_descriptor("persona.update", "更新人格"),
            call_handler=self._persona_update,
        )
        self.register(
            self._builtin_descriptor("persona.delete", "删除人格"),
            call_handler=self._persona_delete,
        )
        self.register(
            self._builtin_descriptor("conversation.new", "新建对话"),
            call_handler=self._conversation_new,
        )
        self.register(
            self._builtin_descriptor("conversation.switch", "切换对话"),
            call_handler=self._conversation_switch,
        )
        self.register(
            self._builtin_descriptor("conversation.delete", "删除对话"),
            call_handler=self._conversation_delete,
        )
        self.register(
            self._builtin_descriptor("conversation.get", "获取对话"),
            call_handler=self._conversation_get,
        )
        self.register(
            self._builtin_descriptor("conversation.list", "列出对话"),
            call_handler=self._conversation_list,
        )
        self.register(
            self._builtin_descriptor("conversation.update", "更新对话"),
            call_handler=self._conversation_update,
        )
        self.register(
            self._builtin_descriptor("kb.get", "获取知识库"),
            call_handler=self._kb_get,
        )
        self.register(
            self._builtin_descriptor("kb.create", "创建知识库"),
            call_handler=self._kb_create,
        )
        self.register(
            self._builtin_descriptor("kb.delete", "删除知识库"),
            call_handler=self._kb_delete,
        )

    def _register_p1_3_capabilities(self) -> None:
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
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_by_id",
                "按 ID 获取平台管理快照",
            ),
            call_handler=self._platform_manager_get_by_id,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.clear_errors",
                "清除平台错误",
            ),
            call_handler=self._platform_manager_clear_errors,
        )
        self.register(
            self._builtin_descriptor(
                "platform.manager.get_stats",
                "获取平台统计信息",
            ),
            call_handler=self._platform_manager_get_stats,
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
            self._builtin_descriptor("system.file.register", "注册文件令牌"),
            call_handler=self._system_file_register,
            exposed=False,
        )
        self.register(
            self._builtin_descriptor("system.file.handle", "解析文件令牌"),
            call_handler=self._system_file_handle,
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
        self.register(
            self._builtin_descriptor(
                "registry.command.register",
                "注册动态命令路由",
            ),
            call_handler=self._registry_command_register,
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

    async def _system_file_register(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        path = str(payload.get("path", "")).strip()
        if not path:
            raise AstrBotError.invalid_input("system.file.register requires path")
        file_token = uuid.uuid4().hex
        self._file_token_store[file_token] = path
        return {"token": file_token, "url": f"mock://file/{file_token}"}

    async def _system_file_handle(
        self, _request_id: str, payload: dict[str, Any], _token
    ) -> dict[str, Any]:
        file_token = str(payload.get("token", "")).strip()
        if not file_token:
            raise AstrBotError.invalid_input("system.file.handle requires token")
        path = self._file_token_store.pop(file_token, None)
        if path is None:
            raise AstrBotError.invalid_input(f"Unknown file token: {file_token}")
        return {"path": path}

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
        if event_type == "message":
            for plugin_name, routes in self._dynamic_command_routes.items():
                for route in routes:
                    if not isinstance(route, dict):
                        continue
                    handlers.append(
                        {
                            "plugin_name": str(route.get("plugin_name", plugin_name)),
                            "handler_full_name": str(
                                route.get("handler_full_name", "")
                            ),
                            "trigger_type": (
                                "message"
                                if bool(route.get("use_regex", False))
                                else "command"
                            ),
                            "event_types": ["message"],
                            "enabled": True,
                            "group_path": [],
                        }
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

    async def _registry_command_register(
        self, _request_id: str, payload: dict[str, Any], _token
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
                "registry.command.register 的 priority 必须是 integer"
            )
        plugin_id = self._require_caller_plugin_id("registry.command.register")
        self.register_dynamic_command_route(
            plugin_id=plugin_id,
            command_name=str(payload.get("command_name", "")),
            handler_full_name=str(payload.get("handler_full_name", "")),
            desc=str(payload.get("desc", "")),
            priority=priority_value,
            use_regex=bool(payload.get("use_regex", False)),
        )
        return {}

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
