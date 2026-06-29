from unittest.mock import AsyncMock, MagicMock, patch

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
async def test_insert_batch_raises_friendly_error_for_embedding_count_mismatch() -> None:
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

    assert exc_info.value.stage == "embedding"
    assert "期望 2，实际 1" in str(exc_info.value)
    assert exc_info.value.details["expected_contents"] == 2
    assert exc_info.value.details["actual_vectors"] == 1
    vec_db.document_storage.insert_documents_batch.assert_not_awaited()
    vec_db.embedding_storage.insert_batch.assert_not_awaited()


@pytest.mark.asyncio
async def test_insert_batch_wraps_embedding_batch_failures_as_embedding_error() -> None:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.embedding_provider.get_embeddings_batch.side_effect = Exception("rate limit")
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()
    vec_db.embedding_storage.dimension = 2

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1"],
            metadatas=[{}],
            ids=["doc-1"],
        )

    assert exc_info.value.stage == "embedding"
    assert "批量生成嵌入向量时出错" in str(exc_info.value)
    assert "rate limit" in str(exc_info.value)
    vec_db.document_storage.insert_documents_batch.assert_not_awaited()
    vec_db.embedding_storage.insert_batch.assert_not_awaited()


def test_embedding_storage_rejects_existing_index_dimension_mismatch() -> None:
    mock_index = MagicMock()
    mock_index.d = 768

    with (
        patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.os.path.exists",
            return_value=True,
        ),
        patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.faiss.read_index",
            return_value=mock_index,
        ),
    ):
        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            EmbeddingStorage(1536, "existing-index.faiss")

    assert exc_info.value.stage == "embedding"
    assert "知识库索引维度与当前嵌入模型维度不一致" in str(exc_info.value)
    assert exc_info.value.details == {
        "index_dimension": 768,
        "provider_dimension": 1536,
    }


def test_embedding_storage_accepts_existing_index_dimension_match() -> None:
    mock_index = MagicMock()
    mock_index.d = 768

    with (
        patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.os.path.exists",
            return_value=True,
        ),
        patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.faiss.read_index",
            return_value=mock_index,
        ),
    ):
        storage = EmbeddingStorage(768, "existing-index.faiss")

    assert storage.index is mock_index
    assert storage.dimension == 768
