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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("embedding_contents", "expected_embedding_contents"),
    [
        (None, ["chunk one", "chunk two"]),
        (
            ["guide\n\nchunk one", "guide\n\nchunk two"],
            ["guide\n\nchunk one", "guide\n\nchunk two"],
        ),
    ],
)
async def test_insert_batch_uses_embedding_contents_without_changing_storage(
    embedding_contents: list[str] | None,
    expected_embedding_contents: list[str],
) -> None:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1, 0.2],
        [0.3, 0.4],
    ]
    vec_db.document_storage = AsyncMock()
    vec_db.document_storage.insert_documents_batch.return_value = [11, 12]
    vec_db.embedding_storage = AsyncMock()
    vec_db.embedding_storage.dimension = 2

    await FaissVecDB.insert_batch(
        vec_db,
        contents=["chunk one", "chunk two"],
        metadatas=[{}, {}],
        ids=["doc-1", "doc-2"],
        embedding_contents=embedding_contents,
    )

    vec_db.embedding_provider.get_embeddings_batch.assert_awaited_once_with(
        expected_embedding_contents,
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
        progress_callback=None,
    )
    vec_db.document_storage.insert_documents_batch.assert_awaited_once_with(
        ["doc-1", "doc-2"],
        ["chunk one", "chunk two"],
        [{}, {}],
    )


@pytest.mark.asyncio
async def test_insert_batch_rejects_embedding_content_count_mismatch() -> None:
    vec_db = FaissVecDB.__new__(FaissVecDB)
    vec_db.embedding_provider = AsyncMock()
    vec_db.document_storage = AsyncMock()
    vec_db.embedding_storage = AsyncMock()

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk one", "chunk two"],
            metadatas=[{}, {}],
            ids=["doc-1", "doc-2"],
            embedding_contents=["guide\n\nchunk one"],
        )

    assert exc_info.value.stage == "storage"
    assert exc_info.value.details == {
        "expected_contents": 2,
        "actual_embedding_contents": 1,
    }
    vec_db.embedding_provider.get_embeddings_batch.assert_not_awaited()
    vec_db.document_storage.insert_documents_batch.assert_not_awaited()


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


def test_embedding_storage_write_index_is_atomic_on_failure(
    tmp_path, monkeypatch
) -> None:
    """Failed FAISS index persistence leaves the prior index intact without temp leaks."""
    import faiss
    import numpy as np

    index_path = tmp_path / "index.faiss"
    storage = EmbeddingStorage(2, str(index_path))
    storage._insert_batch_sync(
        np.array([[1.0, 0.0]], dtype=np.float32),
        [1],
    )
    baseline_bytes = index_path.read_bytes()

    def failing_write(_index, path):
        with open(path, "wb") as f:
            f.write(b"corrupted-partial-bytes")
        raise OSError("disk full")

    monkeypatch.setattr(faiss, "write_index", failing_write)
    with pytest.raises(OSError, match="disk full"):
        EmbeddingStorage._write_index(storage.index, str(index_path))

    assert index_path.read_bytes() == baseline_bytes
    assert [p.name for p in tmp_path.iterdir()] == ["index.faiss"]


@pytest.mark.asyncio
async def test_embedding_storage_offloads_faiss_ops_from_event_loop(
    tmp_path, monkeypatch
) -> None:
    """Async FAISS operations run in a worker thread via asyncio.to_thread."""
    import threading

    import faiss
    import numpy as np

    main_thread_id = threading.get_ident()
    observed_threads: list[int] = []

    storage = EmbeddingStorage(2, str(tmp_path / "threaded.faiss"))
    original_add = storage.index.add_with_ids
    original_search = storage.index.search
    original_remove = storage.index.remove_ids
    original_write = faiss.write_index

    def wrap_write(index, path):
        observed_threads.append(threading.get_ident())
        return original_write(getattr(index, "_target", index), path)

    monkeypatch.setattr(faiss, "write_index", wrap_write)

    class _IndexProxy:
        def __init__(self, target):
            self._target = target

        def add_with_ids(self, vectors, ids):
            observed_threads.append(threading.get_ident())
            return original_add(vectors, ids)

        def search(self, vector, k):
            observed_threads.append(threading.get_ident())
            return original_search(vector, k)

        def remove_ids(self, ids):
            observed_threads.append(threading.get_ident())
            return original_remove(ids)

    storage.index = _IndexProxy(storage.index)
    await storage.insert_batch(np.array([[1.0, 2.0]], dtype=np.float32), [7])
    await storage.search(np.array([1.0, 2.0], dtype=np.float32), 1)
    await storage.delete([7])

    assert len(observed_threads) >= 5
    assert all(tid != main_thread_id for tid in observed_threads)


@pytest.mark.asyncio
async def test_faiss_retrieve_handles_more_than_100_candidates_and_empty_ids(
    tmp_path,
) -> None:
    """FaissVecDB.retrieve passes limit=None and DocumentStorage handles all -1 ids."""
    provider = DelayedEmbeddingProvider()
    vec_db = FaissVecDB(
        doc_store_path=str(tmp_path / "docs.db"),
        index_store_path=str(tmp_path / "vec.faiss"),
        embedding_provider=provider,
    )
    await vec_db.initialize()
    try:
        total = 120
        await vec_db.insert_batch(
            contents=[f"chunk-{i}" for i in range(total)],
            metadatas=[{"kb_id": "kb1", "idx": i} for i in range(total)],
            ids=[f"doc-{i}" for i in range(total)],
            batch_size=total,
        )

        # k=105 triggers fetch_k > 100 when filtered; previously truncated to 100.
        results = await vec_db.retrieve(
            "chunk-0",
            k=105,
            fetch_k=115,
            metadata_filters={"kb_id": "kb1"},
        )
        assert len(results) == 105

        no_match = await vec_db.document_storage.get_documents(
            metadata_filters={},
            ids=[-1, -1],
        )
        assert no_match == []
    finally:
        await vec_db.close()


@pytest.mark.asyncio
async def test_concurrent_embedding_storage_instances_preserve_all_writes(
    tmp_path,
) -> None:
    """Two EmbeddingStorage instances targeting the same file coordinate updates."""
    import numpy as np

    index_path = tmp_path / "shared.faiss"
    storage_a = EmbeddingStorage(2, str(index_path))
    storage_b = EmbeddingStorage(2, str(index_path))

    await asyncio.gather(
        storage_a.insert_batch(np.array([[1.0, 0.0]], dtype=np.float32), [1]),
        storage_b.insert_batch(np.array([[0.0, 1.0]], dtype=np.float32), [2]),
    )

    reloaded = EmbeddingStorage(2, str(index_path))
    assert reloaded.index.ntotal == 2


@pytest.mark.asyncio
async def test_single_insert_rolls_back_doc_and_vector_on_save_failure(
    tmp_path, monkeypatch
) -> None:
    """FaissVecDB.insert rolls back document row and vector when FAISS save fails."""
    import faiss

    provider = DelayedEmbeddingProvider()
    vec_db = FaissVecDB(
        doc_store_path=str(tmp_path / "docs_rollback.db"),
        index_store_path=str(tmp_path / "vec_rollback.faiss"),
        embedding_provider=provider,
    )
    await vec_db.initialize()
    try:

        def failing_write(_index, _path):
            raise OSError("save error")

        monkeypatch.setattr(faiss, "write_index", failing_write)
        with pytest.raises(OSError, match="save error"):
            await vec_db.insert("chunk-1", {"kb_id": "kb1"}, id="single-doc-1")

        assert await vec_db.count_documents() == 0
        assert vec_db.embedding_storage.index.ntotal == 0
    finally:
        await vec_db.close()
