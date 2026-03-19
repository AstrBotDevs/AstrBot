from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ...._memory_utils import (
    cosine_similarity,
    extract_memory_text,
    is_ttl_memory_entry,
    memory_expiration_from_ttl,
    memory_index_entry,
    memory_keyword_score,
    memory_value_for_search,
)
from ....errors import AstrBotError
from ..bridge_base import CapabilityRouterBridgeBase


class MemoryCapabilityMixin(CapabilityRouterBridgeBase):
    @staticmethod
    def _is_ttl_memory_entry(value: Any) -> bool:
        """判断存储值是否使用了 TTL 包装结构。

        Args:
            value: 待检查的存储值。

        Returns:
            bool: 如果值包含 ``value`` 和 ``ttl_seconds`` 字段则返回 ``True``。
        """
        return is_ttl_memory_entry(value)

    @classmethod
    def _memory_value_for_search(cls, stored: Any) -> dict[str, Any] | None:
        """提取用于检索的原始 memory payload。

        Args:
            stored: memory_store 中保存的原始值。

        Returns:
            dict[str, Any] | None: 解开 TTL 包装后的字典，无法解析时返回 ``None``。
        """
        return memory_value_for_search(stored)

    @classmethod
    def _extract_memory_text(cls, stored: Any) -> str:
        """提取用于检索索引的首选文本。

        Args:
            stored: memory_store 中保存的原始值。

        Returns:
            str: 优先使用 ``embedding_text`` / ``content`` 等字段，兜底为 JSON 文本。
        """
        return extract_memory_text(stored)

    @staticmethod
    def _memory_expiration_from_ttl(ttl_seconds: Any) -> datetime | None:
        """将 TTL 秒数转换为 UTC 过期时间。

        Args:
            ttl_seconds: TTL 秒数。

        Returns:
            datetime | None: 绝对过期时间；当输入无效时返回 ``None``。
        """
        return memory_expiration_from_ttl(ttl_seconds)

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
        return memory_keyword_score(query, key, text)

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        """计算两个向量之间的余弦相似度。

        Args:
            left: 左侧向量。
            right: 右侧向量。

        Returns:
            float: 余弦相似度；输入不合法时返回 ``0.0``。
        """
        return cosine_similarity(left, right)

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
        return memory_index_entry(entry, text=text)

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
        raw_min_score = payload.get("min_score")
        min_score = float(raw_min_score) if raw_min_score is not None else None
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
