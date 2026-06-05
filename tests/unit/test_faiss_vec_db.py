from unittest.mock import AsyncMock, MagicMock

import numpy as np
import pytest

from astrbot.core.db.vec_db.faiss_impl.vec_db import EmbeddingCache, FaissVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError


def _make_vecdb():
    """创建最小化的 FaissVecDB mock"""
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = MagicMock()
    vec_db.embedding_storage.dimension = 128
    vec_db.embedding_cache = EmbeddingCache(max_size=100)
    return vec_db


@pytest.mark.asyncio
async def test_insert_batch_skips_empty_contents() -> None:
    vec_db = _make_vecdb()

    result = await FaissVecDB.insert_batch(vec_db, [])

    assert result == []
    vec_db.embedding_provider.get_embeddings_batch.assert_not_called()
    vec_db.document_storage.insert_documents_batch.assert_not_called()
    vec_db.embedding_storage.insert_batch.assert_not_called()


@pytest.mark.asyncio
async def test_insert_batch_raises_friendly_error_for_embedding_count_mismatch() -> (
    None
):
    vec_db = _make_vecdb()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [[0.1, 0.2]]
    vec_db.embedding_storage.dimension = 2

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1", "chunk-2"],
            metadatas=[{}, {}],
            ids=["doc-1", "doc-2"],
        )

    assert "向量化失败" in str(exc_info.value)
    assert "期望 2" in str(exc_info.value)
    assert "实际 1" in str(exc_info.value)
    vec_db.document_storage.insert_documents_batch.assert_not_called()
    vec_db.embedding_storage.insert_batch.assert_not_called()


class TestEmbeddingCache:
    """Phase 2B: 嵌入缓存测试"""

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_value(self):
        """缓存命中时返回已缓存的向量"""
        cache = EmbeddingCache(max_size=100)
        text = "hello world"
        emb = np.array([0.1, 0.2, 0.3], dtype=np.float32)

        await cache.put(text, emb)
        result = await cache.get(text)

        assert result is not None
        assert np.array_equal(result, emb)

    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        """缓存未命中时返回 None"""
        cache = EmbeddingCache(max_size=100)
        result = await cache.get("unknown text")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        """超出 max_size 时最早的条目应被淘汰"""
        cache = EmbeddingCache(max_size=3)
        for i in range(5):
            await cache.put(f"text_{i}", np.array([float(i)], dtype=np.float32))

        assert await cache.__len__() == 3
        # text_0 和 text_1 应该被淘汰
        assert await cache.get("text_0") is None
        assert await cache.get("text_1") is None
        # text_2, text_3, text_4 应该仍然存在
        assert await cache.get("text_2") is not None
        assert await cache.get("text_3") is not None
        assert await cache.get("text_4") is not None

    @pytest.mark.asyncio
    async def test_insert_batch_uses_cache(self):
        """insert_batch 缓存命中时减少 provider 调用"""
        vec_db = _make_vecdb()
        # 预缓存两个文本
        await vec_db.embedding_cache.put(
            "cached_1", np.array([0.5] * 128, dtype=np.float32),
        )
        await vec_db.embedding_cache.put(
            "cached_2", np.array([0.6] * 128, dtype=np.float32),
        )
        vec_db.embedding_provider.get_embeddings_batch.return_value = (
            [[0.1] * 128]
        )
        vec_db.document_storage.insert_documents_batch = AsyncMock(
            return_value=[10, 11, 12],
        )
        vec_db.embedding_storage.insert_batch = AsyncMock()

        result = await FaissVecDB.insert_batch(
            vec_db,
            contents=["cached_1", "cached_2", "fresh_text"],
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )
        assert len(result) == 3
        # 只应调用一次 get_embeddings_batch（仅 fresh_text 未缓存）
        assert vec_db.embedding_provider.get_embeddings_batch.call_count == 1
