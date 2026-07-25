import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.provider.provider import EmbeddingProvider


class DelayedEmbeddingProvider(EmbeddingProvider):
    def __init__(self) -> None:
        super().__init__({}, {})

    async def get_embedding(self, text: str) -> list[float]:
        return [float(text.removeprefix("chunk-"))]

    async def get_embeddings(self, text: list[str]) -> list[list[float]]:
        if text[0] == "chunk-0":
            await asyncio.sleep(0.02)
        return [[float(item.removeprefix("chunk-"))] for item in text]

    def get_dim(self) -> int:
        return 1


@pytest.mark.asyncio
async def test_insert_batch_skips_empty_contents() -> None:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()

    result = await FaissVecDB.insert_batch(vec_db, [])

    assert result == []
    vec_db.embedding_provider.get_embeddings_batch.assert_not_awaited()
    vec_db.document_storage.insert_documents_batch.assert_not_awaited()
    vec_db.embedding_storage.insert_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_insert_batch_raises_friendly_error_for_embedding_count_mismatch() -> (
    None
):
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [[0.1, 0.2]]
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()
    vec_db.embedding_storage.dimension = 2

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1", "chunk-2"],
            metadatas=[{}, {}],
            ids=["doc-1", "doc-2"],
        )

    assert "向量化失败" in str(exc_info.value)
    assert "期望 2，实际 1" in str(exc_info.value)
    vec_db.document_storage.insert_documents_batch.assert_not_awaited()
    vec_db.embedding_storage.insert_batch.assert_not_awaited()


def test_embedding_storage_rejects_zero_dimension_for_a_fresh_index(tmp_path) -> None:
    with pytest.raises(ValueError, match="无效的嵌入向量维度"):
        EmbeddingStorage(0, str(tmp_path / "index.faiss"))


def test_embedding_storage_rejects_negative_dimension_for_a_fresh_index() -> None:
    with pytest.raises(ValueError, match="无效的嵌入向量维度"):
        EmbeddingStorage(-1)


def test_embedding_storage_accepts_a_valid_dimension_for_a_fresh_index() -> None:
    storage = EmbeddingStorage(4)

    assert storage.index.d == 4


@pytest.mark.asyncio
async def test_get_embeddings_batch_preserves_input_order_when_batches_finish_out_of_order():
    provider = DelayedEmbeddingProvider()

    embeddings = await provider.get_embeddings_batch(
        ["chunk-0", "chunk-1", "chunk-2", "chunk-3"],
        batch_size=2,
        tasks_limit=2,
    )

    assert embeddings == [[0.0], [1.0], [2.0], [3.0]]
