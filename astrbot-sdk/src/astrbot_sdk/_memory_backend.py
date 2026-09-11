from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import threading
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from ._internal.memory_utils import (
    cosine_similarity,
    display_memory_namespace,
    extract_memory_text,
    join_memory_namespace,
    memory_keyword_score,
    memory_namespace_matches,
    memory_value_for_search,
    normalize_embedding,
    normalize_memory_namespace,
)


def _utcnow() -> datetime:
    # Centralize time access so expiry tests can advance time without mutating SQLite internals.
    return datetime.now(timezone.utc)


def _sql_placeholders(count: int) -> str:
    if count <= 0:
        raise ValueError("count must be positive")
    return ", ".join("?" for _ in range(count))


def _normalize_scope_namespace(namespace: str | None) -> str | None:
    if namespace is None:
        return None
    return normalize_memory_namespace(namespace)


def _escape_like_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


EmbedMany = Callable[[list[str]], Awaitable[list[list[float]]] | list[list[float]]]
EmbedOne = Callable[[str], Awaitable[list[float]] | list[float]]


@dataclass(slots=True)
class MemorySearchResult:
    key: str
    namespace: str
    value: dict[str, Any] | None
    score: float
    match_type: str

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "key": self.key,
            "value": self.value,
            "score": self.score,
            "match_type": self.match_type,
        }
        namespace = display_memory_namespace(self.namespace)
        if namespace is not None:
            payload["namespace"] = namespace
        return payload


@dataclass(slots=True)
class _StoredRecord:
    namespace: str
    key: str
    stored: dict[str, Any]
    search_text: str
    updated_at: str


@dataclass(slots=True)
class _VectorCandidate:
    namespace: str
    key: str
    stored: dict[str, Any]
    search_text: str
    score: float


class PluginMemoryBackend:
    """Persistent plugin-scoped memory backend with namespace-aware search."""

    def __init__(self, data_dir: Path) -> None:
        self._base_dir = Path(data_dir) / "memory"
        self._db_path = self._base_dir / "memory.sqlite3"
        self._vector_dir = self._base_dir / "vectors"
        self._lock = threading.RLock()
        self._initialized = False
        self._fts_enabled = False
        self._vector_indexes: dict[str, Any | None] = {}
        self._vector_fallbacks: dict[str, list[tuple[int, list[float]]]] = {}

    async def save(
        self,
        key: str,
        value: dict[str, Any],
        *,
        namespace: str | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._save_sync,
            str(key),
            dict(value),
            normalize_memory_namespace(namespace),
            None,
        )

    async def save_with_ttl(
        self,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int,
        *,
        namespace: str | None = None,
    ) -> None:
        expires_at = _utcnow().timestamp() + max(int(ttl_seconds), 0)
        await asyncio.to_thread(
            self._save_sync,
            str(key),
            dict(value),
            normalize_memory_namespace(namespace),
            {
                "ttl_seconds": int(ttl_seconds),
                "expires_at": datetime.fromtimestamp(
                    expires_at,
                    tz=timezone.utc,
                ).isoformat(),
            },
        )

    async def get(
        self,
        key: str,
        *,
        namespace: str | None = None,
    ) -> dict[str, Any] | None:
        return await asyncio.to_thread(
            self._get_sync,
            str(key),
            normalize_memory_namespace(namespace),
        )

    async def list_keys(
        self,
        *,
        namespace: str | None = None,
    ) -> list[str]:
        return await asyncio.to_thread(
            self._list_keys_sync,
            normalize_memory_namespace(namespace),
        )

    async def exists(
        self,
        key: str,
        *,
        namespace: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._exists_sync,
            str(key),
            normalize_memory_namespace(namespace),
        )

    async def get_many(
        self,
        keys: list[str],
        *,
        namespace: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_namespace = normalize_memory_namespace(namespace)
        return await asyncio.to_thread(
            self._get_many_sync,
            [str(item) for item in keys],
            normalized_namespace,
        )

    async def delete(
        self,
        key: str,
        *,
        namespace: str | None = None,
    ) -> bool:
        return await asyncio.to_thread(
            self._delete_sync,
            str(key),
            normalize_memory_namespace(namespace),
        )

    async def clear_namespace(
        self,
        *,
        namespace: str | None = None,
        include_descendants: bool = False,
    ) -> int:
        normalized_namespace = _normalize_scope_namespace(namespace)
        return await asyncio.to_thread(
            self._clear_namespace_sync,
            normalized_namespace,
            bool(include_descendants),
        )

    async def delete_many(
        self,
        keys: list[str],
        *,
        namespace: str | None = None,
    ) -> int:
        normalized_namespace = normalize_memory_namespace(namespace)
        return await asyncio.to_thread(
            self._delete_many_sync,
            [str(item) for item in keys],
            normalized_namespace,
        )

    async def count(
        self,
        *,
        namespace: str | None = None,
        include_descendants: bool = False,
    ) -> int:
        normalized_namespace = _normalize_scope_namespace(namespace)
        return await asyncio.to_thread(
            self._count_sync,
            normalized_namespace,
            bool(include_descendants),
        )

    async def stats(
        self,
        *,
        namespace: str | None = None,
        include_descendants: bool = True,
    ) -> dict[str, Any]:
        normalized_namespace = _normalize_scope_namespace(namespace)
        return await asyncio.to_thread(
            self._stats_sync,
            normalized_namespace,
            bool(include_descendants),
        )

    async def search(
        self,
        query: str,
        *,
        namespace: str | None = None,
        include_descendants: bool = True,
        mode: str,
        limit: int | None,
        min_score: float | None,
        provider_id: str | None = None,
        embed_one: EmbedOne | None = None,
        embed_many: EmbedMany | None = None,
    ) -> list[dict[str, Any]]:
        normalized_namespace = _normalize_scope_namespace(namespace)
        normalized_mode = str(mode).strip().lower() or "keyword"
        query_text = str(query)

        await asyncio.to_thread(self._purge_expired_sync)

        keyword_candidates = await asyncio.to_thread(
            self._keyword_candidates_sync,
            query_text,
            normalized_namespace,
            bool(include_descendants),
            limit,
        )

        vector_candidates: list[_VectorCandidate] = []
        if normalized_mode in {"vector", "hybrid"} and provider_id:
            await self._ensure_embeddings(
                provider_id=provider_id,
                namespace=normalized_namespace,
                include_descendants=bool(include_descendants),
                embed_one=embed_one,
                embed_many=embed_many,
            )
            if embed_one is not None:
                raw_query_embedding = await _maybe_await(embed_one(query_text))
                query_embedding = normalize_embedding(
                    [float(item) for item in raw_query_embedding]
                )
                vector_candidates = await asyncio.to_thread(
                    self._vector_candidates_sync,
                    provider_id,
                    query_embedding,
                    normalized_namespace,
                    bool(include_descendants),
                    limit,
                )

        merged: dict[tuple[str, str], dict[str, Any]] = {}
        for record in keyword_candidates:
            identity = (record.namespace, record.key)
            merged[identity] = {
                "namespace": record.namespace,
                "key": record.key,
                "stored": record.stored,
                "keyword_score": memory_keyword_score(
                    query_text,
                    record.key,
                    record.search_text,
                ),
                "vector_score": 0.0,
            }
        for record in vector_candidates:
            identity = (record.namespace, record.key)
            current = merged.setdefault(
                identity,
                {
                    "namespace": record.namespace,
                    "key": record.key,
                    "stored": record.stored,
                    "keyword_score": memory_keyword_score(
                        query_text,
                        record.key,
                        record.search_text,
                    ),
                    "vector_score": 0.0,
                },
            )
            current["vector_score"] = max(
                float(current["vector_score"]),
                float(record.score),
            )

        results: list[MemorySearchResult] = []
        for item in merged.values():
            keyword_score = max(0.0, float(item["keyword_score"]))
            vector_score = max(0.0, float(item["vector_score"]))
            score = self._combined_score(
                mode=normalized_mode,
                keyword_score=keyword_score,
                vector_score=vector_score,
            )
            if score <= 0:
                continue
            if min_score is not None and score < float(min_score):
                continue

            if normalized_mode == "keyword" or (
                keyword_score > 0 and vector_score <= 0
            ):
                match_type = "keyword"
            elif normalized_mode == "vector" or keyword_score <= 0:
                match_type = "vector"
            else:
                match_type = "hybrid"

            results.append(
                MemorySearchResult(
                    key=str(item["key"]),
                    namespace=str(item["namespace"]),
                    value=memory_value_for_search(item["stored"]),
                    score=score,
                    match_type=match_type,
                )
            )

        results.sort(key=lambda item: (-item.score, item.namespace, item.key))
        if limit is not None and limit >= 0:
            results = results[:limit]
        return [item.to_payload() for item in results]

    async def _ensure_embeddings(
        self,
        *,
        provider_id: str,
        namespace: str | None,
        include_descendants: bool,
        embed_one: EmbedOne | None,
        embed_many: EmbedMany | None,
    ) -> None:
        missing = await asyncio.to_thread(
            self._missing_embeddings_sync,
            provider_id,
            namespace,
            include_descendants,
        )
        if missing:
            texts = [record.search_text for record in missing]
            embeddings: list[list[float]]
            if embed_many is not None:
                raw_embeddings = await _maybe_await(embed_many(texts))
                embeddings = [
                    normalize_embedding([float(value) for value in item])
                    for item in raw_embeddings
                ]
            elif embed_one is not None:
                embeddings = []
                for text in texts:
                    raw_vector = await _maybe_await(embed_one(text))
                    embeddings.append(
                        normalize_embedding([float(value) for value in raw_vector])
                    )
            else:
                embeddings = []
            await asyncio.to_thread(
                self._upsert_embeddings_sync,
                provider_id,
                missing,
                embeddings,
            )
        await asyncio.to_thread(self._ensure_vector_index_sync, provider_id)

    def _save_sync(
        self,
        key: str,
        value: dict[str, Any],
        namespace: str,
        ttl_metadata: dict[str, Any] | None,
    ) -> None:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                stored = dict(value)
                expires_at: str | None = None
                if ttl_metadata is not None:
                    expires_at = str(ttl_metadata.get("expires_at", "")).strip() or None
                    stored = {
                        "value": dict(value),
                        "ttl_seconds": int(ttl_metadata.get("ttl_seconds", 0)),
                    }
                    if expires_at is not None:
                        stored["expires_at"] = expires_at
                search_text = extract_memory_text(stored)
                stored_json = json.dumps(
                    stored,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
                updated_at = _utcnow().isoformat()
                conn.execute(
                    """
                    INSERT INTO memory_records(namespace, key, stored_json, search_text, expires_at, updated_at)
                    VALUES(?, ?, ?, ?, ?, ?)
                    ON CONFLICT(namespace, key) DO UPDATE SET
                        stored_json = excluded.stored_json,
                        search_text = excluded.search_text,
                        expires_at = excluded.expires_at,
                        updated_at = excluded.updated_at
                    """,
                    (namespace, key, stored_json, search_text, expires_at, updated_at),
                )
                self._sync_fts_row_locked(
                    conn,
                    namespace=namespace,
                    key=key,
                    search_text=search_text,
                )
                provider_rows = conn.execute(
                    """
                    SELECT DISTINCT provider_id
                    FROM memory_embeddings
                    WHERE namespace = ? AND key = ?
                    """,
                    (namespace, key),
                ).fetchall()
                conn.execute(
                    "DELETE FROM memory_embeddings WHERE namespace = ? AND key = ?",
                    (namespace, key),
                )
                for row in provider_rows:
                    provider_id = str(row[0]).strip()
                    if provider_id:
                        self._mark_vector_dirty_locked(conn, provider_id)
                conn.commit()
            finally:
                conn.close()

    def _get_sync(self, key: str, namespace: str) -> dict[str, Any] | None:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                row = conn.execute(
                    """
                    SELECT stored_json
                    FROM memory_records
                    WHERE namespace = ? AND key = ?
                    """,
                    (namespace, key),
                ).fetchone()
                if row is None:
                    return None
                stored = self._load_stored_json(row[0])
                return memory_value_for_search(stored)
            finally:
                conn.close()

    def _list_keys_sync(self, namespace: str) -> list[str]:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                rows = conn.execute(
                    """
                    SELECT key
                    FROM memory_records
                    WHERE namespace = ?
                    ORDER BY key COLLATE NOCASE ASC, key ASC
                    """,
                    (namespace,),
                ).fetchall()
                return [str(row[0]) for row in rows]
            finally:
                conn.close()

    def _exists_sync(self, key: str, namespace: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                row = conn.execute(
                    """
                    SELECT 1
                    FROM memory_records
                    WHERE namespace = ? AND key = ?
                    LIMIT 1
                    """,
                    (namespace, key),
                ).fetchone()
                return row is not None
            finally:
                conn.close()

    def _get_many_sync(self, keys: list[str], namespace: str) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                if not keys:
                    return []
                lookup_keys = list(dict.fromkeys(keys))
                placeholders = _sql_placeholders(len(lookup_keys))
                rows = conn.execute(
                    f"""
                    SELECT key, stored_json
                    FROM memory_records
                    WHERE namespace = ? AND key IN ({placeholders})
                    """,
                    (namespace, *lookup_keys),
                ).fetchall()
                stored_by_key = {
                    str(row[0]): self._load_stored_json(row[1]) for row in rows
                }
                return [
                    {
                        "key": key,
                        "value": memory_value_for_search(stored_by_key.get(key)),
                    }
                    for key in keys
                ]
            finally:
                conn.close()

    def _delete_sync(self, key: str, namespace: str) -> bool:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                deleted = self._delete_record_locked(conn, namespace=namespace, key=key)
                conn.commit()
                return deleted
            finally:
                conn.close()

    def _clear_namespace_sync(
        self,
        namespace: str | None,
        include_descendants: bool,
    ) -> int:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                deleted = self._delete_scope_locked(
                    conn,
                    namespace=namespace,
                    include_descendants=include_descendants,
                )
                conn.commit()
                return deleted
            finally:
                conn.close()

    def _delete_many_sync(self, keys: list[str], namespace: str) -> int:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                unique_keys = list(dict.fromkeys(keys))
                if not unique_keys:
                    conn.commit()
                    return 0
                placeholders = _sql_placeholders(len(unique_keys))
                provider_rows = conn.execute(
                    f"""
                    SELECT DISTINCT provider_id
                    FROM memory_embeddings
                    WHERE namespace = ? AND key IN ({placeholders})
                    """,
                    (namespace, *unique_keys),
                ).fetchall()
                conn.execute(
                    f"DELETE FROM memory_embeddings WHERE namespace = ? AND key IN ({placeholders})",
                    (namespace, *unique_keys),
                )
                deleted = conn.execute(
                    f"DELETE FROM memory_records WHERE namespace = ? AND key IN ({placeholders})",
                    (namespace, *unique_keys),
                ).rowcount
                if self._fts_enabled:
                    conn.execute(
                        f"DELETE FROM memory_records_fts WHERE namespace = ? AND key IN ({placeholders})",
                        (namespace, *unique_keys),
                    )
                for row in provider_rows:
                    provider_id = str(row[0]).strip()
                    if provider_id:
                        self._mark_vector_dirty_locked(conn, provider_id)
                conn.commit()
                return deleted
            finally:
                conn.close()

    def _count_sync(
        self,
        namespace: str | None,
        include_descendants: bool,
    ) -> int:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                where_sql, params = self._namespace_where(
                    namespace,
                    include_descendants=include_descendants,
                )
                return int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM memory_records WHERE {where_sql}",
                        params,
                    ).fetchone()[0]
                )
            finally:
                conn.close()

    def _stats_sync(
        self,
        namespace: str | None,
        include_descendants: bool,
    ) -> dict[str, Any]:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                where_sql, params = self._namespace_where(
                    namespace,
                    include_descendants=include_descendants,
                )
                total_items = int(
                    conn.execute(
                        f"SELECT COUNT(*) FROM memory_records WHERE {where_sql}",
                        params,
                    ).fetchone()[0]
                )
                ttl_entries = int(
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM memory_records
                        WHERE {where_sql} AND expires_at IS NOT NULL
                        """,
                        params,
                    ).fetchone()[0]
                )
                total_bytes = int(
                    conn.execute(
                        f"""
                        SELECT COALESCE(SUM(LENGTH(key) + LENGTH(stored_json)), 0)
                        FROM memory_records
                        WHERE {where_sql}
                        """,
                        params,
                    ).fetchone()[0]
                )
                namespace_count = int(
                    conn.execute(
                        f"""
                        SELECT COUNT(DISTINCT namespace)
                        FROM memory_records
                        WHERE {where_sql}
                        """,
                        params,
                    ).fetchone()[0]
                )
                embedding_where_sql, embedding_params = self._namespace_where(
                    namespace,
                    include_descendants=include_descendants,
                    alias="e",
                )
                embedded_items = int(
                    conn.execute(
                        f"""
                        SELECT COUNT(*)
                        FROM (
                            SELECT DISTINCT e.namespace, e.key
                            FROM memory_embeddings e
                            WHERE {embedding_where_sql}
                        )
                        """,
                        embedding_params,
                    ).fetchone()[0]
                )
                indexed_items = total_items
                dirty_items = max(indexed_items - embedded_items, 0)
                provider_rows = conn.execute(
                    """
                    SELECT provider_id, dirty
                    FROM memory_vector_state
                    ORDER BY provider_id
                    """
                ).fetchall()
                return {
                    "total_items": total_items,
                    "total_bytes": total_bytes,
                    "ttl_entries": ttl_entries,
                    "namespace": (
                        None
                        if namespace is None
                        else normalize_memory_namespace(namespace)
                    ),
                    "namespace_count": namespace_count,
                    "indexed_items": indexed_items,
                    "embedded_items": embedded_items,
                    "dirty_items": dirty_items,
                    "fts_enabled": self._fts_enabled,
                    "vector_backend": self._vector_backend_label(),
                    "vector_indexes": [
                        {
                            "provider_id": str(provider_id),
                            "dirty": bool(dirty),
                        }
                        for provider_id, dirty in provider_rows
                    ],
                }
            finally:
                conn.close()

    def _keyword_candidates_sync(
        self,
        query: str,
        namespace: str | None,
        include_descendants: bool,
        limit: int | None,
    ) -> list[_StoredRecord]:
        with self._lock:
            conn = self._connect()
            try:
                fetch_limit = max((int(limit) if limit is not None else 10) * 8, 50)
                where_sql, params = self._namespace_where(
                    namespace,
                    include_descendants=include_descendants,
                )
                seen: set[tuple[str, str]] = set()
                records: list[_StoredRecord] = []
                fts_query = self._fts_query(query)
                if self._fts_enabled and fts_query is not None:
                    fts_where_sql, fts_params = self._namespace_where(
                        namespace,
                        include_descendants=include_descendants,
                        alias="r",
                    )
                    rows = conn.execute(
                        f"""
                        SELECT r.namespace, r.key, r.stored_json, r.search_text, r.updated_at
                        FROM memory_records_fts f
                        JOIN memory_records r
                          ON r.namespace = f.namespace AND r.key = f.key
                        WHERE {fts_where_sql} AND memory_records_fts MATCH ?
                        ORDER BY bm25(memory_records_fts), r.updated_at DESC
                        LIMIT ?
                        """,
                        (*fts_params, fts_query, fetch_limit),
                    ).fetchall()
                    for row in rows:
                        record = self._stored_record_from_row(row)
                        identity = (record.namespace, record.key)
                        if identity not in seen:
                            seen.add(identity)
                            records.append(record)

                like_query = f"%{str(query).strip()}%"
                if not records or len(records) < fetch_limit:
                    rows = conn.execute(
                        f"""
                        SELECT namespace, key, stored_json, search_text, updated_at
                        FROM memory_records
                        WHERE {where_sql}
                          AND (? = '%%' OR key LIKE ? COLLATE NOCASE OR search_text LIKE ? COLLATE NOCASE)
                        ORDER BY updated_at DESC
                        LIMIT ?
                        """,
                        (*params, like_query, like_query, like_query, fetch_limit),
                    ).fetchall()
                    for row in rows:
                        record = self._stored_record_from_row(row)
                        identity = (record.namespace, record.key)
                        if identity not in seen:
                            seen.add(identity)
                            records.append(record)
                return records
            finally:
                conn.close()

    def _missing_embeddings_sync(
        self,
        provider_id: str,
        namespace: str | None,
        include_descendants: bool,
    ) -> list[_StoredRecord]:
        with self._lock:
            conn = self._connect()
            try:
                where_sql, params = self._namespace_where(
                    namespace,
                    include_descendants=include_descendants,
                    alias="r",
                )
                rows = conn.execute(
                    f"""
                    SELECT r.namespace, r.key, r.stored_json, r.search_text, r.updated_at
                    FROM memory_records r
                    LEFT JOIN memory_embeddings e
                      ON e.namespace = r.namespace
                     AND e.key = r.key
                     AND e.provider_id = ?
                    WHERE {where_sql} AND e.id IS NULL
                    ORDER BY r.updated_at DESC
                    """,
                    (provider_id, *params),
                ).fetchall()
                return [self._stored_record_from_row(row) for row in rows]
            finally:
                conn.close()

    def _upsert_embeddings_sync(
        self,
        provider_id: str,
        records: list[_StoredRecord],
        embeddings: list[list[float]],
    ) -> None:
        if not records:
            return
        with self._lock:
            conn = self._connect()
            try:
                for index, record in enumerate(records):
                    vector = embeddings[index] if index < len(embeddings) else []
                    conn.execute(
                        """
                        INSERT INTO memory_embeddings(namespace, key, provider_id, embedding_json, updated_at)
                        VALUES(?, ?, ?, ?, ?)
                        ON CONFLICT(namespace, key, provider_id) DO UPDATE SET
                            embedding_json = excluded.embedding_json,
                            updated_at = excluded.updated_at
                        """,
                        (
                            record.namespace,
                            record.key,
                            provider_id,
                            json.dumps(
                                vector, ensure_ascii=False, separators=(",", ":")
                            ),
                            _utcnow().isoformat(),
                        ),
                    )
                self._mark_vector_dirty_locked(conn, provider_id)
                conn.commit()
            finally:
                conn.close()

    def _vector_candidates_sync(
        self,
        provider_id: str,
        query_embedding: list[float],
        namespace: str | None,
        include_descendants: bool,
        limit: int | None,
    ) -> list[_VectorCandidate]:
        if not query_embedding:
            return []
        with self._lock:
            conn = self._connect()
            try:
                index = self._vector_indexes.get(provider_id)
                fetch_limit = max((int(limit) if limit is not None else 10) * 10, 50)
                if index is not None and self._faiss_available():
                    return self._faiss_vector_candidates_locked(
                        conn=conn,
                        provider_id=provider_id,
                        query_embedding=query_embedding,
                        namespace=namespace,
                        include_descendants=include_descendants,
                        fetch_limit=fetch_limit,
                    )
                return self._fallback_vector_candidates_locked(
                    conn=conn,
                    provider_id=provider_id,
                    query_embedding=query_embedding,
                    namespace=namespace,
                    include_descendants=include_descendants,
                    fetch_limit=fetch_limit,
                )
            finally:
                conn.close()

    def _ensure_vector_index_sync(self, provider_id: str) -> None:
        with self._lock:
            conn = self._connect()
            try:
                self._init_storage_locked(conn)
                row = conn.execute(
                    """
                    SELECT dirty
                    FROM memory_vector_state
                    WHERE provider_id = ?
                    """,
                    (provider_id,),
                ).fetchone()
                dirty = True if row is None else bool(row[0])
                if not dirty and provider_id in self._vector_indexes:
                    return

                index_path = (
                    self._vector_dir / f"{self._safe_filename(provider_id)}.faiss"
                )
                if not dirty and index_path.exists() and self._faiss_available():
                    try:
                        faiss = self._import_faiss()
                        self._vector_indexes[provider_id] = faiss.read_index(
                            str(index_path)
                        )
                        self._vector_fallbacks.pop(provider_id, None)
                        return
                    except Exception:
                        pass

                rows = conn.execute(
                    """
                    SELECT id, embedding_json
                    FROM memory_embeddings
                    WHERE provider_id = ?
                    ORDER BY id
                    """,
                    (provider_id,),
                ).fetchall()
                ids: list[int] = []
                vectors: list[list[float]] = []
                for raw_id, raw_vector in rows:
                    vector = self._load_embedding_json(raw_vector)
                    if not vector:
                        continue
                    ids.append(int(raw_id))
                    vectors.append(vector)

                if self._faiss_available() and vectors:
                    faiss = self._import_faiss()
                    np = self._import_numpy()
                    dimension = len(vectors[0])
                    base_index = faiss.IndexFlatIP(dimension)
                    index = faiss.IndexIDMap2(base_index)
                    index.add_with_ids(
                        np.array(vectors, dtype="float32"),
                        np.array(ids, dtype="int64"),
                    )
                    self._vector_indexes[provider_id] = index
                    self._vector_fallbacks.pop(provider_id, None)
                    self._vector_dir.mkdir(parents=True, exist_ok=True)
                    faiss.write_index(index, str(index_path))
                else:
                    self._vector_indexes[provider_id] = None
                    self._vector_fallbacks[provider_id] = list(
                        zip(ids, vectors, strict=False)
                    )
                conn.execute(
                    """
                    INSERT INTO memory_vector_state(provider_id, dirty, updated_at)
                    VALUES(?, 0, ?)
                    ON CONFLICT(provider_id) DO UPDATE SET
                        dirty = 0,
                        updated_at = excluded.updated_at
                    """,
                    (provider_id, _utcnow().isoformat()),
                )
                conn.commit()
            finally:
                conn.close()

    def _faiss_vector_candidates_locked(
        self,
        *,
        conn: sqlite3.Connection,
        provider_id: str,
        query_embedding: list[float],
        namespace: str | None,
        include_descendants: bool,
        fetch_limit: int,
    ) -> list[_VectorCandidate]:
        index = self._vector_indexes.get(provider_id)
        if index is None:
            return []
        np = self._import_numpy()
        total_count = int(getattr(index, "ntotal", 0) or 0)
        if total_count <= 0:
            return []

        collected: list[_VectorCandidate] = []
        seen: set[tuple[str, str]] = set()
        current_limit = min(fetch_limit, total_count)
        while current_limit > 0:
            scores, ids = index.search(
                np.array([query_embedding], dtype="float32"),
                current_limit,
            )
            raw_ids = [int(item) for item in ids[0] if int(item) >= 0]
            score_map = {
                int(item_id): max(0.0, float(score))
                for item_id, score in zip(raw_ids, scores[0], strict=False)
            }
            if not score_map:
                break
            placeholders = ",".join("?" for _ in score_map)
            rows = conn.execute(
                f"""
                SELECT e.id, r.namespace, r.key, r.stored_json, r.search_text
                FROM memory_embeddings e
                JOIN memory_records r
                  ON r.namespace = e.namespace AND r.key = e.key
                WHERE e.provider_id = ?
                  AND e.id IN ({placeholders})
                """,
                (provider_id, *score_map.keys()),
            ).fetchall()
            row_map = {int(row[0]): row for row in rows}
            for item_id in raw_ids:
                row = row_map.get(item_id)
                if row is None:
                    continue
                record_namespace = normalize_memory_namespace(row[1])
                if not memory_namespace_matches(
                    record_namespace,
                    namespace,
                    include_descendants=include_descendants,
                ):
                    continue
                identity = (record_namespace, str(row[2]))
                if identity in seen:
                    continue
                seen.add(identity)
                collected.append(
                    _VectorCandidate(
                        namespace=record_namespace,
                        key=str(row[2]),
                        stored=self._load_stored_json(row[3]),
                        search_text=str(row[4]),
                        score=max(0.0, score_map.get(item_id, 0.0)),
                    )
                )
            if len(collected) >= fetch_limit or current_limit >= total_count:
                break
            next_limit = min(total_count, current_limit * 2)
            if next_limit == current_limit:
                break
            current_limit = next_limit
        return collected

    def _fallback_vector_candidates_locked(
        self,
        *,
        conn: sqlite3.Connection,
        provider_id: str,
        query_embedding: list[float],
        namespace: str | None,
        include_descendants: bool,
        fetch_limit: int,
    ) -> list[_VectorCandidate]:
        rows = conn.execute(
            """
            SELECT e.namespace, e.key, e.embedding_json, r.stored_json, r.search_text
            FROM memory_embeddings e
            JOIN memory_records r
              ON r.namespace = e.namespace AND r.key = e.key
            WHERE e.provider_id = ?
            """,
            (provider_id,),
        ).fetchall()
        candidates: list[_VectorCandidate] = []
        for raw_namespace, raw_key, raw_embedding, raw_stored, raw_search_text in rows:
            record_namespace = normalize_memory_namespace(raw_namespace)
            if not memory_namespace_matches(
                record_namespace,
                namespace,
                include_descendants=include_descendants,
            ):
                continue
            embedding = self._load_embedding_json(raw_embedding)
            score = max(0.0, cosine_similarity(query_embedding, embedding))
            if score <= 0:
                continue
            candidates.append(
                _VectorCandidate(
                    namespace=record_namespace,
                    key=str(raw_key),
                    stored=self._load_stored_json(raw_stored),
                    search_text=str(raw_search_text),
                    score=score,
                )
            )
        candidates.sort(key=lambda item: (-item.score, item.namespace, item.key))
        return candidates[:fetch_limit]

    def _purge_expired_sync(self) -> None:
        with self._lock:
            conn = self._connect()
            try:
                self._purge_expired_locked(conn)
                conn.commit()
            finally:
                conn.close()

    def _purge_expired_locked(self, conn: sqlite3.Connection) -> None:
        self._init_storage_locked(conn)
        now_iso = _utcnow().isoformat()
        rows = conn.execute(
            """
            SELECT namespace, key
            FROM memory_records
            WHERE expires_at IS NOT NULL AND expires_at <= ?
            """,
            (now_iso,),
        ).fetchall()
        for namespace, key in rows:
            self._delete_record_locked(
                conn,
                namespace=normalize_memory_namespace(namespace),
                key=str(key),
            )

    def _delete_record_locked(
        self,
        conn: sqlite3.Connection,
        *,
        namespace: str,
        key: str,
    ) -> bool:
        provider_rows = conn.execute(
            """
            SELECT DISTINCT provider_id
            FROM memory_embeddings
            WHERE namespace = ? AND key = ?
            """,
            (namespace, key),
        ).fetchall()
        conn.execute(
            "DELETE FROM memory_embeddings WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        deleted = (
            conn.execute(
                "DELETE FROM memory_records WHERE namespace = ? AND key = ?",
                (namespace, key),
            ).rowcount
            > 0
        )
        if self._fts_enabled:
            conn.execute(
                "DELETE FROM memory_records_fts WHERE namespace = ? AND key = ?",
                (namespace, key),
            )
        for row in provider_rows:
            provider_id = str(row[0]).strip()
            if provider_id:
                self._mark_vector_dirty_locked(conn, provider_id)
        return deleted

    def _delete_scope_locked(
        self,
        conn: sqlite3.Connection,
        *,
        namespace: str | None,
        include_descendants: bool,
    ) -> int:
        where_sql, params = self._namespace_where(
            namespace,
            include_descendants=include_descendants,
        )
        affected_rows = conn.execute(
            f"""
            SELECT namespace, key
            FROM memory_records
            WHERE {where_sql}
            """,
            params,
        ).fetchall()
        if not affected_rows:
            return 0

        pair_placeholders = ", ".join("(?, ?)" for _ in affected_rows)
        pair_params = tuple(
            value
            for raw_namespace, raw_key in affected_rows
            for value in (normalize_memory_namespace(raw_namespace), str(raw_key))
        )

        provider_rows = conn.execute(
            f"""
            SELECT DISTINCT provider_id
            FROM memory_embeddings
            WHERE (namespace, key) IN ({pair_placeholders})
            """,
            pair_params,
        ).fetchall()
        conn.execute(
            f"""
            DELETE FROM memory_embeddings
            WHERE (namespace, key) IN ({pair_placeholders})
            """,
            pair_params,
        )
        if self._fts_enabled:
            conn.execute(
                f"""
                DELETE FROM memory_records_fts
                WHERE (namespace, key) IN ({pair_placeholders})
                """,
                pair_params,
            )
        deleted = conn.execute(
            f"""
            DELETE FROM memory_records
            WHERE (namespace, key) IN ({pair_placeholders})
            """,
            pair_params,
        ).rowcount
        for row in provider_rows:
            provider_id = str(row[0]).strip()
            if provider_id:
                self._mark_vector_dirty_locked(conn, provider_id)
        return deleted

    def _connect(self) -> sqlite3.Connection:
        self._base_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        self._init_storage_locked(conn)
        return conn

    def _init_storage_locked(self, conn: sqlite3.Connection) -> None:
        if self._initialized:
            return
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_records (
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                stored_json TEXT NOT NULL,
                search_text TEXT NOT NULL,
                expires_at TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(namespace, key)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_records_namespace
            ON memory_records(namespace)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_records_expires_at
            ON memory_records(expires_at)
            """
        )
        try:
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_records_fts
                USING fts5(namespace UNINDEXED, key, search_text, tokenize='unicode61')
                """
            )
            self._fts_enabled = True
        except sqlite3.OperationalError:
            self._fts_enabled = False
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_embeddings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace TEXT NOT NULL,
                key TEXT NOT NULL,
                provider_id TEXT NOT NULL,
                embedding_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(namespace, key, provider_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_embeddings_provider
            ON memory_embeddings(provider_id, namespace)
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_vector_state (
                provider_id TEXT PRIMARY KEY,
                dirty INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
        self._initialized = True

    def _sync_fts_row_locked(
        self,
        conn: sqlite3.Connection,
        *,
        namespace: str,
        key: str,
        search_text: str,
    ) -> None:
        if not self._fts_enabled:
            return
        conn.execute(
            "DELETE FROM memory_records_fts WHERE namespace = ? AND key = ?",
            (namespace, key),
        )
        conn.execute(
            """
            INSERT INTO memory_records_fts(namespace, key, search_text)
            VALUES(?, ?, ?)
            """,
            (namespace, key, search_text),
        )

    def _mark_vector_dirty_locked(
        self,
        conn: sqlite3.Connection,
        provider_id: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO memory_vector_state(provider_id, dirty, updated_at)
            VALUES(?, 1, ?)
            ON CONFLICT(provider_id) DO UPDATE SET
                dirty = 1,
                updated_at = excluded.updated_at
            """,
            (provider_id, _utcnow().isoformat()),
        )
        self._vector_indexes.pop(provider_id, None)
        self._vector_fallbacks.pop(provider_id, None)

    @staticmethod
    def _combined_score(
        *,
        mode: str,
        keyword_score: float,
        vector_score: float,
    ) -> float:
        if mode == "keyword":
            return keyword_score
        if mode == "vector":
            return vector_score
        if keyword_score > 0 and vector_score > 0:
            return min(1.0, 0.65 * vector_score + 0.35 * keyword_score + 0.05)
        if vector_score > 0:
            return min(1.0, vector_score)
        return min(1.0, keyword_score)

    @staticmethod
    def _load_stored_json(raw_value: Any) -> dict[str, Any]:
        if isinstance(raw_value, dict):
            return dict(raw_value)
        if isinstance(raw_value, str):
            decoded = json.loads(raw_value)
            return dict(decoded) if isinstance(decoded, dict) else {}
        return {}

    @staticmethod
    def _load_embedding_json(raw_value: Any) -> list[float]:
        if isinstance(raw_value, list):
            return [float(item) for item in raw_value]
        if isinstance(raw_value, str):
            decoded = json.loads(raw_value)
            if isinstance(decoded, list):
                return [float(item) for item in decoded]
        return []

    @staticmethod
    def _stored_record_from_row(row: Any) -> _StoredRecord:
        return _StoredRecord(
            namespace=normalize_memory_namespace(row[0]),
            key=str(row[1]),
            stored=PluginMemoryBackend._load_stored_json(row[2]),
            search_text=str(row[3]),
            updated_at=str(row[4]),
        )

    @staticmethod
    def _namespace_where(
        namespace: str | None,
        *,
        include_descendants: bool,
        alias: str | None = None,
    ) -> tuple[str, tuple[Any, ...]]:
        column = f"{alias}.namespace" if alias else "namespace"
        if namespace is None:
            return "1 = 1", ()
        normalized_namespace = normalize_memory_namespace(namespace)
        if not normalized_namespace:
            if include_descendants:
                return "1 = 1", ()
            return f"{column} = ''", ()
        if include_descendants:
            escaped_namespace = _escape_like_value(normalized_namespace)
            return (
                f"({column} = ? OR {column} LIKE ? ESCAPE '\\')",
                (normalized_namespace, f"{escaped_namespace}/%"),
            )
        return f"{column} = ?", (normalized_namespace,)

    @staticmethod
    def _fts_query(query: str) -> str | None:
        stripped = str(query).strip()
        if not stripped:
            return None
        terms = [
            item for item in re.findall(r"\w+", stripped, flags=re.UNICODE) if item
        ]
        if not terms:
            return None
        escaped_terms = [term.replace('"', '""') for term in terms[:8]]
        return " OR ".join(f'"{term}"' for term in escaped_terms)

    @staticmethod
    def _safe_filename(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._") or "default"

    @staticmethod
    def _import_faiss() -> Any:
        # FAISS often ships without stable type stubs, so keep the lazy import
        # boundary explicitly dynamic to avoid false-positive Pylance errors.
        import faiss

        return cast(Any, faiss)

    @staticmethod
    def _import_numpy():
        import numpy

        return numpy

    @classmethod
    def _faiss_available(cls) -> bool:
        try:
            faiss = cls._import_faiss()
            cls._import_numpy()
        except Exception:
            return False
        required_attrs = (
            "IndexFlatIP",
            "IndexIDMap2",
            "read_index",
            "write_index",
        )
        return all(hasattr(faiss, attr) for attr in required_attrs)

    def _vector_backend_label(self) -> str:
        return "faiss" if self._faiss_available() else "exact"


async def _maybe_await(value: Any) -> Any:
    if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
        return await value
    return value


def extend_memory_namespace(
    base_namespace: str | None,
    extra_namespace: str | None,
) -> str:
    """Join a base namespace with a relative namespace override."""

    return join_memory_namespace(base_namespace, extra_namespace)
