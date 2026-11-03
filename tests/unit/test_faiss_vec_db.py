import asyncio
import errno
import os
import tempfile
from unittest.mock import AsyncMock

import pytest

from astrbot.core.db.vec_db.faiss_impl import embedding_storage
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


def test_safe_temp_dir_raises_when_every_candidate_rejects_creation(
    tmp_path, monkeypatch
) -> None:
    system_root = str(tmp_path / "Windows")
    system_temp = os.path.join(system_root, "Temp")
    fallback_dir = str(tmp_path / "fallback")
    os.makedirs(fallback_dir)

    monkeypatch.setattr(embedding_storage.os, "name", "nt")
    monkeypatch.setenv("SystemRoot", system_root)
    monkeypatch.setattr(embedding_storage.os.path, "isdir", lambda _path: True)
    monkeypatch.setattr(embedding_storage.os, "access", lambda *_args: True)
    monkeypatch.setattr(embedding_storage.tempfile, "gettempdir", lambda: fallback_dir)

    def deny_creation(*_args, **_kwargs):
        raise PermissionError(errno.EACCES, "Permission denied")

    monkeypatch.setattr(embedding_storage.tempfile, "mkstemp", deny_creation)

    with pytest.raises(OSError) as exc_info:
        embedding_storage._safe_temp_dir()

    message = str(exc_info.value)
    assert system_temp in message
    assert fallback_dir in message
    assert "Permission denied" in message


def test_safe_temp_dir_falls_back_to_a_writable_candidate(
    tmp_path, monkeypatch
) -> None:
    system_root = str(tmp_path / "Windows")
    system_temp = os.path.join(system_root, "Temp")
    fallback_dir = str(tmp_path / "fallback")
    os.makedirs(fallback_dir)

    monkeypatch.setattr(embedding_storage.os, "name", "nt")
    monkeypatch.setenv("SystemRoot", system_root)
    monkeypatch.setattr(embedding_storage.tempfile, "gettempdir", lambda: fallback_dir)

    real_mkstemp = tempfile.mkstemp

    def reject_system_temp(*args, **kwargs):
        if kwargs.get("dir") == system_temp:
            raise PermissionError(errno.EACCES, "Permission denied")
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(embedding_storage.tempfile, "mkstemp", reject_system_temp)

    assert embedding_storage._safe_temp_dir() == fallback_dir


def test_make_temp_file_returns_a_writable_file() -> None:
    path = embedding_storage._make_temp_file("_test")
    try:
        assert os.path.isfile(path)
        with open(path, "w", encoding="utf-8") as file:
            file.write("ok")
    finally:
        os.remove(path)


def test_write_index_bridges_through_a_temp_file(tmp_path, monkeypatch) -> None:
    faiss = pytest.importorskip("faiss")
    monkeypatch.setattr(embedding_storage, "_needs_bridge", lambda _path: True)

    index = faiss.IndexFlatL2(2)
    path = str(tmp_path / "中文索引.faiss")

    EmbeddingStorage._write_index(index, path)

    assert os.path.isfile(path)
    assert EmbeddingStorage._read_index(path).d == 2


@pytest.mark.asyncio
async def test_get_embeddings_batch_preserves_input_order_when_batches_finish_out_of_order():
    provider = DelayedEmbeddingProvider()

    embeddings = await provider.get_embeddings_batch(
        ["chunk-0", "chunk-1", "chunk-2", "chunk-3"],
        batch_size=2,
        tasks_limit=2,
    )

    assert embeddings == [[0.0], [1.0], [2.0], [3.0]]
