from unittest.mock import AsyncMock

import pytest

from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError


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


@pytest.mark.parametrize("dimension", [0, -1])
def test_embedding_storage_rejects_non_positive_dimension_for_fresh_index(
    tmp_path,
    dimension: int,
) -> None:
    with pytest.raises(ValueError, match="无效的嵌入向量维度"):
        EmbeddingStorage(dimension, str(tmp_path / "index.faiss"))


def test_embedding_storage_accepts_valid_dimension_for_fresh_index() -> None:
    storage = EmbeddingStorage(4)

    assert storage.index.d == 4


@pytest.mark.asyncio
async def test_insert_batch_validates_dimension_before_writing_documents() -> None:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [[0.1, 0.2, 0.3]]
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()
    vec_db.embedding_storage.dimension = 2

    with pytest.raises(
        KnowledgeBaseUploadError, match="维度与当前知识库索引维度不一致"
    ):
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1"],
            metadatas=[{}],
            ids=["doc-1"],
        )

    vec_db.document_storage.insert_documents_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_insert_batch_rolls_back_documents_when_faiss_write_fails() -> None:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [[0.1, 0.2]]
    vec_db.document_storage = AsyncMock()
    vec_db.document_storage.insert_documents_batch.return_value = [11]
    vec_db.embedding_storage = AsyncMock()
    vec_db.embedding_storage.dimension = 2
    vec_db.embedding_storage.insert_batch.side_effect = RuntimeError(
        "index write failed"
    )

    with pytest.raises(RuntimeError, match="index write failed"):
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1"],
            metadatas=[{}],
            ids=["doc-1"],
        )

    vec_db.embedding_storage.delete.assert_awaited_once_with([11])
    vec_db.document_storage.delete_document_by_doc_id.assert_awaited_once_with("doc-1")
