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


def test_l2_normalize_scales_rows_to_unit_length() -> None:
    import numpy as np

    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import _l2_normalize

    vectors = np.array([[3.0, 4.0], [0.0, 0.0], [0.5, 0.0]], dtype=np.float32)
    normalized = _l2_normalize(vectors)

    norms = np.linalg.norm(normalized, axis=1)
    assert norms[0] == pytest.approx(1.0)
    assert norms[1] == pytest.approx(0.0)  # 全零行保持为零，不产生 NaN
    assert norms[2] == pytest.approx(1.0)
    assert np.array_equal(normalized[0], np.array([0.6, 0.8], dtype=np.float32))


@pytest.mark.asyncio
async def test_embedding_storage_ranks_by_cosine_regardless_of_magnitude() -> None:
    """issue #11006：模长不同的向量必须按方向（余弦）排序，而不是按模长。"""
    import numpy as np

    storage = EmbeddingStorage(2)

    # 相关文档：方向接近查询，但模长被压到很小
    await storage.insert(np.array([0.6, 0.8], dtype=np.float32) * 0.2, 1)
    # 无关文档：与查询正交，但模长很大
    await storage.insert(np.array([0.0, 1.0], dtype=np.float32) * 5.0, 2)

    distances, indices = await storage.search(np.array([1.0, 0.0], dtype=np.float32), 2)

    assert indices[0][0] == 1, "语义更近的文档必须排在前面"
    scores = 1 - distances[0] / 2.0
    assert scores[0] == pytest.approx(0.6, abs=1e-5)
    assert scores[1] == pytest.approx(0.0, abs=1e-5)


@pytest.mark.asyncio
async def test_embedding_storage_batch_insert_also_normalizes() -> None:
    import numpy as np

    storage = EmbeddingStorage(2)
    vectors = np.array(
        [[0.6, 0.8], [0.0, 2.0]],
        dtype=np.float32,
    ) * np.array([[0.3], [1.0]], dtype=np.float32)

    await storage.insert_batch(vectors, [1, 2])
    distances, indices = await storage.search(np.array([1.0, 0.0], dtype=np.float32), 2)

    assert indices[0].tolist() == [1, 2]
    assert (1 - distances[0] / 2.0)[0] == pytest.approx(0.6, abs=1e-5)


@pytest.mark.asyncio
async def test_retrieve_uses_query_embedding_hook() -> None:
    """retrieve 必须走 get_query_embedding，才能带上查询侧任务条件化。"""
    import numpy as np

    class QueryAwareProvider(EmbeddingProvider):
        def __init__(self) -> None:
            super().__init__({}, {})
            self.query_calls: list[str] = []

        async def get_embedding(self, text: str) -> list[float]:
            return [1.0, 0.0]

        async def get_query_embedding(self, text: str) -> list[float]:
            self.query_calls.append(text)
            return [1.0, 0.0]

        async def get_embeddings(self, text: list[str]) -> list[list[float]]:
            return [[1.0, 0.0] for _ in text]

        def get_dim(self) -> int:
            return 2

    provider = QueryAwareProvider()
    vec_db = FaissVecDB.__new__(FaissVecDB)
    from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage

    vec_db.embedding_provider = provider
    vec_db.rerank_provider = None
    vec_db.embedding_storage = EmbeddingStorage(2)
    vec_db.document_storage = DocumentStorage(":memory:")
    await vec_db.document_storage.initialize()
    await vec_db.embedding_storage.insert(np.array([1.0, 0.0], dtype=np.float32), 1)

    await vec_db.retrieve(query="查询词", k=1)

    assert provider.query_calls == ["查询词"]


def test_l2_normalize_handles_extreme_magnitudes_without_nan() -> None:
    """极大/极小模长都不能产出 NaN 或 inf。"""
    import numpy as np

    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import _l2_normalize

    vectors = np.array(
        [[1e-30, 0.0], [3e38, 0.0], [0.0, 0.0], [3.0, 4.0]],
        dtype=np.float32,
    )
    normalized = _l2_normalize(vectors)

    assert not np.isnan(normalized).any()
    assert not np.isinf(normalized).any()
    # 极小模长不放大噪声，保持原样
    assert normalized[0][0] == pytest.approx(1e-30, rel=1e-6)
    # 极大模长应正确归一化，而不是被 float32 溢出成 0
    assert normalized[1][0] == pytest.approx(1.0)
    assert normalized[3] == pytest.approx(np.array([0.6, 0.8], dtype=np.float32))


def test_l2_normalize_preserves_empty_batch() -> None:
    import numpy as np

    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import _l2_normalize

    empty = np.zeros((0, 4), dtype=np.float32)
    assert _l2_normalize(empty).shape == (0, 4)


@pytest.mark.asyncio
async def test_loading_legacy_index_normalizes_stored_vectors() -> None:
    """旧版本入库未归一化，加载时必须重建，否则两侧标准不一致。"""
    import os

    import numpy as np

    faiss = pytest.importorskip("faiss")
    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    # faiss 的 C++ 层在 Windows 上无法写非 ASCII 路径，这里用纯 ASCII 临时目录。
    tmp_dir = _ascii_tmp_dir()
    path = os.path.join(tmp_dir, "legacy.faiss")
    # 旧索引：未归一化，模长各不相同
    legacy = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    legacy.add_with_ids(
        np.array([[0.6, 0.8], [0.0, 1.0]], dtype=np.float32)
        * np.array([[0.5], [3.0]], dtype=np.float32),
        np.array([1, 2], dtype=np.int64),
    )
    faiss.write_index(legacy, path)

    storage = EmbeddingStorage(2, path)
    assert storage._pending_save is True

    distances, indices = await storage.search(np.array([1.0, 0.0], dtype=np.float32), 2)
    assert indices[0].tolist() == [1, 2]
    scores = 1 - distances[0] / 2.0
    assert scores[0] == pytest.approx(0.6, abs=1e-5)
    assert scores[1] == pytest.approx(0.0, abs=1e-5)

    await storage.flush()
    assert storage._pending_save is False

    # 重新加载后不应再次触发迁移
    reloaded = EmbeddingStorage(2, path)
    assert reloaded._pending_save is False
    redo_dist, _ = await reloaded.search(np.array([1.0, 0.0], dtype=np.float32), 2)
    assert (1 - redo_dist[0] / 2.0)[0] == pytest.approx(0.6, abs=1e-5)


@pytest.mark.asyncio
async def test_flush_is_noop_for_fresh_index() -> None:
    storage = EmbeddingStorage(4)
    assert storage._pending_save is False
    await storage.flush()
    assert storage._pending_save is False


@pytest.mark.asyncio
async def test_zero_vector_does_not_retrigger_migration() -> None:
    """零向量模长为 0，不能让它被误判成"未归一化"而反复重建索引。"""
    import os

    import numpy as np

    faiss = pytest.importorskip("faiss")
    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    tmp_dir = _ascii_tmp_dir()
    path = os.path.join(tmp_dir, "zero.faiss")

    index = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    index.add_with_ids(
        np.array([[0.6, 0.8], [0.0, 0.0]], dtype=np.float32),
        np.array([1, 2], dtype=np.int64),
    )
    faiss.write_index(index, path)

    first = EmbeddingStorage(2, path)
    assert first._pending_save is False, "全部已归一化时不应重建"

    second = EmbeddingStorage(2, path)
    assert second._pending_save is False, "零向量不能触发重复迁移"


@pytest.mark.asyncio
async def test_migration_still_runs_when_zero_vector_mixed_with_unnormalized() -> None:
    import os

    import numpy as np

    faiss = pytest.importorskip("faiss")
    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    tmp_dir = _ascii_tmp_dir()
    path = os.path.join(tmp_dir, "mix.faiss")

    index = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    index.add_with_ids(
        np.array([[0.3, 0.4], [0.0, 0.0]], dtype=np.float32),  # 前一个模长 0.5
        np.array([1, 2], dtype=np.int64),
    )
    faiss.write_index(index, path)

    storage = EmbeddingStorage(2, path)
    assert storage._pending_save is True, "存在未归一化向量时仍需迁移"

    distances, indices = await storage.search(np.array([1.0, 0.0], dtype=np.float32), 2)
    assert indices[0][0] == 1
    assert (1 - distances[0] / 2.0)[0] == pytest.approx(0.6, abs=1e-5)


@pytest.mark.asyncio
async def test_flush_failure_does_not_break_initialization() -> None:
    """归一化落盘失败不能让知识库打不开；内存索引仍应可用。"""
    import os
    from unittest.mock import patch

    import numpy as np

    faiss = pytest.importorskip("faiss")
    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    tmp_dir = _ascii_tmp_dir()
    path = os.path.join(tmp_dir, "readonly.faiss")

    index = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    index.add_with_ids(
        np.array([[0.3, 0.4]], dtype=np.float32),
        np.array([1], dtype=np.int64),
    )
    faiss.write_index(index, path)

    storage = EmbeddingStorage(2, path)
    assert storage._pending_save is True

    with patch.object(
        EmbeddingStorage, "_write_index", side_effect=OSError("No space left")
    ):
        # 不应抛出
        await storage.flush()

    # 写盘失败要保留标记，以便后续 initialize/close 重试
    assert storage._pending_save is True

    # 内存中的索引已经归一化，检索照常工作
    distances, indices = await storage.search(np.array([1.0, 0.0], dtype=np.float32), 1)
    assert indices[0][0] == 1
    assert (1 - distances[0] / 2.0)[0] == pytest.approx(0.6, abs=1e-5)


@pytest.mark.asyncio
async def test_flush_retries_after_a_write_failure() -> None:
    """一次写盘失败不能让归一化结果永远丢掉。"""
    import os
    from unittest.mock import patch

    import numpy as np

    faiss = pytest.importorskip("faiss")
    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    tmp_dir = _ascii_tmp_dir()
    path = os.path.join(tmp_dir, "retry.faiss")

    index = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    index.add_with_ids(
        np.array([[0.3, 0.4]], dtype=np.float32),
        np.array([1], dtype=np.int64),
    )
    faiss.write_index(index, path)

    storage = EmbeddingStorage(2, path)
    assert storage._pending_save is True

    with patch.object(
        EmbeddingStorage, "_write_index", side_effect=OSError("disk full")
    ):
        await storage.flush()
    assert storage._pending_save is True, "失败后必须保留重试标记"

    # 第二次成功
    await storage.flush()
    assert storage._pending_save is False

    reloaded = EmbeddingStorage(2, path)
    assert reloaded._pending_save is False
    distances, _ = await reloaded.search(np.array([1.0, 0.0], dtype=np.float32), 1)
    assert (1 - distances[0] / 2.0)[0] == pytest.approx(0.6, abs=1e-5)


@pytest.mark.asyncio
async def test_close_flushes_pending_normalization() -> None:
    """close() 也要尝试落盘，别让内存里的归一化结果丢掉。"""
    import os

    import numpy as np

    faiss = pytest.importorskip("faiss")
    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    tmp_dir = _ascii_tmp_dir()
    path = os.path.join(tmp_dir, "close.faiss")

    index = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    index.add_with_ids(
        np.array([[0.3, 0.4]], dtype=np.float32),
        np.array([1], dtype=np.int64),
    )
    faiss.write_index(index, path)

    storage = EmbeddingStorage(2, path)
    assert storage._pending_save is True

    await storage.flush()

    reloaded = EmbeddingStorage(2, path)
    assert reloaded._pending_save is False, "落盘后重新加载不应再次迁移"


@pytest.mark.asyncio
async def test_migration_logs_do_not_leak_local_paths(caplog) -> None:
    """日志不能带出索引绝对路径（含用户名等本地信息）。"""
    import logging
    import os

    import numpy as np

    faiss = pytest.importorskip("faiss")
    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    tmp_dir = _ascii_tmp_dir()
    secret_name = "leakcanary.faiss"
    path = os.path.join(tmp_dir, secret_name)

    index = faiss.IndexIDMap(faiss.IndexFlatL2(2))
    index.add_with_ids(
        np.array([[0.3, 0.4]], dtype=np.float32),
        np.array([1], dtype=np.int64),
    )
    faiss.write_index(index, path)

    with caplog.at_level(logging.DEBUG):
        storage = EmbeddingStorage(2, path)
        assert storage._pending_save is True
        await storage.flush()

    assert secret_name not in caplog.text, "日志里不应出现索引文件名"
    assert tmp_dir not in caplog.text, "日志里不应出现索引所在目录"


def _ascii_tmp_dir() -> str:
    """返回纯 ASCII 的临时目录。

    faiss 的 C++ 层在 Windows 上按 ANSI codepage 打开文件，含中文的用户名路径
    会写失败，因此 Windows 上固定用系统 Temp。
    """
    import os
    import tempfile

    return tempfile.mkdtemp(dir="C:/Windows/Temp" if os.name == "nt" else None)
