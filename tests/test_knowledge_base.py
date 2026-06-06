"""Consolidated knowledge base regression tests."""


# --- Merged from tests/unit/test_document_storage_fts.py ---

import asyncio
import sqlite3

import pytest
from sqlalchemy.exc import IntegrityError

from astrbot.core.db.vec_db.faiss_impl.document_storage import DocumentStorage


@pytest.mark.asyncio
async def test_document_storage_fts_insert_search_and_delete(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    assert storage.fts5_available is True

    await storage.insert_documents_batch(
        doc_ids=["chunk-1", "chunk-2"],
        texts=["AstrBot 知识库召回性能优化", "FAISS 向量检索"],
        metadatas=[
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 1},
        ],
    )

    results = await storage.search_sparse(["知识库"], limit=10)

    assert results is not None
    assert [result["doc_id"] for result in results] == ["chunk-1"]

    await storage.delete_document_by_doc_id("chunk-1")
    results = await storage.search_sparse(["知识库"], limit=10)

    assert results == []

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_rebuilds_existing_documents(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    storage.fts5_available = False
    await storage.insert_document(
        doc_id="legacy-chunk",
        text="legacy 知识库 文本",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )

    storage.fts5_available = True
    storage._fts_index_ready = False

    results = await storage.search_sparse(["知识库"], limit=10)

    assert results is not None
    assert [result["doc_id"] for result in results] == ["legacy-chunk"]

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_search_documents_filters_and_paginates(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    await storage.insert_documents_batch(
        doc_ids=["chunk-1", "chunk-2", "chunk-3"],
        texts=[
            "AstrBot plugin lifecycle",
            "AstrBot provider lifecycle",
            "unrelated content",
        ],
        metadatas=[
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
            {"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 1},
            {"kb_doc_id": "doc-2", "kb_id": "kb-1", "chunk_index": 0},
        ],
    )

    result = await storage.search_documents(
        "lifecycle",
        metadata_filters={"kb_doc_id": "doc-1"},
        offset=1,
        limit=1,
    )

    assert result is not None
    docs, total = result
    assert total == 2
    assert [doc["doc_id"] for doc in docs] == ["chunk-2"]

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_search_sparse_non_positive_limit_falls_back(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    assert await storage.search_sparse(["知识库"], limit=0) is None

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_rebuild_is_serialized(tmp_path, monkeypatch):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    storage.fts5_available = False
    await storage.insert_document(
        doc_id="legacy-chunk",
        text="legacy 知识库 文本",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )

    storage.fts5_available = True
    storage._fts_index_ready = False
    rebuild_count = 0
    original_rebuild = storage._rebuild_fts_index_unlocked

    async def counted_rebuild():
        nonlocal rebuild_count
        rebuild_count += 1
        await asyncio.sleep(0)
        await original_rebuild()

    monkeypatch.setattr(storage, "_rebuild_fts_index_unlocked", counted_rebuild)

    results = await asyncio.gather(
        storage.ensure_fts_index(),
        storage.ensure_fts_index(),
        storage.ensure_fts_index(),
    )

    assert results == [True, True, True]
    assert rebuild_count == 1

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_delete_skips_missing_fts_row(tmp_path):
    storage = DocumentStorage(str(tmp_path / "doc.db"))
    await storage.initialize()

    storage.fts5_available = False
    await storage.insert_document(
        doc_id="legacy-chunk",
        text="legacy 知识库 文本",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )

    storage.fts5_available = True
    await storage.delete_document_by_doc_id("legacy-chunk")

    assert await storage.get_document_by_doc_id("legacy-chunk") is None

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_fts_recovers_from_legacy_non_fts_table(tmp_path):
    db_path = tmp_path / "doc.db"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE documents_fts (rowid INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()

    storage = DocumentStorage(str(db_path))
    await storage.initialize()

    assert storage.fts5_available is True

    await storage.insert_document(
        doc_id="legacy-fix",
        text="legacy fts recovery text",
        metadata={"kb_doc_id": "doc-1", "kb_id": "kb-1", "chunk_index": 0},
    )
    results = await storage.search_sparse(["legacy"], limit=10)

    assert results is not None
    assert [result["doc_id"] for result in results] == ["legacy-fix"]

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_adds_unique_doc_id_index_to_existing_table(tmp_path):
    db_path = tmp_path / "doc.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id VARCHAR NOT NULL,
            text VARCHAR NOT NULL,
            metadata TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
        """,
    )
    conn.execute(
        "INSERT INTO documents (doc_id, text) VALUES ('legacy-chunk', 'legacy text')"
    )
    conn.commit()
    conn.close()

    storage = DocumentStorage(str(db_path))
    await storage.initialize()

    with pytest.raises(IntegrityError):
        await storage.insert_document(
            doc_id="legacy-chunk",
            text="duplicate text",
            metadata={},
        )

    await storage.close()


@pytest.mark.asyncio
async def test_document_storage_adds_missing_kb_id_generated_column(tmp_path):
    db_path = tmp_path / "doc.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id VARCHAR NOT NULL,
            text VARCHAR NOT NULL,
            metadata TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            kb_doc_id TEXT GENERATED ALWAYS AS
                (json_extract(metadata, '$.kb_doc_id')) VIRTUAL
        )
        """,
    )
    conn.execute(
        """
        INSERT INTO documents (doc_id, text, metadata)
        VALUES (
            'legacy-chunk',
            'legacy text',
            '{"kb_doc_id":"doc-1","kb_id":"kb-1","chunk_index":0}'
        )
        """,
    )
    conn.commit()
    conn.close()

    storage = DocumentStorage(str(db_path))
    await storage.initialize()

    docs = await storage.get_documents(metadata_filters={"kb_id": "kb-1"})

    assert [doc["doc_id"] for doc in docs] == ["legacy-chunk"]

    await storage.close()


# --- Merged from tests/unit/test_embedding_storage.py ---

"""测试 FAISS EmbeddingStorage — 向量归一化、余弦相似度、写锁、索引迁移"""

import asyncio
import tempfile
from pathlib import Path

import numpy as np
import pytest

from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage


DIM = 128


def make_random_vector(dim: int = DIM) -> np.ndarray:
    return np.random.default_rng(42).random(dim).astype(np.float32)


def make_random_batch(n: int, dim: int = DIM) -> np.ndarray:
    return np.random.default_rng(42).random((n, dim)).astype(np.float32)


def _normalize_vector(v: np.ndarray) -> None:
    """用 FAISS 归一化单个向量（原地修改）"""
    faiss = pytest.importorskip("faiss")
    faiss.normalize_L2(v.reshape(1, -1))


def assert_unit_norm(vector: np.ndarray) -> None:
    """断言向量已 L2 归一化（模长 ≈ 1.0）"""
    norm = np.linalg.norm(vector)
    assert abs(norm - 1.0) < 1e-5, f"向量未归一化, 模长={norm}"


class TestVectorNormalization:
    """Phase 1A: 验证入库向量归一化 & 余弦相似度"""

    @pytest.mark.asyncio
    async def test_insert_normalizes_vector(self):
        """插入后存储的向量应该已被 L2 归一化（通过自身搜索验证）

        插入时自动归一化向量，用同一向量查询应得到接近 1.0 的内积分。
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            v = make_random_vector()
            await storage.insert(v, id=1)

            # 搜索自身：归一化后内积应 ≈ 1.0
            distances, indices = await storage.search(
                v.copy().reshape(1, -1), k=1
            )
            assert indices[0][0] == 1, f"应返回 id=1，实际={indices[0][0]}"
            assert distances[0][0] > 0.999, (
                f"归一化后自身内积应 ≈ 1.0，实际={distances[0][0]}"
            )

    @pytest.mark.asyncio
    async def test_insert_batch_normalizes_vectors(self):
        """批量插入后所有存储的向量应该已被 L2 归一化（通过搜索验证）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            vectors = make_random_batch(10)
            ids = list(range(10))
            await storage.insert_batch(vectors, ids)

            # 用其中一个向量搜索自身
            q = vectors[0].copy()
            distances, _ = await storage.search(q.reshape(1, -1), k=1)
            assert distances[0][0] > 0.999, (
                f"归一化后自身内积应 ≈ 1.0，实际={distances[0][0]}"
            )

    @pytest.mark.asyncio
    async def test_search_returns_ip_scores(self):
        """IP 搜索对归一化向量应返回内积分数 (≈余弦相似度)"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            # 插入一个向量
            v = np.ones(DIM, dtype=np.float32)
            _normalize_vector(v)
            await storage.insert(v, id=1)

            # 用相同向量搜索自身 — 内积应接近 1.0
            query = v.copy()
            distances, indices = await storage.search(
                query.reshape(1, -1), k=1
            )
            # IP 分数应在 [-1, 1] 范围内
            assert -1.0 - 1e-5 <= distances[0][0] <= 1.0 + 1e-5, (
                f"IP 分数超出 [-1,1] 范围: {distances[0][0]}"
            )
            # 同向量内积应接近 1.0
            assert abs(distances[0][0] - 1.0) < 1e-3, (
                f"自身内积应 ≈ 1.0，实际={distances[0][0]}"
            )

    @pytest.mark.asyncio
    async def test_score_conversion_range(self):
        """分数转换 (scores + 1) / 2 应映射 [-1,1] → [0,1]"""
        from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB

        # 模拟检索后分数转换
        test_cases = [
            (np.array([[1.0]]), 1.0),   # 完美匹配
            (np.array([[0.0]]), 0.5),   # 正交
            (np.array([[-1.0]]), 0.0),  # 完全相反
        ]
        for raw_scores, expected in test_cases:
            converted = (raw_scores[0] + 1.0) / 2.0
            assert abs(converted[0] - expected) < 1e-5, (
                f"转换错误: {raw_scores[0][0]} → {converted[0]}, 期望 {expected}"
            )


class TestWriteLock:
    """Phase 1B: 验证 asyncio.Lock 串行化写入操作"""

    @pytest.mark.asyncio
    async def test_concurrent_inserts_serialized(self):
        """并发插入应被正确序列化，最终 ntotal 正确"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            async def insert_one(offset: int) -> None:
                for i in range(5):
                    v = make_random_vector()
                    await storage.insert(v, id=offset * 5 + i)

            # 4 个协程并发插入
            await asyncio.gather(
                insert_one(0), insert_one(1), insert_one(2), insert_one(3),
            )

            assert storage.index.ntotal == 20, (
                f"并发插入后 ntotal 应为 20, 实际={storage.index.ntotal}"
            )

    @pytest.mark.asyncio
    async def test_search_not_blocked_by_write(self):
        """写入锁不应阻塞搜索（搜索不加锁）"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            # 预先插入一些数据
            for i in range(10):
                v = make_random_vector()
                await storage.insert(v, id=i)

            query = make_random_vector()

            # 同时进行搜索和插入
            search_task = asyncio.create_task(
                storage.search(query.reshape(1, -1), k=5)
            )
            insert_task = asyncio.create_task(
                storage.insert(make_random_vector(), id=100)
            )

            results = await asyncio.gather(search_task, insert_task)
            distances, _ = results[0]
            assert len(distances[0]) == 5


class TestIndexMigration:
    """Phase 1A: 向后兼容 — L2 索引迁移到 IP"""

    @pytest.mark.asyncio
    async def test_migration_l2_to_ip(self):
        """加载旧的 L2 索引时自动迁移为 IP"""
        faiss = pytest.importorskip("faiss")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"

            # 模拟旧版 L2 索引
            old_index = faiss.IndexIDMap(faiss.IndexFlatL2(DIM))
            v = make_random_vector()
            old_index.add_with_ids(v.reshape(1, -1), np.array([1]))
            faiss.write_index(old_index, str(index_path))

            # 加载时应检测 L2 并迁移
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            # 迁移后应为有效索引
            assert storage.index is not None
            assert storage.index.ntotal == 1

            # 确保能正常搜索（search 方法自动归一化查询向量）
            distances, _ = await storage.search(v.copy().reshape(1, -1), k=1)
            assert distances[0][0] > 0.9, (
                f"迁移后搜索自身应有高分, 实际={distances[0][0]}"
            )

    @pytest.mark.asyncio
    async def test_migration_preserves_external_ids(self):
        faiss = pytest.importorskip("faiss")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            old_index = faiss.IndexIDMap(faiss.IndexFlatL2(DIM))
            vectors = make_random_batch(3)
            ids = np.array([10, 42, 99], dtype=np.int64)
            old_index.add_with_ids(vectors, ids)
            faiss.write_index(old_index, str(index_path))

            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            _, result_ids = await storage.search(vectors[1].copy().reshape(1, -1), k=1)
            assert result_ids[0][0] == 42

    @pytest.mark.asyncio
    async def test_migration_creates_backup_before_overwrite(self):
        faiss = pytest.importorskip("faiss")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            old_index = faiss.IndexIDMap(faiss.IndexFlatL2(DIM))
            vectors = make_random_batch(2)
            ids = np.array([7, 8], dtype=np.int64)
            old_index.add_with_ids(vectors, ids)
            faiss.write_index(old_index, str(index_path))

            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            backups = list(index_path.parent.glob("index.faiss.bak.*"))
            assert len(backups) == 1

            migrated_base_index = (
                storage.index.index if hasattr(storage.index, "index") else storage.index
            )
            assert migrated_base_index.metric_type == faiss.METRIC_INNER_PRODUCT

            backup_index = faiss.read_index(str(backups[0]))
            backup_base_index = (
                backup_index.index if hasattr(backup_index, "index") else backup_index
            )
            assert backup_base_index.metric_type == faiss.METRIC_L2
            assert backup_index.ntotal == 2

    @pytest.mark.asyncio
    async def test_no_crash_on_reload_existing_ip_index(self):
        """重新加载已有的 IP 索引不应报错"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"

            # 创建 IP 索引
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))
            v = make_random_vector()
            await storage.insert(v, id=1)  # insert 自动归一化

            # 重新加载
            storage2 = EmbeddingStorage(dimension=DIM, path=str(index_path))
            assert storage2.index is not None
            assert storage2.index.ntotal == 1

    @pytest.mark.asyncio
    async def test_dimension_mismatch_on_load_raises_error(self):
        """加载维度不匹配的索引时应抛出清晰错误"""
        faiss = pytest.importorskip("faiss")

        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            # 创建不同维度的索引
            wrong_dim = 256
            index = faiss.IndexIDMap(faiss.IndexFlatIP(wrong_dim))
            faiss.write_index(index, str(index_path))

            with pytest.raises(ValueError, match="索引维度不匹配"):
                EmbeddingStorage(dimension=DIM, path=str(index_path))


class TestZeroVectorGuard:
    """零向量应抛出明确错误，而非静默产生无意义数据"""

    @pytest.mark.asyncio
    async def test_zero_vector_insert_raises_error(self):
        """插入零向量应抛出 ValueError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            zero_v = np.zeros(DIM, dtype=np.float32)
            with pytest.raises(ValueError, match="零向量"):
                await storage.insert(zero_v, id=1)

    @pytest.mark.asyncio
    async def test_batch_zero_vectors_raises_error(self):
        """批量插入含零向量应抛出 ValueError"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            vectors = make_random_batch(10)
            vectors[0] = np.zeros(DIM, dtype=np.float32)
            ids = list(range(10))
            with pytest.raises(ValueError, match="零向量"):
                await storage.insert_batch(vectors, ids)

    @pytest.mark.asyncio
    async def test_near_zero_vector_inserted_normally(self):
        """接近零但不为零的向量应正常插入并归一化"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(dimension=DIM, path=str(index_path))

            # 非常小但不为零的向量
            tiny_v = np.full(DIM, 1e-8, dtype=np.float32)
            await storage.insert(tiny_v, id=1)
            assert storage.index.ntotal == 1


class TestHNSWIndex:
    """Phase 2A: HNSW 索引创建、持久化和搜索"""

    @pytest.mark.asyncio
    async def test_create_hnsw_index(self):
        """创建 HNSW 索引应成功"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(
                dimension=DIM, path=str(index_path), index_type="hnsw",
            )
            assert storage.index is not None
            assert storage.index.ntotal == 0

    @pytest.mark.asyncio
    async def test_hnsw_insert_and_search(self):
        """HNSW 索引应支持插入和搜索"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(
                dimension=DIM, path=str(index_path), index_type="hnsw",
            )
            # 插入多个向量
            for i in range(10):
                v = make_random_vector()
                await storage.insert(v, id=i)

            assert storage.index.ntotal == 10

            # 搜索
            q = make_random_vector()
            distances, indices = await storage.search(q.reshape(1, -1), k=5)
            assert len(indices[0]) == 5

    @pytest.mark.asyncio
    async def test_hnsw_persistence(self):
        """HNSW 索引应能持久化并重新加载"""
        with tempfile.TemporaryDirectory() as tmpdir:
            index_path = Path(tmpdir) / "index.faiss"
            storage = EmbeddingStorage(
                dimension=DIM, path=str(index_path), index_type="hnsw",
            )
            v = make_random_vector()
            await storage.insert(v, id=1)

            # 重新加载
            storage2 = EmbeddingStorage(
                dimension=DIM, path=str(index_path), index_type="hnsw",
            )
            assert storage2.index is not None
            assert storage2.index.ntotal == 1


# --- Merged from tests/unit/test_faiss_vec_db.py ---

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
@pytest.mark.parametrize(
    ("embeddings", "expected_fragments"),
    [
        ([[0.1, 0.2]], ("期望 2", "实际 1")),
        ([[0.1, 0.2], [0.3]], ()),
    ],
)
async def test_insert_batch_rejects_invalid_embeddings_before_writing_documents(
    embeddings: list[list[float]],
    expected_fragments: tuple[str, ...],
) -> None:
    vec_db = _make_vecdb()
    vec_db.embedding_provider.get_embeddings_batch.return_value = embeddings
    vec_db.embedding_storage.dimension = 2

    with pytest.raises(KnowledgeBaseUploadError) as exc_info:
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1", "chunk-2"],
            metadatas=[{}, {}],
            ids=["doc-1", "doc-2"],
        )

    assert exc_info.value.stage == "embedding"
    assert "向量化失败" in str(exc_info.value)
    for fragment in expected_fragments:
        assert fragment in str(exc_info.value)
    vec_db.document_storage.insert_documents_batch.assert_not_called()
    vec_db.embedding_storage.insert_batch.assert_not_called()


@pytest.mark.asyncio
async def test_insert_batch_cleans_document_rows_when_faiss_insert_fails() -> None:
    vec_db = _make_vecdb()
    vec_db.embedding_provider.get_embeddings_batch.return_value = [
        [0.1] * 128,
        [0.2] * 128,
    ]
    vec_db.document_storage.insert_documents_batch = AsyncMock(return_value=[10, 11])
    vec_db.document_storage.delete_document_by_doc_id = AsyncMock()
    vec_db.embedding_storage.insert_batch = AsyncMock(
        side_effect=RuntimeError("faiss fail"),
    )
    vec_db.embedding_storage.delete = AsyncMock()

    with pytest.raises(RuntimeError, match="faiss fail"):
        await FaissVecDB.insert_batch(
            vec_db,
            contents=["chunk-1", "chunk-2"],
            metadatas=[{}, {}],
            ids=["doc-1", "doc-2"],
        )

    vec_db.embedding_storage.delete.assert_awaited_once_with([10, 11])
    vec_db.document_storage.delete_document_by_doc_id.assert_any_await("doc-1")
    vec_db.document_storage.delete_document_by_doc_id.assert_any_await("doc-2")
    assert vec_db.document_storage.delete_document_by_doc_id.await_count == 2


@pytest.mark.asyncio
async def test_delete_returns_false_when_chunk_is_missing() -> None:
    vec_db = _make_vecdb()
    vec_db.document_storage.get_document_by_doc_id.return_value = None
    vec_db.document_storage.delete_document_by_doc_id = AsyncMock()
    vec_db.embedding_storage.delete = AsyncMock()

    deleted = await FaissVecDB.delete(vec_db, "missing-chunk")

    assert deleted is False
    vec_db.document_storage.delete_document_by_doc_id.assert_not_called()
    vec_db.embedding_storage.delete.assert_not_called()


@pytest.mark.asyncio
async def test_delete_returns_true_when_chunk_exists() -> None:
    vec_db = _make_vecdb()
    vec_db.document_storage.get_document_by_doc_id.return_value = {"id": 42}
    vec_db.document_storage.delete_document_by_doc_id = AsyncMock()
    vec_db.embedding_storage.delete = AsyncMock()

    deleted = await FaissVecDB.delete(vec_db, "chunk-1")

    assert deleted is True
    vec_db.document_storage.delete_document_by_doc_id.assert_awaited_once_with("chunk-1")
    vec_db.embedding_storage.delete.assert_awaited_once_with([42])


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


# --- Merged from tests/unit/test_kb_core_features.py ---

import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.db.vec_db.base import Result
from astrbot.core.knowledge_base.capabilities import (
    DEFAULT_CHUNK_OVERLAP,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_INDEX_TYPE,
    DEFAULT_TOP_K_DENSE,
    DEFAULT_TOP_K_SPARSE,
    DEFAULT_TOP_M_FINAL,
)
from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker
from astrbot.core.knowledge_base.kb_helper import (
    CONSISTENCY_CHECK_PAGE_SIZE,
    CONSISTENCY_REPAIR_TYPES,
    KBHelper,
)
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.knowledge_base.models import KBDocument, KnowledgeBase
from astrbot.core.knowledge_base.parsers import pdf_parser
from astrbot.core.knowledge_base.parsers.pdf_parser import PDFParser
from astrbot.core.knowledge_base.retrieval.manager import (
    RetrievalManager,
    RetrievalResult,
)
from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseResult


def test_knowledge_base_model_defaults_match_capabilities():
    kb = KnowledgeBase(kb_name="defaults", embedding_provider_id="emb-1")

    assert kb.chunk_size == DEFAULT_CHUNK_SIZE
    assert kb.chunk_overlap == DEFAULT_CHUNK_OVERLAP
    assert kb.top_k_dense == DEFAULT_TOP_K_DENSE
    assert kb.top_k_sparse == DEFAULT_TOP_K_SPARSE
    assert kb.top_m_final == DEFAULT_TOP_M_FINAL
    assert kb.index_type == DEFAULT_INDEX_TYPE


@pytest.mark.asyncio
async def test_create_kb_uses_capability_defaults(monkeypatch):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.provider_manager = MagicMock()
    manager.kb_db = MagicMock()
    manager.kb_insts = {}
    manager._kb_name_index = {}

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    manager.kb_db.get_db.return_value = context

    async def initialize(self):
        return None

    monkeypatch.setattr(KBHelper, "initialize", initialize)

    kb_helper = await manager.create_kb(
        kb_name="defaults",
        embedding_provider_id="emb-1",
    )

    created_kb = session.add.call_args.args[0]
    assert created_kb is kb_helper.kb
    assert created_kb.chunk_size == DEFAULT_CHUNK_SIZE
    assert created_kb.chunk_overlap == DEFAULT_CHUNK_OVERLAP
    assert created_kb.top_k_dense == DEFAULT_TOP_K_DENSE
    assert created_kb.top_k_sparse == DEFAULT_TOP_K_SPARSE
    assert created_kb.top_m_final == DEFAULT_TOP_M_FINAL
    assert created_kb.index_type == DEFAULT_INDEX_TYPE


@pytest.mark.asyncio
async def test_markdown_chunk_returns_text_only_compatibility() -> None:
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=0)
    text = "# Guide\nIntro\n\n## Install\nStep one"

    chunks = await chunker.chunk(text)
    chunks_with_metadata = await chunker.chunk_with_metadata(text)

    assert chunks == [chunk.text for chunk in chunks_with_metadata]
    assert [chunk.title_path for chunk in chunks_with_metadata] == [
        ["Guide"],
        ["Guide", "Install"],
    ]
    assert [chunk.section_index for chunk in chunks_with_metadata] == [0, 1]


@pytest.mark.asyncio
async def test_markdown_split_chunks_keep_current_title_path() -> None:
    chunker = MarkdownChunker(chunk_size=80, chunk_overlap=0)
    text = "# Guide\n" + "\n".join(
        f"Long installation paragraph {idx}." for idx in range(12)
    )

    chunks = await chunker.chunk_with_metadata(text)

    assert len(chunks) > 1
    assert all(chunk.title_path == ["Guide"] for chunk in chunks)
    assert all(chunk.section_index == 0 for chunk in chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_skips_front_matter() -> None:
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=0)
    text = "---\noutline: deep\n---\n\n# Guide\nVisible content"

    chunks = await chunker.chunk_with_metadata(text)

    assert len(chunks) == 1
    assert "outline: deep" not in chunks[0].text
    assert chunks[0].text.startswith("# Guide")


@pytest.mark.asyncio
async def test_markdown_chunker_splits_long_tables_with_header() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    table_rows = "\n".join(f"| row-{idx} | value-{idx} |" for idx in range(8))
    text = "# Data\n| Name | Value |\n| --- | --- |\n" + table_rows

    chunks = await chunker.chunk_with_metadata(text)
    table_chunks = [chunk.text for chunk in chunks if "| Name | Value |" in chunk.text]

    assert len(table_chunks) > 1
    assert all("| --- | --- |" in chunk for chunk in table_chunks)
    assert all("| Name | Value |" in chunk for chunk in table_chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_keeps_code_fences_when_splitting() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    code = "\n".join(f"print('line {idx}')" for idx in range(12))
    text = f"# Code\n```python\n{code}\n```"

    chunks = await chunker.chunk_with_metadata(text)
    code_chunks = [chunk.text for chunk in chunks if "```python" in chunk.text]

    assert len(code_chunks) > 1
    assert all(chunk.count("```") == 2 for chunk in code_chunks)
    assert all(chunk.rstrip().endswith("```") for chunk in code_chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_preserves_links_inside_long_paragraphs() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    url = "https://example.com/docs/plugin-development-reference"
    text = (
        "# Links\nRead the official guide at "
        f"[plugin docs]({url}) "
        + "before changing provider settings. " * 5
    )

    chunks = await chunker.chunk_with_metadata(text)
    link_chunks = [chunk.text for chunk in chunks if "plugin docs" in chunk.text]

    assert len(link_chunks) == 1
    assert f"[plugin docs]({url})" in link_chunks[0]
    assert sum(chunk.text.count("[plugin docs](") for chunk in chunks) == 1


@pytest.mark.asyncio
async def test_markdown_chunker_keeps_callout_blocks_together() -> None:
    chunker = MarkdownChunker(chunk_size=200, chunk_overlap=0)
    text = (
        "# Notice\n"
        "> [!WARNING]\n"
        "> Keep the provider settings unchanged during migration.\n"
        "> Rebuild only new documents.\n\n"
        "Normal paragraph after the callout."
    )

    chunks = await chunker.chunk_with_metadata(text)
    callout_chunks = [chunk.text for chunk in chunks if "[!WARNING]" in chunk.text]

    assert len(callout_chunks) == 1
    assert "Rebuild only new documents." in callout_chunks[0]


@pytest.mark.asyncio
async def test_markdown_chunker_keeps_math_block_wrapped_when_splitting() -> None:
    chunker = MarkdownChunker(chunk_size=90, chunk_overlap=0)
    formula_lines = "\n".join(
        rf"a_{{{idx}}} = b_{{{idx}}} + c_{{{idx}}}" for idx in range(10)
    )
    text = f"# Math\n$$\n{formula_lines}\n$$"

    chunks = await chunker.chunk_with_metadata(text)
    math_chunks = [chunk.text for chunk in chunks if "$$" in chunk.text]

    assert len(math_chunks) > 1
    assert all(chunk.startswith("$$") or "\n$$" in chunk for chunk in math_chunks)
    assert all(chunk.rstrip().endswith("$$") for chunk in math_chunks)


@pytest.mark.asyncio
async def test_markdown_chunker_preserves_inline_math_spans() -> None:
    chunker = MarkdownChunker(chunk_size=80, chunk_overlap=0)
    formula = r"$E = mc^2 + \alpha + \beta + \gamma$"
    bracket_formula = r"\(a^2 + b^2 = c^2\)"
    text = (
        "# Math\n"
        "Use "
        f"{formula} and {bracket_formula} "
        + "inside a paragraph with enough surrounding words to split. " * 4
    )

    chunks = await chunker.chunk_with_metadata(text)
    inline_math_chunks = [
        chunk.text for chunk in chunks if "E = mc^2" in chunk.text
    ]
    bracket_math_chunks = [
        chunk.text for chunk in chunks if "a^2 + b^2" in chunk.text
    ]

    assert len(inline_math_chunks) == 1
    assert formula in inline_math_chunks[0]
    assert len(bracket_math_chunks) == 1
    assert bracket_formula in bracket_math_chunks[0]


@pytest.mark.asyncio
async def test_pdf_parser_preserves_page_number_segments(monkeypatch) -> None:
    page_one = MagicMock()
    page_one.extract_text.return_value = "Page one"
    page_two = MagicMock()
    page_two.extract_text.return_value = "Page two"
    reader = MagicMock()
    reader.pages = [page_one, page_two]
    monkeypatch.setattr(pdf_parser, "PdfReader", MagicMock(return_value=reader))

    result = await PDFParser().parse(b"pdf bytes", "guide.pdf")

    assert result.text == "Page one\n\nPage two"
    assert [segment.text for segment in result.text_segments or []] == [
        "Page one",
        "Page two",
    ]
    assert [segment.metadata for segment in result.text_segments or []] == [
        {"page_number": 1},
        {"page_number": 2},
    ]


def _manager() -> KnowledgeBaseManager:
    return KnowledgeBaseManager.__new__(KnowledgeBaseManager)


def test_format_result_source_includes_structural_metadata():
    manager = _manager()
    result = RetrievalResult(
        chunk_id="chunk-1",
        doc_id="doc-1",
        doc_name="guide.md",
        kb_id="kb-1",
        kb_name="Docs",
        content="content",
        score=0.9,
        metadata={
            "chunk_index": 3,
            "section_index": 2,
            "title_path": ["Plugin", "Install"],
            "page_number": 5,
            "parent_chunk_id": "parent-1",
        },
    )

    assert manager._format_result_source(result) == {
        "kb_name": "Docs",
        "document_name": "guide.md",
        "chunk_index": 3,
        "section_index": 2,
        "title_path": ["Plugin", "Install"],
        "page_number": 5,
        "parent_chunk_id": "parent-1",
    }


def test_format_context_includes_source_location_details():
    manager = _manager()
    result = RetrievalResult(
        chunk_id="chunk-1",
        doc_id="doc-1",
        doc_name="guide.md",
        kb_id="kb-1",
        kb_name="Docs",
        content="Install steps",
        score=0.91,
        metadata={
            "chunk_index": 0,
            "section_index": 2,
            "title_path": ["Plugin", "Install"],
            "page_number": 5,
        },
    )

    context = manager._format_context([result])

    assert "Docs / guide.md (Plugin > Install; 第 5 页; 章节 2)" in context
    assert "Install steps" in context


def _dense_result(
    *,
    chunk_id: str,
    doc_id: str,
    kb_id: str = "kb-1",
    chunk_index: int = 0,
    text: str,
    similarity: float,
    metadata: dict | None = None,
) -> Result:
    chunk_metadata = {
        "chunk_index": chunk_index,
        "kb_doc_id": doc_id,
        "kb_id": kb_id,
    }
    if metadata:
        chunk_metadata.update(metadata)
    return Result(
        similarity=similarity,
        data={
            "doc_id": chunk_id,
            "text": text,
            "metadata": json.dumps(chunk_metadata),
        },
    )


def _metadata(doc_id: str, kb_id: str = "kb-1") -> dict:
    return {
        "document": SimpleNamespace(doc_id=doc_id, doc_name=f"{doc_id}.md"),
        "knowledge_base": SimpleNamespace(kb_id=kb_id, kb_name="kb"),
    }


def test_build_kb_options_uses_capability_defaults_for_empty_kb_values():
    manager = RetrievalManager(
        sparse_retriever=SimpleNamespace(),
        rank_fusion=SimpleNamespace(),
        kb_db=SimpleNamespace(),
    )
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=None,
            top_k_sparse=None,
            top_m_final=None,
            rerank_provider_id=None,
        ),
        vec_db=SimpleNamespace(),
    )

    kb_ids, kb_options = manager._build_kb_options(
        ["kb-1"],
        {"kb-1": kb_helper},
    )

    assert kb_ids == ["kb-1"]
    assert kb_options["kb-1"]["top_k_dense"] == DEFAULT_TOP_K_DENSE
    assert kb_options["kb-1"]["top_k_sparse"] == DEFAULT_TOP_K_SPARSE
    assert kb_options["kb-1"]["top_m_final"] == DEFAULT_TOP_M_FINAL


@pytest.mark.asyncio
async def test_retrieve_with_trace_exposes_pipeline_stages_and_ranks():
    dense_results = [
        _dense_result(
            chunk_id="chunk-b",
            doc_id="doc-b",
            chunk_index=1,
            text="dense only content",
            similarity=0.92,
        ),
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            chunk_index=0,
            text="hybrid dense content",
            similarity=0.81,
        ),
    ]
    sparse_results = [
        SparseResult(
            chunk_id="chunk-a",
            chunk_index=0,
            doc_id="doc-a",
            kb_id="kb-1",
            content="hybrid sparse content",
            score=0.0,
            metadata={
                "chunk_index": 0,
                "kb_doc_id": "doc-a",
                "kb_id": "kb-1",
                "title_path": ["Guide", "Install"],
                "page_number": 2,
            },
        ),
        SparseResult(
            chunk_id="chunk-c",
            chunk_index=2,
            doc_id="doc-c",
            kb_id="kb-1",
            content="sparse only content",
            score=4.0,
        ),
    ]

    vec_db = SimpleNamespace(retrieve=AsyncMock(return_value=dense_results))
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=2,
            top_k_sparse=2,
            top_m_final=2,
            rerank_provider_id=None,
        ),
        vec_db=vec_db,
    )
    sparse_retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=sparse_results),
    )
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "doc-a": _metadata("doc-a"),
                "doc-b": _metadata("doc-b"),
                "doc-c": _metadata("doc-c"),
            },
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="hybrid",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=3,
        top_m_final=2,
    )

    assert [result.chunk_id for result in response.results] == [
        "chunk-a",
        "chunk-b",
    ]
    trace = response.trace.to_dict()
    assert set(trace) == {
        "dense",
        "sparse",
        "fusion",
        "dedup",
        "dedup_removed",
        "rerank",
        "final",
    }
    assert [item["chunk_id"] for item in trace["dense"]] == ["chunk-b", "chunk-a"]
    assert [item["chunk_id"] for item in trace["sparse"]] == ["chunk-a", "chunk-c"]

    hybrid_trace = trace["fusion"][0]
    assert hybrid_trace["chunk_id"] == "chunk-a"
    assert hybrid_trace["dense_rank"] == 2
    assert hybrid_trace["sparse_rank"] == 1
    assert hybrid_trace["dense_score"] == 0.81
    assert hybrid_trace["sparse_score"] == 0.0
    assert hybrid_trace["rrf_score"] == hybrid_trace["score"]
    assert hybrid_trace["doc_name"] == "doc-a.md"
    assert hybrid_trace["score"] > trace["fusion"][1]["score"]
    assert hybrid_trace["title_path"] == ["Guide", "Install"]
    assert hybrid_trace["page_number"] == 2

    assert [item["chunk_id"] for item in trace["dedup"]] == [
        "chunk-a",
        "chunk-b",
        "chunk-c",
    ]
    assert trace["dedup_removed"] == []
    assert trace["rerank"] == []
    assert [item["chunk_id"] for item in trace["final"]] == ["chunk-a", "chunk-b"]
    assert trace["final"][0]["title_path"] == ["Guide", "Install"]
    assert trace["final"][0]["page_number"] == 2
    assert trace["final"][0]["dense_score"] == 0.81
    assert trace["final"][0]["sparse_score"] == 0.0
    assert trace["final"][0]["rrf_score"] == trace["final"][0]["score"]


@pytest.mark.asyncio
async def test_retrieve_with_trace_deduplicates_near_identical_contexts():
    dense_results = [
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            chunk_index=0,
            text="Install AstrBot plugin with pip and restart the service.",
            similarity=0.95,
        ),
        _dense_result(
            chunk_id="chunk-b",
            doc_id="doc-b",
            chunk_index=1,
            text="Install AstrBot plugin with pip and restart the service.",
            similarity=0.93,
        ),
        _dense_result(
            chunk_id="chunk-c",
            doc_id="doc-c",
            chunk_index=2,
            text="Configure the provider in the dashboard settings.",
            similarity=0.75,
        ),
    ]

    vec_db = SimpleNamespace(retrieve=AsyncMock(return_value=dense_results))
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=3,
            top_k_sparse=1,
            top_m_final=3,
            rerank_provider_id=None,
        ),
        vec_db=vec_db,
    )
    sparse_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "doc-a": _metadata("doc-a"),
                "doc-b": _metadata("doc-b"),
                "doc-c": _metadata("doc-c"),
            },
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="install plugin",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=3,
        top_m_final=3,
    )

    trace = response.trace.to_dict()
    assert [item["chunk_id"] for item in trace["fusion"]] == [
        "chunk-a",
        "chunk-b",
        "chunk-c",
    ]
    assert [item["chunk_id"] for item in trace["dedup"]] == [
        "chunk-a",
        "chunk-c",
    ]
    assert [item["chunk_id"] for item in trace["dedup_removed"]] == ["chunk-b"]
    assert trace["dedup_removed"][0]["duplicate_of_chunk_id"] == "chunk-a"
    assert trace["dedup_removed"][0]["duplicate_of_doc_id"] == "doc-a"
    assert trace["dedup_removed"][0]["dedup_similarity"] == 1.0
    assert [result.chunk_id for result in response.results] == [
        "chunk-a",
        "chunk-c",
    ]


@pytest.mark.asyncio
async def test_retrieve_with_trace_applies_temporary_retrieval_overrides():
    dense_results = [
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            text="temporary override content",
            similarity=0.9,
        ),
    ]
    vec_db = SimpleNamespace(retrieve=AsyncMock(return_value=dense_results))
    kb = SimpleNamespace(
        top_k_dense=10,
        top_k_sparse=10,
        top_m_final=5,
        rerank_provider_id="rerank-1",
    )
    kb_helper = SimpleNamespace(kb=kb, vec_db=vec_db)
    sparse_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={"doc-a": _metadata("doc-a")},
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="override",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=3,
        top_m_final=2,
        retrieval_overrides={
            "top_k_dense": 2,
            "top_k_sparse": 3,
            "top_m_final": 2,
            "rerank_provider_id": None,
        },
    )

    assert [result.chunk_id for result in response.results] == ["chunk-a"]
    vec_db.retrieve.assert_awaited_once()
    assert vec_db.retrieve.await_args.kwargs["k"] == 2
    assert vec_db.retrieve.await_args.kwargs["fetch_k"] == 4
    sparse_retriever.retrieve.assert_awaited_once()
    assert (
        sparse_retriever.retrieve.await_args.kwargs["kb_options"]["kb-1"][
            "top_k_sparse"
        ]
        == 3
    )
    assert (
        sparse_retriever.retrieve.await_args.kwargs["kb_options"]["kb-1"][
            "rerank_provider_id"
        ]
        is None
    )
    assert kb.top_k_dense == 10
    assert kb.top_k_sparse == 10
    assert kb.rerank_provider_id == "rerank-1"


@pytest.mark.asyncio
async def test_retrieve_with_trace_preserves_rerank_and_rrf_scores():
    dense_results = [
        _dense_result(
            chunk_id="chunk-a",
            doc_id="doc-a",
            text="alpha content",
            similarity=0.9,
        ),
        _dense_result(
            chunk_id="chunk-b",
            doc_id="doc-b",
            text="beta content",
            similarity=0.8,
        ),
    ]

    class FakeRerankProvider:
        def meta(self):
            return SimpleNamespace(id="rerank-1")

        async def rerank(self, *, query, documents):
            assert query == "rerank"
            assert documents == ["alpha content", "beta content"]
            return [
                SimpleNamespace(index=1, relevance_score=0.95),
                SimpleNamespace(index=0, relevance_score=0.4),
            ]

    vec_db = SimpleNamespace(
        retrieve=AsyncMock(return_value=dense_results),
        rerank_provider=FakeRerankProvider(),
    )
    kb_helper = SimpleNamespace(
        kb=SimpleNamespace(
            top_k_dense=2,
            top_k_sparse=0,
            top_m_final=2,
            rerank_provider_id="rerank-1",
        ),
        vec_db=vec_db,
    )
    sparse_retriever = SimpleNamespace(retrieve=AsyncMock(return_value=[]))
    kb_db = SimpleNamespace(
        get_documents_with_metadata_batch=AsyncMock(
            return_value={
                "doc-a": _metadata("doc-a"),
                "doc-b": _metadata("doc-b"),
            },
        ),
    )
    manager = RetrievalManager(
        sparse_retriever=sparse_retriever,
        rank_fusion=RankFusion(kb_db),
        kb_db=kb_db,
    )

    response = await manager.retrieve_with_trace(
        query="rerank",
        kb_ids=["kb-1"],
        kb_id_helper_map={"kb-1": kb_helper},
        top_k_fusion=2,
        top_m_final=2,
    )

    trace = response.trace.to_dict()
    assert [result.chunk_id for result in response.results] == [
        "chunk-b",
        "chunk-a",
    ]
    assert [item["chunk_id"] for item in trace["rerank"]] == [
        "chunk-b",
        "chunk-a",
    ]
    assert trace["final"][0]["chunk_id"] == "chunk-b"
    assert trace["final"][0]["score"] == 0.95
    assert trace["final"][0]["rerank_score"] == 0.95
    assert trace["final"][0]["rrf_score"] != trace["final"][0]["rerank_score"]
    assert trace["final"][0]["dense_score"] == 0.8


def _build_doc(
    *,
    doc_id: str,
    file_path: str,
    chunk_count: int,
    status: str = "ready",
    source_type: str = "file",
) -> KBDocument:
    return KBDocument(
        doc_id=doc_id,
        kb_id="kb-1",
        doc_name=f"{doc_id}.md",
        file_type="md",
        file_size=1,
        file_path=file_path,
        source_type=source_type,
        status=status,
        chunk_count=chunk_count,
    )


@pytest.mark.asyncio
async def test_check_consistency_reports_metadata_file_and_vector_issues(tmp_path):
    files_root = tmp_path / "files" / "kb-1"
    source_path = files_root / "doc-ok" / "ok.md"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("hello", encoding="utf-8")
    outside_source_path = tmp_path / "outside.md"
    outside_source_path.write_text("outside", encoding="utf-8")

    docs = [
        _build_doc(
            doc_id="doc-ok",
            file_path=str(source_path),
            chunk_count=2,
        ),
        _build_doc(
            doc_id="doc-missing",
            file_path=str(files_root / "doc-missing" / "missing.md"),
            chunk_count=1,
        ),
        _build_doc(
            doc_id="doc-unsafe",
            file_path=str(outside_source_path),
            chunk_count=0,
        ),
    ]
    chunks = [
        {
            "id": 1,
            "doc_id": "chunk-ok-1",
            "text": "hello",
            "metadata": json.dumps(
                {"kb_id": "kb-1", "kb_doc_id": "doc-ok", "chunk_index": 0},
            ),
        },
        {
            "id": 2,
            "doc_id": "chunk-orphan",
            "text": "orphan",
            "metadata": json.dumps(
                {"kb_id": "kb-1", "kb_doc_id": "doc-gone", "chunk_index": 0},
            ),
        },
        {
            "id": 3,
            "doc_id": "chunk-invalid",
            "text": "bad",
            "metadata": "{not-json",
        },
    ]

    storage = MagicMock()
    storage.get_documents = AsyncMock(return_value=chunks)
    vec_db = MagicMock()
    vec_db.document_storage = storage

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.kb_files_dir = files_root
    helper.vec_db = vec_db
    helper.list_documents = AsyncMock(return_value=docs)

    report = await KBHelper.check_consistency(helper)

    assert report["kb_id"] == "kb-1"
    assert report["summary"]["sqlite_document_count"] == 3
    assert report["summary"]["document_chunk_count"] == 3
    assert report["summary"]["indexed_chunk_count"] == 3
    assert report["summary"]["source_file_count"] == 1
    assert report["summary"]["missing_vectors"] == 1
    assert report["summary"]["orphan_vectors"] == 1
    assert report["summary"]["missing_source_files"] == 1
    assert report["summary"]["chunk_count_mismatches"] == 2
    assert report["summary"]["invalid_vector_metadata"] == 1
    assert report["summary"]["unsafe_source_paths"] == 1
    assert report["summary"]["healthy"] is False
    assert report["issues"]["missing_vectors"][0]["doc_id"] == "doc-missing"
    assert report["issues"]["orphan_vectors"][0]["doc_id"] == "doc-gone"
    assert report["issues"]["unsafe_source_paths"][0]["doc_id"] == "doc-unsafe"
    assert (
        report["issues"]["invalid_vector_metadata"][0]["metadata_error"]
        == "invalid metadata JSON"
    )

    helper.list_documents.assert_awaited_once_with(offset=0, limit=1000)
    storage.get_documents.assert_awaited_once_with(
        metadata_filters={"kb_id": "kb-1"},
        offset=0,
        limit=1000,
    )


@pytest.mark.asyncio
async def test_check_consistency_reads_all_document_and_chunk_pages(tmp_path):
    docs = [
        _build_doc(
            doc_id=f"doc-{index}",
            file_path="",
            chunk_count=0,
        )
        for index in range(CONSISTENCY_CHECK_PAGE_SIZE + 1)
    ]
    chunks = [
        {
            "id": index,
            "doc_id": f"chunk-{index}",
            "text": "hello",
            "metadata": json.dumps(
                {
                    "kb_id": "kb-1",
                    "kb_doc_id": f"doc-{index}",
                    "chunk_index": 0,
                },
            ),
        }
        for index in range(CONSISTENCY_CHECK_PAGE_SIZE + 1)
    ]

    async def list_documents(offset=0, limit=100):
        return docs[offset : offset + limit]

    async def list_chunks(metadata_filters=None, offset=0, limit=100):
        return chunks[offset : offset + limit]

    storage = MagicMock()
    storage.get_documents = AsyncMock(side_effect=list_chunks)
    vec_db = MagicMock()
    vec_db.document_storage = storage

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.kb_files_dir = tmp_path
    helper.vec_db = vec_db
    helper.list_documents = AsyncMock(side_effect=list_documents)

    report = await KBHelper.check_consistency(helper)

    assert report["summary"]["sqlite_document_count"] == len(docs)
    assert report["summary"]["indexed_chunk_count"] == len(chunks)
    assert helper.list_documents.await_args_list[0].kwargs == {
        "offset": 0,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }
    assert helper.list_documents.await_args_list[1].kwargs == {
        "offset": CONSISTENCY_CHECK_PAGE_SIZE,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }
    assert storage.get_documents.await_args_list[0].kwargs == {
        "metadata_filters": {"kb_id": "kb-1"},
        "offset": 0,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }
    assert storage.get_documents.await_args_list[1].kwargs == {
        "metadata_filters": {"kb_id": "kb-1"},
        "offset": CONSISTENCY_CHECK_PAGE_SIZE,
        "limit": CONSISTENCY_CHECK_PAGE_SIZE,
    }


@pytest.mark.asyncio
async def test_check_consistency_reports_unsupported_storage_backend():
    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.vec_db = MagicMock()
    helper.list_documents = AsyncMock(return_value=[])

    with pytest.raises(ValueError, match="不支持一致性检查"):
        await KBHelper.check_consistency(helper)


@pytest.mark.asyncio
async def test_repair_consistency_repairs_safe_issues_and_skips_rebuild_cases():
    pre_report = {
        "kb_id": "kb-1",
        "kb_name": "kb",
        "checked_at": "2026-06-01T00:00:00+00:00",
        "summary": {"healthy": False},
        "issues": {
            "orphan_vectors": [
                {"doc_id": "doc-gone", "chunk_id": "chunk-1"},
                {"doc_id": "doc-gone", "chunk_id": "chunk-2"},
            ],
            "chunk_count_mismatches": [
                {
                    "doc_id": "doc-extra-indexed",
                    "expected_chunk_count": 1,
                    "actual_chunk_count": 2,
                },
                {
                    "doc_id": "doc-missing-index",
                    "expected_chunk_count": 3,
                    "actual_chunk_count": 1,
                },
            ],
            "missing_vectors": [{"doc_id": "doc-missing-index"}],
            "missing_source_files": [{"doc_id": "doc-missing-file"}],
            "invalid_vector_metadata": [{"chunk_id": "chunk-invalid"}],
            "unsafe_source_paths": [{"doc_id": "doc-unsafe"}],
        },
    }
    post_report = copy.deepcopy(pre_report)
    post_report["summary"] = {"healthy": True}
    post_report["issues"] = {
        "orphan_vectors": [],
        "chunk_count_mismatches": [],
        "missing_vectors": [],
        "missing_source_files": [],
        "invalid_vector_metadata": [],
        "unsafe_source_paths": [],
    }

    vec_db = MagicMock()
    vec_db.delete_documents = AsyncMock()
    kb_db = MagicMock()
    kb_db.update_kb_stats = AsyncMock()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.vec_db = vec_db
    helper.kb_db = kb_db
    helper.check_consistency = AsyncMock(side_effect=[pre_report, post_report])
    helper.refresh_document = AsyncMock()
    helper.refresh_kb = AsyncMock()

    result = await KBHelper.repair_consistency(helper)

    assert result["repair_types"] == sorted(CONSISTENCY_REPAIR_TYPES)
    assert result["summary"] == {
        "repaired_count": 2,
        "skipped_count": 5,
        "failed_count": 0,
        "healthy_after_repair": True,
    }
    vec_db.delete_documents.assert_awaited_once_with(
        metadata_filters={"kb_id": "kb-1", "kb_doc_id": "doc-gone"},
    )
    helper.refresh_document.assert_awaited_once_with("doc-extra-indexed")
    kb_db.update_kb_stats.assert_awaited_once_with(
        kb_id="kb-1",
        vec_db=vec_db,
    )
    helper.refresh_kb.assert_awaited_once_with()
    assert result["actions"]["repaired"][0]["type"] == "orphan_vectors"
    assert result["actions"]["repaired"][0]["count"] == 2
    assert any(
        action["type"] == "chunk_count_mismatches"
        and action["reason"] == "missing_vectors_require_rebuild"
        for action in result["actions"]["skipped"]
    )
    assert any(
        action["type"] == "missing_vectors"
        and action["reason"] == "document_rebuild_required"
        for action in result["actions"]["skipped"]
    )


@pytest.mark.asyncio
async def test_repair_consistency_only_runs_selected_repair_types():
    pre_report = {
        "kb_id": "kb-1",
        "kb_name": "kb",
        "checked_at": "2026-06-01T00:00:00+00:00",
        "summary": {"healthy": False},
        "issues": {
            "orphan_vectors": [{"doc_id": "doc-gone", "chunk_id": "chunk-1"}],
            "chunk_count_mismatches": [
                {
                    "doc_id": "doc-extra-indexed",
                    "expected_chunk_count": 1,
                    "actual_chunk_count": 2,
                },
            ],
            "missing_vectors": [],
            "missing_source_files": [],
            "invalid_vector_metadata": [],
            "unsafe_source_paths": [],
        },
    }
    post_report = copy.deepcopy(pre_report)

    vec_db = MagicMock()
    vec_db.delete_documents = AsyncMock()
    kb_db = MagicMock()
    kb_db.update_kb_stats = AsyncMock()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    helper.vec_db = vec_db
    helper.kb_db = kb_db
    helper.check_consistency = AsyncMock(side_effect=[pre_report, post_report])
    helper.refresh_document = AsyncMock()
    helper.refresh_kb = AsyncMock()

    result = await KBHelper.repair_consistency(
        helper,
        repair_types=["chunk_count_mismatches"],
    )

    assert result["repair_types"] == ["chunk_count_mismatches"]
    vec_db.delete_documents.assert_not_awaited()
    helper.refresh_document.assert_awaited_once_with("doc-extra-indexed")


def test_normalize_consistency_repair_types_rejects_unknown_types():
    with pytest.raises(ValueError, match="unsupported"):
        KBHelper._normalize_consistency_repair_types(["unsupported"])


# --- Merged from tests/unit/test_kb_manager_delete.py ---

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_delete_kb_removes_related_document_and_media_metadata(tmp_path):
    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
    from astrbot.core.knowledge_base.models import (
        KBDocument,
        KBMedia,
        KnowledgeBase,
    )

    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    kb = KnowledgeBase(
        kb_id="kb-delete",
        kb_name="delete-me",
        embedding_provider_id="emb-1",
    )
    other_kb = KnowledgeBase(
        kb_id="kb-keep",
        kb_name="keep-me",
        embedding_provider_id="emb-1",
    )
    doc = KBDocument(
        doc_id="doc-delete",
        kb_id="kb-delete",
        doc_name="delete.txt",
        file_type="txt",
        file_size=1,
        file_path="",
    )
    other_doc = KBDocument(
        doc_id="doc-keep",
        kb_id="kb-keep",
        doc_name="keep.txt",
        file_type="txt",
        file_size=1,
        file_path="",
    )
    media = KBMedia(
        media_id="media-delete",
        doc_id="doc-delete",
        kb_id="kb-delete",
        media_type="image",
        file_name="delete.png",
        file_path="",
        file_size=1,
        mime_type="image/png",
        created_at=datetime.now(timezone.utc),
    )
    other_media = KBMedia(
        media_id="media-keep",
        doc_id="doc-keep",
        kb_id="kb-keep",
        media_type="image",
        file_name="keep.png",
        file_path="",
        file_size=1,
        mime_type="image/png",
        created_at=datetime.now(timezone.utc),
    )
    async with kb_db.get_db() as session:
        session.add(kb)
        session.add(other_kb)
        session.add(doc)
        session.add(other_doc)
        session.add(media)
        session.add(other_media)
        await session.commit()

    helper = KBHelper.__new__(KBHelper)
    helper.kb = kb
    helper.delete_vec_db = AsyncMock()

    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.kb_db = kb_db
    manager.kb_insts = {"kb-delete": helper}

    deleted = await manager.delete_kb("kb-delete")

    assert deleted is True
    helper.delete_vec_db.assert_awaited_once()
    assert await kb_db.get_kb_by_id("kb-delete") is None
    assert await kb_db.get_document_by_id("doc-delete") is None
    assert await kb_db.get_media_by_id("media-delete") is None
    assert await kb_db.get_kb_by_id("kb-keep") is not None
    assert await kb_db.get_document_by_id("doc-keep") is not None
    assert await kb_db.get_media_by_id("media-keep") is not None
    assert await manager.get_kb_by_name("delete-me") is None

    await kb_db.close()


@pytest.mark.asyncio
async def test_create_kb_cleans_created_directory_when_initialize_fails(
    tmp_path,
    monkeypatch,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    manager = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    manager.provider_manager = MagicMock()
    manager.kb_db = MagicMock()
    manager.kb_insts = {}

    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=session)
    context.__aexit__ = AsyncMock(return_value=False)
    manager.kb_db.get_db.return_value = context

    async def fail_initialize(self):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(KBHelper, "initialize", fail_initialize)
    monkeypatch.setattr("astrbot.core.knowledge_base.kb_mgr.FILES_PATH", str(tmp_path))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        await manager.create_kb(
            kb_name="broken",
            embedding_provider_id="emb-1",
        )

    assert list(tmp_path.iterdir()) == []


# --- Merged from tests/unit/test_kb_manager_resilience.py ---

"""
Unit tests for knowledge base manager resilience behavior.

Tests the following scenarios:
1. update_kb preserves old instance when re-initialization fails
2. update_kb switches instance only after new instance initializes successfully
3. _ensure_vec_db clears stale init_error after successful initialization

These tests use lazy imports and mocks to avoid circular import issues
in the astrbot core module chain.
"""

import sys
import types
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture
def stub_provider_manager_module():
    """Stub provider manager module to avoid circular imports in unit tests."""
    original_module = sys.modules.get("astrbot.core.provider.manager")
    stub_module = types.ModuleType("astrbot.core.provider.manager")

    class ProviderManager: ...

    setattr(stub_module, "ProviderManager", ProviderManager)
    sys.modules["astrbot.core.provider.manager"] = stub_module

    try:
        yield
    finally:
        if original_module is not None:
            sys.modules["astrbot.core.provider.manager"] = original_module
        else:
            sys.modules.pop("astrbot.core.provider.manager", None)


@pytest.fixture
def mock_provider_manager():
    """Create a mock ProviderManager."""
    manager = MagicMock()
    manager.get_provider_by_id = AsyncMock()
    manager.acm = MagicMock()
    manager.acm.default_conf = {}
    return manager


@pytest.fixture
def mock_kb_db():
    """Create a mock KBSQLiteDatabase."""
    db = MagicMock()
    db.get_db = MagicMock()
    db.list_kbs = AsyncMock(return_value=[])
    db.get_kb_by_id = AsyncMock()
    return db


@pytest.fixture
def mock_knowledge_base():
    """Create a mock KnowledgeBase instance."""
    # Use lazy import to avoid circular import
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test_kb",
        description="Test knowledge base",
        emoji="📚",
        embedding_provider_id="test-embedding-provider",
        rerank_provider_id=None,
        chunk_size=512,
        chunk_overlap=50,
        top_k_dense=50,
        top_k_sparse=50,
        top_m_final=5,
    )
    return kb


@pytest.fixture
def mock_embedding_provider():
    """Create a mock EmbeddingProvider."""
    provider = MagicMock()
    provider.get_embeddings_batch = AsyncMock(return_value=[[0.1, 0.2, 0.3]])
    return provider


@pytest.mark.asyncio
async def test_load_kbs_does_not_limit_database_records(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {}
    kb_mgr._kb_name_index = {}

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock):
        await kb_mgr.load_kbs()

    mock_kb_db.list_kbs.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_kb_invalid_options_do_not_mutate_existing_kb(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.init_error = None

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        with pytest.raises(ValueError, match="chunk_overlap"):
            await kb_mgr.update_kb(
                kb_id=mock_knowledge_base.kb_id,
                chunk_size=100,
                chunk_overlap=100,
            )

    mock_init.assert_not_awaited()
    assert mock_knowledge_base.chunk_size == 512
    assert mock_knowledge_base.chunk_overlap == 50


@pytest.mark.asyncio
async def test_update_kb_preserves_old_instance_when_reinit_fails(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """
    Test that update_kb preserves the old KBHelper instance when
    re-initialization fails, ensuring the knowledge base remains available.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    # Setup: create an existing KBHelper with working vec_db
    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider

    # Create KBHelper using __new__ to avoid __init__ side effects
    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.prov_mgr = mock_provider_manager
    old_helper.kb_db = mock_kb_db
    old_helper.kb_root_dir = "/tmp/test_kb"
    old_helper.chunker = MagicMock()
    old_helper.init_error = None
    old_helper.vec_db = MagicMock()  # Simulate existing working vec_db
    old_helper.terminate = AsyncMock()

    # Create KBManager and inject the existing helper
    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}
    kb_mgr.retrieval_manager = MagicMock()

    # Mock KBHelper creation to simulate initialization failure
    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        # First call (for new_helper) should fail
        mock_init.side_effect = Exception("Embedding provider unavailable")

        # Execute update_kb with a different embedding provider
        result = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="updated_kb",
            embedding_provider_id="new-embedding-provider",
        )

        # Verify: the old helper should be returned, not a new one
        assert result is not None
        assert result is old_helper
        assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is old_helper

        # Verify: old helper's vec_db should still be available
        assert hasattr(result, "vec_db")
        assert result.vec_db is not None

        # Verify: failure does not replace the existing helper state
        assert result.init_error is None
        assert result.kb.kb_name == "test_kb"
        assert result.kb.embedding_provider_id == "test-embedding-provider"


@pytest.mark.asyncio
async def test_update_kb_switches_instance_only_after_new_reinit_success(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """
    Test that update_kb only switches to the new KBHelper instance
    after the new instance successfully initializes.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    # Setup: create an existing KBHelper
    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider

    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.prov_mgr = mock_provider_manager
    old_helper.kb_db = mock_kb_db
    old_helper.kb_root_dir = "/tmp/test_kb"
    old_helper.chunker = MagicMock()
    old_helper.init_error = None
    old_helper.vec_db = MagicMock()
    old_helper.terminate = AsyncMock()

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}
    kb_mgr.retrieval_manager = MagicMock()

    # Mock session context for database operations
    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_context.__aexit__ = AsyncMock()
    mock_kb_db.get_db.return_value = mock_db_context

    # Mock KBHelper.initialize to succeed
    with patch.object(KBHelper, "initialize", new_callable=AsyncMock) as mock_init:
        mock_init.return_value = None

        # Execute update_kb
        result = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="updated_kb",
            embedding_provider_id="new-embedding-provider",
        )

        # Verify: a new helper should be returned
        assert result is not None
        assert result is not old_helper
        assert result.init_error is None
        assert kb_mgr.kb_insts[mock_knowledge_base.kb_id] is result

        # Verify: old helper should be terminated
        old_helper.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_get_kb_waits_for_update_instance_swap(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.init_error = None
    old_helper.terminate = AsyncMock()

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}

    commit_started = asyncio.Event()
    release_commit = asyncio.Event()

    async def commit():
        commit_started.set()
        await release_commit.wait()

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock(side_effect=commit)
    mock_session.refresh = AsyncMock()
    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_context.__aexit__ = AsyncMock(return_value=False)
    mock_kb_db.get_db.return_value = mock_db_context

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock):
        update_task = asyncio.create_task(
            kb_mgr.update_kb(
                kb_id=mock_knowledge_base.kb_id,
                kb_name="updated_kb",
            )
        )
        await commit_started.wait()

        get_task = asyncio.create_task(kb_mgr.get_kb(mock_knowledge_base.kb_id))
        await asyncio.sleep(0)
        assert not get_task.done()

        release_commit.set()
        updated_helper = await update_task
        observed_helper = await get_task

    assert updated_helper is observed_helper
    assert observed_helper is kb_mgr.kb_insts[mock_knowledge_base.kb_id]
    assert observed_helper is not old_helper


@pytest.mark.asyncio
async def test_get_kb_does_not_retry_failed_helper_during_cooldown(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import (
        INIT_RETRY_COOLDOWN_SECONDS,
        KnowledgeBaseManager,
    )

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.init_error = "provider unavailable"
    helper.init_retry_count = 0
    helper.last_init_retry_at = 100.0
    helper.initialize = AsyncMock()

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: helper}

    with patch(
        "astrbot.core.knowledge_base.kb_mgr.time.monotonic",
        return_value=100.0 + INIT_RETRY_COOLDOWN_SECONDS - 1,
    ):
        result = await kb_mgr.get_kb(mock_knowledge_base.kb_id)

    assert result is helper
    helper.initialize.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_vec_db_clears_stale_init_error(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
    mock_embedding_provider,
):
    """
    Test that _ensure_vec_db clears the init_error attribute
    after successful initialization, removing stale error state.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    # Setup: create KBHelper with stale init_error
    mock_provider_manager.get_provider_by_id.return_value = mock_embedding_provider

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.prov_mgr = mock_provider_manager
    helper.kb_db = mock_kb_db
    helper.kb_root_dir = "/tmp/test_kb"
    helper.chunker = MagicMock()
    helper.init_error = "Previous initialization failed"
    helper.kb_dir = Path("/tmp/test_kb") / mock_knowledge_base.kb_id
    helper.kb_medias_dir = helper.kb_dir / "medias" / mock_knowledge_base.kb_id
    helper.kb_files_dir = helper.kb_dir / "files" / mock_knowledge_base.kb_id

    # Mock FaissVecDB initialization
    mock_vec_db = MagicMock()
    mock_vec_db.initialize = AsyncMock()
    mock_vec_db.close = AsyncMock()

    with patch(
        "astrbot.core.db.vec_db.faiss_impl.vec_db.FaissVecDB",
        return_value=mock_vec_db,
    ):
        # Execute _ensure_vec_db
        await helper._ensure_vec_db()

        # Verify: init_error should be cleared
        assert helper.init_error is None
        assert helper.vec_db is mock_vec_db


@pytest.mark.asyncio
async def test_update_kb_omitted_rerank_provider_preserves_existing_value(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mock_knowledge_base.rerank_provider_id = "rerank-1"
    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.init_error = None
    old_helper.terminate = AsyncMock()

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_context.__aexit__ = AsyncMock()
    mock_kb_db.get_db.return_value = mock_db_context

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock):
        result = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="updated_kb",
        )

    assert result is not None
    assert result.kb.rerank_provider_id == "rerank-1"


@pytest.mark.asyncio
async def test_update_kb_explicit_none_clears_rerank_provider(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager

    mock_knowledge_base.rerank_provider_id = "rerank-1"
    old_helper = KBHelper.__new__(KBHelper)
    old_helper.kb = mock_knowledge_base
    old_helper.init_error = None
    old_helper.terminate = AsyncMock()

    kb_mgr = KnowledgeBaseManager.__new__(KnowledgeBaseManager)
    kb_mgr.provider_manager = mock_provider_manager
    kb_mgr.kb_db = mock_kb_db
    kb_mgr.kb_insts = {mock_knowledge_base.kb_id: old_helper}

    mock_session = MagicMock()
    mock_session.add = MagicMock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_db_context = MagicMock()
    mock_db_context.__aenter__ = AsyncMock(return_value=mock_session)
    mock_db_context.__aexit__ = AsyncMock()
    mock_kb_db.get_db.return_value = mock_db_context

    with patch.object(KBHelper, "initialize", new_callable=AsyncMock):
        result = await kb_mgr.update_kb(
            kb_id=mock_knowledge_base.kb_id,
            kb_name="updated_kb",
            rerank_provider_id=None,
        )

    assert result is not None
    assert result.kb.rerank_provider_id is None


@pytest.mark.asyncio
async def test_ensure_vec_db_sets_init_error_on_failure(
    stub_provider_manager_module,
    mock_provider_manager,
    mock_kb_db,
    mock_knowledge_base,
):
    """
    Test that _ensure_vec_db does NOT clear init_error when
    initialization fails, preserving the error state.
    """
    # Lazy import to avoid circular import
    from astrbot.core.knowledge_base.kb_helper import KBHelper

    # Setup: provider unavailable
    mock_provider_manager.get_provider_by_id.return_value = None

    helper = KBHelper.__new__(KBHelper)
    helper.kb = mock_knowledge_base
    helper.prov_mgr = mock_provider_manager
    helper.kb_db = mock_kb_db
    helper.kb_root_dir = "/tmp/test_kb"
    helper.chunker = MagicMock()
    helper.init_error = "Previous initialization failed"
    helper.kb_dir = Path("/tmp/test_kb") / mock_knowledge_base.kb_id
    helper.kb_medias_dir = helper.kb_dir / "medias" / mock_knowledge_base.kb_id
    helper.kb_files_dir = helper.kb_dir / "files" / mock_knowledge_base.kb_id

    # Execute _ensure_vec_db - should raise exception
    try:
        await helper._ensure_vec_db()
        pytest.fail("Expected exception but none was raised")
    except ValueError as e:
        # Verify: exception should be raised
        assert "无法找到" in str(e) or "未配置" in str(e)

        # Verify: init_error should NOT be cleared (still has previous error)
        # Note: _ensure_vec_db doesn't set init_error; that's done by the caller
        assert helper.init_error is not None


# --- Merged from tests/unit/test_kb_rate_limiter.py ---

import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.knowledge_base import kb_helper
from astrbot.core.knowledge_base.kb_helper import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_serializes_concurrent_entries(monkeypatch):
    real_sleep = asyncio.sleep
    monotonic_values = iter([0.0, 0.0, 0.0, 0.0])
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(
        kb_helper,
        "time",
        SimpleNamespace(monotonic=lambda: next(monotonic_values)),
    )
    monkeypatch.setattr(
        kb_helper,
        "asyncio",
        SimpleNamespace(Lock=asyncio.Lock, sleep=fake_sleep),
    )

    limiter = RateLimiter(max_rpm=60)
    limiter.last_call_time = -1.0
    await asyncio.gather(
        limiter.__aenter__(),
        limiter.__aenter__(),
    )

    assert sleeps == [1.0]


# --- Merged from tests/unit/test_sparse_retriever.py ---

import json
from types import SimpleNamespace

import pytest

from astrbot.core.knowledge_base.retrieval.sparse_retriever import SparseRetriever


def make_doc(chunk_id: str, text: str, chunk_index: int = 0) -> dict:
    return {
        "doc_id": chunk_id,
        "text": text,
        "metadata": json.dumps(
            {
                "chunk_index": chunk_index,
                "kb_doc_id": f"doc-{chunk_index}",
                "kb_id": "kb-1",
            },
        ),
    }


class FTSStorage:
    def __init__(self):
        self.search_sparse_calls = 0
        self.get_documents_calls = 0

    async def search_sparse(self, query_tokens: list[str], limit: int):
        self.search_sparse_calls += 1
        assert query_tokens == ["apple"]
        assert limit == 1
        return [
            {
                **make_doc("chunk-1", "apple banana", 0),
                "score": -1.0,
            },
        ]

    async def get_documents(self, *args, **kwargs):
        self.get_documents_calls += 1
        return []


class FallbackStorage:
    def __init__(self):
        self.search_sparse_calls = 0
        self.get_documents_calls = 0

    async def search_sparse(self, query_tokens: list[str], limit: int):
        self.search_sparse_calls += 1
        return None

    async def get_documents(self, metadata_filters: dict, limit: int | None, offset):
        self.get_documents_calls += 1
        return [
            make_doc("chunk-1", "apple banana", 0),
            make_doc("chunk-2", "orange pear", 1),
            make_doc("chunk-3", "grape melon", 2),
        ]


@pytest.mark.asyncio
async def test_sparse_retriever_uses_fts5_when_available():
    storage = FTSStorage()
    vec_db = SimpleNamespace(document_storage=storage)
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-1"],
        kb_options={"kb-1": {"vec_db": vec_db, "top_k_sparse": 1}},
    )

    assert [result.chunk_id for result in results] == ["chunk-1"]
    assert storage.search_sparse_calls == 1
    assert storage.get_documents_calls == 0


@pytest.mark.asyncio
async def test_sparse_retriever_falls_back_to_bm25_when_fts5_is_unavailable():
    storage = FallbackStorage()
    vec_db = SimpleNamespace(document_storage=storage)
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="apple",
        kb_ids=["kb-1"],
        kb_options={"kb-1": {"vec_db": vec_db, "top_k_sparse": 1}},
    )

    assert [result.chunk_id for result in results] == ["chunk-1"]
    assert storage.search_sparse_calls == 1
    assert storage.get_documents_calls == 1


class MultiKBStorage:
    """模拟多知识库 BM25 回退场景"""

    def __init__(self, kb_id: str):
        self.kb_id = kb_id
        self.search_sparse_calls = 0
        self.get_documents_calls = 0

    async def search_sparse(self, query_tokens: list[str], limit: int):
        self.search_sparse_calls += 1
        return None  # 始终回退到 BM25

    async def get_documents(
        self, metadata_filters: dict, limit: int | None, offset
    ):
        self.get_documents_calls += 1
        # 返回 10 条 chunk，远多于 top_k_sparse 限制
        return [
            make_doc(f"{self.kb_id}-chunk-{i}", f"document chunk {i}", i)
            for i in range(10)
        ]


@pytest.mark.asyncio
async def test_bm25_fallback_respects_per_kb_top_k_sparse():
    """多知识库 BM25 回退时，每个知识库的结果应被截断到各自的 top_k_sparse

    Phase 1C: 验证 top_k_sparse 不再被错误求和，而是逐 KB 截断。
    """
    storage_a = MultiKBStorage("kb-a")
    storage_b = MultiKBStorage("kb-b")
    vec_db_a = SimpleNamespace(document_storage=storage_a)
    vec_db_b = SimpleNamespace(document_storage=storage_b)
    retriever = SparseRetriever(kb_db=None)

    results = await retriever.retrieve(
        query="test query",
        kb_ids=["kb-a", "kb-b"],
        kb_options={
            "kb-a": {"vec_db": vec_db_a, "top_k_sparse": 2},
            "kb-b": {"vec_db": vec_db_b, "top_k_sparse": 3},
        },
    )

    # 总结果数不应超过 max(2, 3) = 3（最终截断），且每个 KB 各贡献 ≤ 其 top_k
    assert len(results) <= 3, f"结果过多: {len(results)}"
    kb_a_count = sum(1 for r in results if r.kb_id == "kb-a")
    kb_b_count = sum(1 for r in results if r.kb_id == "kb-b")
    assert kb_a_count <= 2, f"KB-A 贡献了 {kb_a_count} 条，应 ≤ 2"
    assert kb_b_count <= 3, f"KB-B 贡献了 {kb_b_count} 条，应 ≤ 3"


# --- Merged from tests/unit/test_knowledge_base_tools.py ---

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_retrieve_knowledge_base_reports_all_invalid_session_kbs(monkeypatch):
    from astrbot.core.tools import knowledge_base_tools

    context = MagicMock()
    context.kb_manager.get_kb = AsyncMock(return_value=None)

    monkeypatch.setattr(
        knowledge_base_tools.sp,
        "session_get",
        AsyncMock(return_value={"kb_ids": ["missing-kb"], "top_k": 5}),
    )

    result = await knowledge_base_tools.retrieve_knowledge_base(
        query="hello",
        umo="session-1",
        context=context,
    )

    assert result == "会话配置的知识库均不存在或未加载，请检查知识库设置。"
    context.kb_manager.retrieve.assert_not_called()


# --- Merged from tests/test_kb_batch_delete.py ---

"""Tests for batch knowledge-base document deletion."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, call

import pytest


def _build_batch_delete_helper():
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test-kb",
        kb_id="kb-test-1",
        embedding_provider_id="emb-1",
        chunk_size=512,
        chunk_overlap=50,
    )
    helper = KBHelper.__new__(KBHelper)
    helper.kb = kb
    helper.kb_db = AsyncMock()
    helper.kb_db.get_document_by_id = AsyncMock(return_value=None)
    helper.kb_db.list_media_by_doc = AsyncMock(return_value=[])
    helper.vec_db = AsyncMock()
    helper.refresh_kb = AsyncMock()
    return helper


def _build_batch_delete_helper_with_real_dirs(tmp_path):
    helper = _build_batch_delete_helper()
    helper.kb_files_dir = tmp_path / "files"
    helper.kb_medias_dir = tmp_path / "medias"
    helper.kb_files_dir.mkdir(parents=True)
    helper.kb_medias_dir.mkdir(parents=True)
    return helper


class TestBatchDeleteKbDb:
    """Verify batch delete at the kb_db_sqlite layer."""

    @pytest.mark.asyncio
    async def test_delete_documents_by_ids_empty_list(self):
        """Empty list returns empty dict."""
        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

        kb_db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)
        vec_db = AsyncMock()

        results = await kb_db.delete_documents_by_ids([], vec_db)

        assert results == {}
        vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_documents_by_ids_batch_kb_db(self):
        """Vector cleanup succeeds before kb.db metadata is deleted."""
        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

        kb_db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)

        session = AsyncMock()
        session.__aenter__.return_value = session
        session.begin = MagicMock(return_value=session)
        kb_db.get_db = MagicMock(return_value=session)

        vec_db = AsyncMock()
        vec_db.delete_documents = AsyncMock()

        results = await kb_db.delete_documents_by_ids(
            ["doc-1", "doc-2", "doc-3"],
            vec_db,
        )

        assert results == {"doc-1": True, "doc-2": True, "doc-3": True}
        assert vec_db.delete_documents.await_count == 3
        vec_db.delete_documents.assert_has_awaits(
            [
                call(metadata_filters={"kb_doc_id": "doc-1"}),
                call(metadata_filters={"kb_doc_id": "doc-2"}),
                call(metadata_filters={"kb_doc_id": "doc-3"}),
            ],
            any_order=True,
        )
        session.execute.assert_called()

    @pytest.mark.asyncio
    async def test_delete_documents_best_effort(self):
        """One vec_db failure doesn't block other deletions."""
        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

        kb_db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)

        session = AsyncMock()
        session.__aenter__.return_value = session
        session.begin = MagicMock(return_value=session)
        kb_db.get_db = MagicMock(return_value=session)

        vec_db = AsyncMock()

        async def _delete_side_effect(metadata_filters):
            doc_id = metadata_filters["kb_doc_id"]
            if doc_id == "doc-2":
                raise RuntimeError("vector delete failed")

        vec_db.delete_documents = AsyncMock(side_effect=_delete_side_effect)

        results = await kb_db.delete_documents_by_ids(
            ["doc-1", "doc-2", "doc-3"],
            vec_db,
        )

        assert results == {"doc-1": True, "doc-2": False, "doc-3": True}
        assert vec_db.delete_documents.await_count == 3

    @pytest.mark.asyncio
    async def test_delete_document_keeps_metadata_when_vec_delete_fails(self):
        """Metadata remains visible when vector deletion fails."""
        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
        from astrbot.core.knowledge_base.models import KBDocument

        kb_db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)
        doc = KBDocument(
            doc_id="doc-1",
            kb_id="kb-a",
            doc_name="a.txt",
            file_type="txt",
            file_size=1,
            file_path="",
        )
        kb_db.get_document_by_id = AsyncMock(return_value=doc)
        session = AsyncMock()
        session.__aenter__.return_value = session
        session.begin = MagicMock(return_value=session)
        kb_db.get_db = MagicMock(return_value=session)
        vec_db = AsyncMock()
        vec_db.delete_documents = AsyncMock(side_effect=RuntimeError("boom"))

        with pytest.raises(RuntimeError, match="boom"):
            await kb_db.delete_document_by_id("doc-1", vec_db, kb_id="kb-a")

        session.execute.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_document_rejects_wrong_kb_id(self):
        """A document from another KB must not be deleted."""
        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
        from astrbot.core.knowledge_base.models import KBDocument

        kb_db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)
        doc = KBDocument(
            doc_id="doc-1",
            kb_id="kb-other",
            doc_name="a.txt",
            file_type="txt",
            file_size=1,
            file_path="",
        )
        kb_db.get_document_by_id = AsyncMock(return_value=doc)
        vec_db = AsyncMock()

        deleted = await kb_db.delete_document_by_id("doc-1", vec_db, kb_id="kb-a")

        assert deleted is False
        vec_db.delete_documents.assert_not_awaited()


class TestHelperBatchDelete:
    """Verify batch delete at the kb_helper layer."""

    @pytest.mark.asyncio
    async def test_delete_documents_updates_stats_once(self):
        """update_kb_stats is called exactly once, not N times."""
        helper = _build_batch_delete_helper()
        helper.kb_db.delete_documents_by_ids = AsyncMock(
            return_value={"doc-1": True, "doc-2": True},
        )

        results = await helper.delete_documents(["doc-1", "doc-2"])

        assert results == {"doc-1": True, "doc-2": True}
        helper.kb_db.delete_documents_by_ids.assert_awaited_once_with(
            doc_ids=["doc-1", "doc-2"],
            vec_db=helper.vec_db,
            kb_id="kb-test-1",
        )
        helper.kb_db.update_kb_stats.assert_awaited_once_with(
            kb_id="kb-test-1",
            vec_db=helper.vec_db,
        )
        helper.refresh_kb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_documents_empty_list(self):
        """Empty list delegates to kb_db layer (returns empty dict)."""
        helper = _build_batch_delete_helper()
        helper.kb_db.delete_documents_by_ids = AsyncMock(return_value={})

        results = await helper.delete_documents([])

        assert results == {}
        helper.kb_db.update_kb_stats.assert_awaited_once()
        helper.refresh_kb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_documents_preserves_failures(self):
        """Failures from kb_db layer are propagated in the result dict."""
        helper = _build_batch_delete_helper()
        helper.kb_db.delete_documents_by_ids = AsyncMock(
            return_value={"doc-1": True, "doc-2": False, "doc-3": True},
        )

        results = await helper.delete_documents(["doc-1", "doc-2", "doc-3"])

        assert results == {"doc-1": True, "doc-2": False, "doc-3": True}
        # stats still updated once even with partial failures
        helper.kb_db.update_kb_stats.assert_awaited_once()
        helper.refresh_kb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_chunk_raises_when_chunk_is_missing(self):
        helper = _build_batch_delete_helper()
        helper.vec_db.delete = AsyncMock(return_value=False)

        with pytest.raises(ValueError, match="无法找到 ID 为 chunk-missing 的文本块"):
            await helper.delete_chunk("chunk-missing", "doc-1")

        helper.vec_db.delete.assert_awaited_once_with("chunk-missing")
        helper.kb_db.update_kb_stats.assert_not_awaited()
        helper.refresh_kb.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_delete_document_cleans_source_and_media_files(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument, KBMedia

        helper = _build_batch_delete_helper_with_real_dirs(tmp_path)
        source_path = helper.kb_files_dir / "doc-1" / "source.txt"
        media_path = helper.kb_medias_dir / "doc-1" / "image.png"
        source_path.parent.mkdir(parents=True)
        media_path.parent.mkdir(parents=True)
        source_path.write_text("hello", encoding="utf-8")
        media_path.write_bytes(b"image")

        doc = KBDocument(
            doc_id="doc-1",
            kb_id="kb-test-1",
            doc_name="source.txt",
            file_type="txt",
            file_size=5,
            file_path=str(source_path),
        )
        media = KBMedia(
            media_id="media-1",
            doc_id="doc-1",
            kb_id="kb-test-1",
            media_type="image",
            file_name="image.png",
            file_path=str(media_path),
            file_size=5,
            mime_type="image/png",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=doc)
        helper.kb_db.list_media_by_doc = AsyncMock(return_value=[media])
        helper.kb_db.delete_document_by_id = AsyncMock(return_value=True)

        await helper.delete_document("doc-1")

        assert not source_path.exists()
        assert not media_path.exists()
        helper.kb_db.delete_document_by_id.assert_awaited_once()
        helper.kb_db.update_kb_stats.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_documents_only_cleans_successful_deletes(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_batch_delete_helper_with_real_dirs(tmp_path)
        success_path = helper.kb_files_dir / "doc-ok" / "ok.txt"
        failed_path = helper.kb_files_dir / "doc-fail" / "fail.txt"
        success_path.parent.mkdir(parents=True)
        failed_path.parent.mkdir(parents=True)
        success_path.write_text("ok", encoding="utf-8")
        failed_path.write_text("fail", encoding="utf-8")
        docs = {
            "doc-ok": KBDocument(
                doc_id="doc-ok",
                kb_id="kb-test-1",
                doc_name="ok.txt",
                file_type="txt",
                file_size=2,
                file_path=str(success_path),
            ),
            "doc-fail": KBDocument(
                doc_id="doc-fail",
                kb_id="kb-test-1",
                doc_name="fail.txt",
                file_type="txt",
                file_size=4,
                file_path=str(failed_path),
            ),
        }
        helper.kb_db.get_document_by_id = AsyncMock(
            side_effect=lambda doc_id: docs.get(doc_id),
        )
        helper.kb_db.list_media_by_doc = AsyncMock(return_value=[])
        helper.kb_db.delete_documents_by_ids = AsyncMock(
            return_value={"doc-ok": True, "doc-fail": False},
        )

        result = await helper.delete_documents(["doc-ok", "doc-fail"])

        assert result == {"doc-ok": True, "doc-fail": False}
        assert not success_path.exists()
        assert failed_path.exists()


@pytest.mark.asyncio
async def test_kb_sqlite_migration_adds_index_type_to_legacy_table(tmp_path):
    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

    db_path = tmp_path / "kb.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE knowledge_bases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kb_id VARCHAR(36) NOT NULL UNIQUE,
            kb_name VARCHAR(100) NOT NULL,
            description TEXT,
            emoji VARCHAR(10),
            embedding_provider_id VARCHAR(100),
            rerank_provider_id VARCHAR(100),
            chunk_size INTEGER,
            chunk_overlap INTEGER,
            top_k_dense INTEGER,
            top_k_sparse INTEGER,
            top_m_final INTEGER,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            doc_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL
        )
        """,
    )
    conn.execute(
        """
        CREATE TABLE kb_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id VARCHAR(36) NOT NULL UNIQUE,
            kb_id VARCHAR(36) NOT NULL,
            doc_name VARCHAR(255) NOT NULL,
            file_type VARCHAR(20) NOT NULL,
            file_size INTEGER NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            chunk_count INTEGER NOT NULL,
            media_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
    )
    conn.execute(
        """
        CREATE TABLE kb_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id VARCHAR(36) NOT NULL UNIQUE,
            doc_id VARCHAR(36) NOT NULL,
            kb_id VARCHAR(36) NOT NULL,
            media_type VARCHAR(20) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    )
    conn.commit()
    conn.close()

    kb_db = KBSQLiteDatabase(str(db_path))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    conn = sqlite3.connect(db_path)
    columns = {row[1] for row in conn.execute("PRAGMA table_info(knowledge_bases)")}
    conn.close()
    await kb_db.close()

    assert "index_type" in columns


@pytest.mark.asyncio
async def test_kb_sqlite_migration_adds_document_governance_columns(tmp_path):
    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

    db_path = tmp_path / "kb.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE knowledge_bases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kb_id VARCHAR(36) NOT NULL UNIQUE,
            kb_name VARCHAR(100) NOT NULL,
            description TEXT,
            emoji VARCHAR(10),
            embedding_provider_id VARCHAR(100),
            rerank_provider_id VARCHAR(100),
            chunk_size INTEGER,
            chunk_overlap INTEGER,
            top_k_dense INTEGER,
            top_k_sparse INTEGER,
            top_m_final INTEGER,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL,
            doc_count INTEGER NOT NULL,
            chunk_count INTEGER NOT NULL
        )
        """,
    )
    conn.execute(
        """
        CREATE TABLE kb_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id VARCHAR(36) NOT NULL UNIQUE,
            kb_id VARCHAR(36) NOT NULL,
            doc_name VARCHAR(255) NOT NULL,
            file_type VARCHAR(20) NOT NULL,
            file_size INTEGER NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            chunk_count INTEGER NOT NULL,
            media_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """,
    )
    conn.execute(
        """
        CREATE TABLE kb_media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            media_id VARCHAR(36) NOT NULL UNIQUE,
            doc_id VARCHAR(36) NOT NULL,
            kb_id VARCHAR(36) NOT NULL,
            media_type VARCHAR(20) NOT NULL,
            file_name VARCHAR(255) NOT NULL,
            file_path VARCHAR(512) NOT NULL,
            file_size INTEGER NOT NULL,
            mime_type VARCHAR(100) NOT NULL,
            created_at DATETIME NOT NULL
        )
        """,
    )
    conn.commit()
    conn.close()

    kb_db = KBSQLiteDatabase(str(db_path))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    conn = sqlite3.connect(db_path)
    doc_columns = {row[1] for row in conn.execute("PRAGMA table_info(kb_documents)")}
    indexes = {row[1] for row in conn.execute("PRAGMA index_list(kb_documents)")}
    task_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(kb_ingestion_tasks)")
    }
    task_indexes = {
        row[1] for row in conn.execute("PRAGMA index_list(kb_ingestion_tasks)")
    }
    conn.close()
    await kb_db.close()

    assert {
        "source_type",
        "source_uri",
        "content_hash",
        "parser_name",
        "parser_version",
        "chunker_name",
        "chunker_version",
        "status",
        "error_stage",
        "error_message",
        "version",
        "parent_doc_id",
        "indexed_at",
    }.issubset(doc_columns)
    assert {
        "idx_doc_content_hash",
        "idx_doc_status",
        "idx_doc_parent_doc_id",
    }.issubset(indexes)
    assert {
        "task_id",
        "kb_id",
        "task_type",
        "status",
        "progress_stage",
        "progress_current",
        "progress_total",
        "progress",
        "result",
        "error",
        "created_at",
        "updated_at",
    }.issubset(task_columns)
    assert {
        "idx_task_task_id",
        "idx_task_kb_id",
        "idx_task_type",
        "idx_task_status",
        "idx_task_created_at",
    }.issubset(task_indexes)


@pytest.mark.asyncio
async def test_get_document_by_content_hash_scopes_to_kb_and_active_status(tmp_path):
    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
    from astrbot.core.knowledge_base.models import KBDocument

    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    active_doc = KBDocument(
        doc_id="doc-active",
        kb_id="kb-a",
        doc_name="active.txt",
        file_type="txt",
        file_size=1,
        file_path="",
        content_hash="hash-a",
        status="ready",
    )
    failed_doc = KBDocument(
        doc_id="doc-failed",
        kb_id="kb-a",
        doc_name="failed.txt",
        file_type="txt",
        file_size=1,
        file_path="",
        content_hash="hash-failed",
        status="failed",
    )
    other_kb_doc = KBDocument(
        doc_id="doc-other-kb",
        kb_id="kb-b",
        doc_name="other.txt",
        file_type="txt",
        file_size=1,
        file_path="",
        content_hash="hash-a",
        status="ready",
    )

    async with kb_db.get_db() as session:
        session.add(active_doc)
        session.add(failed_doc)
        session.add(other_kb_doc)
        await session.commit()

    duplicate = await kb_db.get_document_by_content_hash(
        kb_id="kb-a",
        content_hash="hash-a",
    )
    failed = await kb_db.get_document_by_content_hash(
        kb_id="kb-a",
        content_hash="hash-failed",
    )
    other_kb = await kb_db.get_document_by_content_hash(
        kb_id="kb-b",
        content_hash="hash-a",
    )

    await kb_db.close()

    assert duplicate is not None
    assert duplicate.doc_id == "doc-active"
    assert failed is None
    assert other_kb is not None
    assert other_kb.doc_id == "doc-other-kb"


@pytest.mark.asyncio
async def test_document_list_filters_by_status_and_source_type(tmp_path):
    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
    from astrbot.core.knowledge_base.models import KBDocument

    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    docs = [
        KBDocument(
            doc_id="doc-ready-file",
            kb_id="kb-a",
            doc_name="alpha.txt",
            file_type="txt",
            file_size=1,
            file_path="",
            source_type="file",
            status="ready",
        ),
        KBDocument(
            doc_id="doc-failed-file",
            kb_id="kb-a",
            doc_name="alpha-failed.txt",
            file_type="txt",
            file_size=1,
            file_path="",
            source_type="file",
            status="failed",
        ),
        KBDocument(
            doc_id="doc-ready-url",
            kb_id="kb-a",
            doc_name="alpha-url.txt",
            file_type="txt",
            file_size=1,
            file_path="",
            source_type="url",
            status="ready",
        ),
        KBDocument(
            doc_id="doc-other-kb",
            kb_id="kb-b",
            doc_name="alpha.txt",
            file_type="txt",
            file_size=1,
            file_path="",
            source_type="file",
            status="ready",
        ),
    ]

    async with kb_db.get_db() as session:
        session.add_all(docs)
        await session.commit()

    filtered_docs = await kb_db.list_documents_by_kb(
        "kb-a",
        search="alpha",
        status="ready",
        source_type="file",
    )
    filtered_count = await kb_db.count_documents_by_kb(
        "kb-a",
        search="alpha",
        status="ready",
        source_type="file",
    )

    await kb_db.close()

    assert [doc.doc_id for doc in filtered_docs] == ["doc-ready-file"]
    assert filtered_count == 1


@pytest.mark.asyncio
async def test_ingestion_task_crud_round_trips_json_and_filters(tmp_path):
    from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    created = await kb_db.create_ingestion_task(
        task_id="task-upload",
        kb_id="kb-a",
        task_type="upload",
        status="pending",
        progress_stage="waiting",
        progress={"file_total": 2},
    )
    await kb_db.create_ingestion_task(
        task_id="task-import",
        kb_id="kb-b",
        task_type="import",
        status="processing",
    )

    updated = await kb_db.update_ingestion_task(
        "task-upload",
        status="completed",
        progress_stage="embedding",
        progress_current=2,
        progress_total=2,
        progress={"file_index": 1, "file_total": 2},
        result={"success_count": 2, "failed": []},
        error=None,
    )
    missing = await kb_db.update_ingestion_task(
        "missing-task",
        status="failed",
    )
    fetched = await kb_db.get_ingestion_task("task-upload")
    completed_tasks = await kb_db.list_ingestion_tasks(status="completed")
    kb_b_tasks = await kb_db.list_ingestion_tasks(kb_id="kb-b", task_type="import")
    completed_task_count = await kb_db.count_ingestion_tasks(status="completed")
    kb_b_task_count = await kb_db.count_ingestion_tasks(
        kb_id="kb-b",
        task_type="import",
    )

    await kb_db.close()

    assert created["task_id"] == "task-upload"
    assert created["progress"] == {"file_total": 2}
    assert updated is not None
    assert updated["status"] == "completed"
    assert updated["progress_stage"] == "embedding"
    assert updated["progress_current"] == 2
    assert updated["progress_total"] == 2
    assert updated["progress"] == {"file_index": 1, "file_total": 2}
    assert updated["result"] == {"success_count": 2, "failed": []}
    assert updated["error"] is None
    assert missing is None
    assert fetched == updated
    assert [task["task_id"] for task in completed_tasks] == ["task-upload"]
    assert [task["task_id"] for task in kb_b_tasks] == ["task-import"]
    assert completed_task_count == 1
    assert kb_b_task_count == 1


# --- Merged from tests/test_kb_faiss_async_save.py ---

"""Tests for #5: FAISS save_index uses asyncio.to_thread to avoid blocking
the event loop during synchronous faiss.write_index calls.
"""

import asyncio
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _make_storage(dimension: int = 128, path: str = "/tmp/test.index"):
    """Build an EmbeddingStorage instance with a minimal mocked FAISS index."""
    import asyncio

    from astrbot.core.db.vec_db.faiss_impl.embedding_storage import EmbeddingStorage

    storage = EmbeddingStorage.__new__(EmbeddingStorage)
    storage.dimension = dimension
    storage.path = path
    storage._write_lock = asyncio.Lock()
    # Mock FAISS index — just enough to satisfy the method guards
    storage.index = MagicMock()
    storage.index.ntotal = 100
    return storage


class TestFaissSaveIndexAsync:
    """Verify save_index delegates to asyncio.to_thread."""

    @pytest.mark.asyncio
    async def test_save_index_uses_to_thread(self):
        """save_index offloads faiss.write_index to a thread."""
        import faiss  # noqa: F401 — ensure faiss is importable

        storage = _make_storage()

        with patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.asyncio.to_thread",
        ) as mock_to_thread:
            mock_to_thread.return_value = None  # simulate completion
            await storage.save_index()

        mock_to_thread.assert_awaited_once_with(
            faiss.write_index, storage.index, storage.path,
        )

    @pytest.mark.asyncio
    async def test_save_index_skips_when_index_none(self):
        """save_index is a no-op when index hasn't been initialized."""
        storage = _make_storage()
        storage.index = None

        with patch(
            "astrbot.core.db.vec_db.faiss_impl.embedding_storage.asyncio.to_thread",
        ) as mock_to_thread:
            await storage.save_index()

        mock_to_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_insert_calls_save_index(self):
        """insert() calls _save_index_locked after adding the vector."""
        storage = _make_storage()
        storage.index.add_with_ids = MagicMock()

        with patch.object(
            storage, "_save_index_locked", return_value=None
        ) as mock_save:
            import faiss  # noqa: F811

            vector = np.random.rand(storage.dimension).astype(np.float32)
            await storage.insert(vector, id=42)

        storage.index.add_with_ids.assert_called_once()
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_insert_batch_calls_save_index(self):
        """insert_batch() calls _save_index_locked after batch-adding vectors."""
        storage = _make_storage()
        storage.index.add_with_ids = MagicMock()

        with patch.object(
            storage, "_save_index_locked", return_value=None
        ) as mock_save:
            vectors = np.random.rand(10, storage.dimension).astype(np.float32)
            ids = list(range(10))
            await storage.insert_batch(vectors, ids)

        storage.index.add_with_ids.assert_called_once()
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_calls_save_index(self):
        """delete() calls _save_index_locked after removing vectors."""
        storage = _make_storage()
        storage.index.remove_ids = MagicMock()

        with patch.object(
            storage, "_save_index_locked", return_value=None
        ) as mock_save:
            await storage.delete([1, 2, 3])

        storage.index.remove_ids.assert_called_once()
        mock_save.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_index_with_real_faiss_index(self):
        """End-to-end: save_index with a real FAISS index writes to a temp file."""
        import faiss
        import tempfile

        dim = 128
        base_index = faiss.IndexFlatL2(dim)
        index = faiss.IndexIDMap(base_index)
        index.add_with_ids(
            np.random.rand(5, dim).astype(np.float32),
            np.array([1, 2, 3, 4, 5], dtype=np.int64),
        )

        with tempfile.NamedTemporaryFile(suffix=".index", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = _make_storage(dimension=dim, path=tmp_path)
            storage.index = index

            await storage.save_index()

            # Verify file was written and is readable
            assert __import__("os").path.exists(tmp_path)
            assert __import__("os").path.getsize(tmp_path) > 0

            # Round-trip: read back and verify dimension matches
            restored = faiss.read_index(tmp_path)
            assert restored.ntotal == 5
        finally:
            __import__("os").unlink(tmp_path)

    @pytest.mark.asyncio
    async def test_real_save_does_not_block_event_loop(self):
        """Verify a real save_index completes quickly for a small index."""
        import faiss
        import tempfile

        dim = 64
        base_index = faiss.IndexFlatL2(dim)
        index = faiss.IndexIDMap(base_index)
        # 1000 vectors — should be very fast
        index.add_with_ids(
            np.random.rand(1000, dim).astype(np.float32),
            np.arange(1000, dtype=np.int64),
        )

        with tempfile.NamedTemporaryFile(suffix=".index", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            storage = _make_storage(dimension=dim, path=tmp_path)
            storage.index = index

            # Should complete quickly
            await asyncio.wait_for(storage.save_index(), timeout=5.0)
            assert __import__("os").path.getsize(tmp_path) > 0
        finally:
            __import__("os").unlink(tmp_path)


# --- Merged from tests/test_kb_import.py ---

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from quart import Quart

from astrbot.core import LogBroker
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KBDocument
from astrbot.core.utils.auth_password import (
    hash_dashboard_password,
    hash_legacy_dashboard_password,
)
from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute
from astrbot.dashboard.server import AstrBotDashboard

_TEST_DASHBOARD_PASSWORD = "AstrbotTest123"


@pytest_asyncio.fixture(scope="module")
async def core_lifecycle_td(tmp_path_factory):
    """Creates and initializes a core lifecycle instance with a temporary database."""
    tmp_db_path = tmp_path_factory.mktemp("data") / "test_data_kb.db"
    db = SQLiteDatabase(str(tmp_db_path))
    log_broker = LogBroker()
    core_lifecycle = AstrBotCoreLifecycle(log_broker, db)
    await core_lifecycle.initialize()

    # Mock kb_manager and kb_helper
    kb_manager = MagicMock()
    kb_helper = AsyncMock(spec=KBHelper)

    # Configure get_kb to be an async mock that returns kb_helper
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)

    # Mock upload_document return value
    mock_doc = KBDocument(
        doc_id="test_doc_id",
        kb_id="test_kb_id",
        doc_name="test_file.txt",
        file_type="txt",
        file_size=100,
        file_path="",
        chunk_count=2,
        media_count=0,
    )
    kb_helper.upload_document.return_value = mock_doc

    # kb_manager.get_kb.return_value = kb_helper # Removed this line as it's handled above
    core_lifecycle.kb_manager = kb_manager
    generated_password = getattr(
        core_lifecycle.astrbot_config,
        "_generated_dashboard_password",
        None,
    )
    dashboard_password = generated_password or _TEST_DASHBOARD_PASSWORD
    if not generated_password:
        core_lifecycle.astrbot_config["dashboard"]["pbkdf2_password"] = (
            hash_dashboard_password(dashboard_password)
        )
        core_lifecycle.astrbot_config["dashboard"]["password"] = (
            hash_legacy_dashboard_password(dashboard_password)
        )
    object.__setattr__(
        core_lifecycle,
        "_dashboard_plain_password",
        dashboard_password,
    )

    try:
        yield core_lifecycle
    finally:
        try:
            _stop_res = core_lifecycle.stop()
            if asyncio.iscoroutine(_stop_res):
                await _stop_res
        except Exception:
            pass


@pytest.fixture(scope="module")
def app(core_lifecycle_td: AstrBotCoreLifecycle):
    """Creates a Quart app instance for testing."""
    shutdown_event = asyncio.Event()
    server = AstrBotDashboard(core_lifecycle_td, core_lifecycle_td.db, shutdown_event)
    return server.app


def _resolve_dashboard_password(core_lifecycle_td: AstrBotCoreLifecycle) -> str:
    generated_password = getattr(core_lifecycle_td, "_dashboard_plain_password", None)
    if generated_password:
        return generated_password
    password = core_lifecycle_td.astrbot_config["dashboard"]["pbkdf2_password"]
    if isinstance(password, str) and password.startswith("pbkdf2_sha256$"):
        return "astrbot"
    return password


@pytest_asyncio.fixture(scope="module")
async def authenticated_header(app: Quart, core_lifecycle_td: AstrBotCoreLifecycle):
    """Handles login and returns an authenticated header."""
    test_client = app.test_client()
    response = await test_client.post(
        "/api/auth/login",
        json={
            "username": core_lifecycle_td.astrbot_config["dashboard"]["username"],
            "password": _resolve_dashboard_password(core_lifecycle_td),
        },
    )
    data = await response.get_json()
    assert data["status"] == "ok"
    token = data["data"]["token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_import_documents(
    app: Quart, authenticated_header: dict, core_lifecycle_td: AstrBotCoreLifecycle
):
    """Tests the import documents functionality."""
    test_client = app.test_client()
    kb_helper = await core_lifecycle_td.kb_manager.get_kb("test_kb_id")
    kb_helper.upload_document.reset_mock()
    kb_helper.upload_document.side_effect = None

    # Test data
    import_data = {
        "kb_id": "test_kb_id",
        "documents": [
            {"file_name": "test_file_1.txt", "chunks": ["chunk1", "chunk2"]},
            {"file_name": "test_file_2.md", "chunks": ["chunk3", "chunk4", "chunk5"]},
        ],
    }

    # Send request
    response = await test_client.post(
        "/api/kb/document/import", json=import_data, headers=authenticated_header
    )

    # Verify response
    assert response.status_code == 200
    data = await response.get_json()
    assert data["status"] == "ok"
    assert "task_id" in data["data"]
    assert data["data"]["doc_count"] == 2

    task_id = data["data"]["task_id"]

    # Wait for background task to complete (mocked)
    # Since we mocked upload_document, it should be fast, but we might need to poll progress
    for _ in range(10):
        progress_response = await test_client.get(
            f"/api/kb/document/upload/progress?task_id={task_id}",
            headers=authenticated_header,
        )
        progress_data = await progress_response.get_json()
        if progress_data["data"]["status"] == "completed":
            break
        await asyncio.sleep(0.1)

    assert progress_data["data"]["status"] == "completed"
    result = progress_data["data"]["result"]
    assert result["success_count"] == 2
    assert result["failed_count"] == 0

    # Verify kb_helper.upload_document was called correctly
    assert kb_helper.upload_document.call_count == 2

    # Check first call arguments
    call_args_list = kb_helper.upload_document.call_args_list

    # First document
    args1, kwargs1 = call_args_list[0]
    assert kwargs1["file_name"] == "test_file_1.txt"
    assert kwargs1["pre_chunked_text"] == ["chunk1", "chunk2"]

    # Second document
    args2, kwargs2 = call_args_list[1]
    assert kwargs2["file_name"] == "test_file_2.md"
    assert kwargs2["pre_chunked_text"] == ["chunk3", "chunk4", "chunk5"]


@pytest.mark.asyncio
async def test_import_documents_returns_friendly_failure_message(
    core_lifecycle_td: AstrBotCoreLifecycle,
):
    kb_helper = await core_lifecycle_td.kb_manager.get_kb("test_kb_id")
    kb_helper.upload_document.reset_mock()
    kb_helper.upload_document.side_effect = KnowledgeBaseUploadError(
        stage="embedding",
        user_message=(
            "向量化失败：嵌入模型返回的向量数量与文本分块数量不一致（期望 2，实际 1）。"
        ),
        details={"expected_contents": 2, "actual_vectors": 1},
    )

    route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
    route.upload_progress = {}
    route.upload_tasks = {}

    await KnowledgeBaseRoute._background_import_task(
        route,
        task_id="task-1",
        kb_helper=kb_helper,
        documents=[{"file_name": "broken.txt", "chunks": ["chunk1", "chunk2"]}],
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
    )

    assert route.upload_tasks["task-1"]["status"] == "failed"
    result = route.upload_tasks["task-1"]["result"]
    assert result["success_count"] == 0
    assert result["failed_count"] == 1
    assert result["failed"][0]["file_name"] == "broken.txt"
    assert result["failed"][0]["error"].startswith("broken.txt:")
    assert "向量化失败" in result["failed"][0]["error"]
    assert "期望 2，实际 1" in result["failed"][0]["error"]
    assert "not same nb of vectors as ids" not in result["failed"][0]["error"]
    assert kb_helper.upload_document.await_count == 1

    kb_helper.upload_document.side_effect = None


@pytest.mark.asyncio
async def test_import_documents_invalid_input(app: Quart, authenticated_header: dict):
    """Tests import documents with invalid input."""
    test_client = app.test_client()

    # Missing kb_id
    response = await test_client.post(
        "/api/kb/document/import", json={"documents": []}, headers=authenticated_header
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "缺少参数 kb_id" in data["message"]

    # Missing documents
    response = await test_client.post(
        "/api/kb/document/import",
        json={"kb_id": "test_kb"},
        headers=authenticated_header,
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "缺少参数 documents" in data["message"]

    # Invalid document format
    response = await test_client.post(
        "/api/kb/document/import",
        json={
            "kb_id": "test_kb",
            "documents": [{"file_name": "test"}],  # Missing chunks
        },
        headers=authenticated_header,
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "文档格式错误" in data["message"]

    # Invalid chunks type
    response = await test_client.post(
        "/api/kb/document/import",
        json={
            "kb_id": "test_kb",
            "documents": [{"file_name": "test", "chunks": "not-a-list"}],
        },
        headers=authenticated_header,
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "chunks 必须是列表" in data["message"]

    # Invalid chunks content
    response = await test_client.post(
        "/api/kb/document/import",
        json={
            "kb_id": "test_kb",
            "documents": [{"file_name": "test", "chunks": ["valid", ""]}],
        },
        headers=authenticated_header,
    )
    data = await response.get_json()
    assert data["status"] == "error"
    assert "chunks 必须是非空字符串列表" in data["message"]


# --- Merged from tests/test_kb_sparse_retrieval.py ---

"""Tests for sparse retrieval score consistency between FTS5 and BM25 paths.

RRF only uses rank positions, not score magnitudes. The sparse retrieval stage
just needs consistent sort direction: lower-is-better, ascending order.
"""

import json
from unittest.mock import AsyncMock

import pytest

from astrbot.core.knowledge_base.retrieval.sparse_retriever import (
    SparseResult,
    SparseRetriever,
)


def _make_fake_doc(doc_id: str, text: str, metadata: dict) -> dict:
    return {
        "id": hash(doc_id) % 10000,
        "doc_id": doc_id,
        "text": text,
        "metadata": json.dumps(metadata),
        "created_at": "2025-01-01T00:00:00",
        "updated_at": "2025-01-01T00:00:00",
    }


class TestSparseRetrieverScoreDirection:
    """Verify FTS5 and BM25 both use lower-is-better, ascending sort."""

    @pytest.mark.asyncio
    async def test_fts5_best_match_has_lowest_score(self):
        """FTS5: raw bm25=0 (perfect) → score=0, sorts first (ascending)."""
        sr = SparseRetriever(kb_db=AsyncMock())
        sr._index_cache = {}

        vec_db = AsyncMock()
        vec_db.document_storage.search_sparse = AsyncMock(
            return_value=[
                {
                    "id": 1, "doc_id": "best", "text": "exact match",
                    "metadata": json.dumps({"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": 0.0,  # perfect
                    "created_at": "", "updated_at": "",
                },
                {
                    "id": 2, "doc_id": "worst", "text": "poor match",
                    "metadata": json.dumps({"chunk_index": 1, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": 50.0,  # terrible
                    "created_at": "", "updated_at": "",
                },
            ],
        )

        kb_options = {"kb-a": {"vec_db": vec_db, "top_k_sparse": 10}}
        results = await sr.retrieve(query="test", kb_ids=["kb-a"], kb_options=kb_options)

        assert len(results) == 2
        assert results[0].chunk_id == "best", f"Best should be first, got {results[0].chunk_id}"
        assert results[0].score == 0.0  # lower-is-better
        assert results[0].score < results[1].score  # ascending

    @pytest.mark.asyncio
    async def test_fts5_negative_bm25_clamped_to_zero(self):
        """FTS5 bm25() negative values → clamped to 0 (same as perfect match)."""
        sr = SparseRetriever(kb_db=AsyncMock())
        sr._index_cache = {}

        vec_db = AsyncMock()
        vec_db.document_storage.search_sparse = AsyncMock(
            return_value=[
                {
                    "id": 1, "doc_id": "short-doc", "text": "short",
                    "metadata": json.dumps({"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": -8.56,  # FTS5 can be negative for short docs
                    "created_at": "", "updated_at": "",
                },
            ],
        )

        kb_options = {"kb-a": {"vec_db": vec_db, "top_k_sparse": 10}}
        results = await sr.retrieve(query="test", kb_ids=["kb-a"], kb_options=kb_options)

        assert len(results) == 1
        assert results[0].score == 0.0, (
            f"Negative raw bm25 should be clamped to 0, got {results[0].score}"
        )

    @pytest.mark.asyncio
    async def test_bm25_fallback_negates_scores(self):
        """BM25Okapi higher=better → negated to lower=better, ascending sort."""
        sr = SparseRetriever(kb_db=AsyncMock())
        sr._index_cache = {}

        vec_db = AsyncMock()
        vec_db.document_storage.get_documents = AsyncMock(
            return_value=[
                _make_fake_doc("chunk-best", "exact match hello world",
                               {"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                _make_fake_doc("chunk-worst", "unrelated content here",
                               {"chunk_index": 0, "kb_doc_id": "d2", "kb_id": "kb-a"}),
            ],
        )

        kb_options = {"kb-a": {"vec_db": vec_db, "top_k_sparse": 50}}
        results = await sr._retrieve_with_bm25(query="hello", kb_ids=["kb-a"], kb_options=kb_options)

        assert len(results) == 2
        # Best match should be most negative (negated highest BM25Okapi)
        assert results[0].score <= results[1].score, (
            f"Expected ascending sort (lower=better), got {[r.score for r in results]}"
        )
        # Best score should be <= 0 (negation of non-negative BM25Okapi)
        assert results[0].score <= 0, (
            f"BM25 fallback best match should be negative after negation, got {results[0].score}"
        )

    @pytest.mark.asyncio
    async def test_merged_fts5_and_bm25_sort_correctly(self):
        """Merge: FTS5 (0=best) + BM25 (neg=best) → ascending sort, both can be top."""
        fts = [
            SparseResult(chunk_id="fts-best", chunk_index=0, doc_id="d1",
                         kb_id="kb-a", content="a", score=0.0),
            SparseResult(chunk_id="fts-mid", chunk_index=1, doc_id="d1",
                         kb_id="kb-a", content="b", score=3.0),
            SparseResult(chunk_id="fts-worst", chunk_index=2, doc_id="d2",
                         kb_id="kb-a", content="c", score=12.5),
        ]
        bm25 = [
            SparseResult(chunk_id="bm25-good", chunk_index=0, doc_id="d3",
                         kb_id="kb-b", content="d", score=-15.0),  # negated best
            SparseResult(chunk_id="bm25-ok", chunk_index=1, doc_id="d3",
                         kb_id="kb-b", content="e", score=-5.0),
            SparseResult(chunk_id="bm25-poor", chunk_index=2, doc_id="d4",
                         kb_id="kb-b", content="f", score=0.0),  # negated worst
        ]

        merged = fts + bm25
        merged.sort(key=lambda x: x.score)  # ascending, lower=better

        # Expected: bm25-good(-15) < fts-best(0) < fts-mid(3) < bm25-ok(-5) < bm25-poor(0) < fts-worst(12.5)
        # Wait: -15 < -5 < 0 < 0 < 3 < 12.5
        assert merged[0].chunk_id == "bm25-good"
        assert merged[1].chunk_id == "bm25-ok"
        # fts-best(0) and bm25-poor(0) tie — stable sort preserves order
        assert merged[4].chunk_id == "fts-mid"
        assert merged[5].chunk_id == "fts-worst"

    @pytest.mark.asyncio
    async def test_fts5_and_bm25_both_contribute_to_sort(self):
        """Integration: both paths produce consistent lower-is-better scores."""
        sr = SparseRetriever(kb_db=AsyncMock())

        # KB "a" uses FTS5
        fts_vec_db = AsyncMock()
        fts_vec_db.document_storage.search_sparse = AsyncMock(
            return_value=[
                {
                    "id": 1, "doc_id": "fts-hit", "text": "test query match",
                    "metadata": json.dumps({"chunk_index": 0, "kb_doc_id": "d1", "kb_id": "kb-a"}),
                    "score": 0.0,
                },
            ],
        )

        # KB "b" falls back to BM25
        bm25_vec_db = AsyncMock()
        bm25_vec_db.document_storage.search_sparse = AsyncMock(return_value=None)
        bm25_vec_db.document_storage.get_documents = AsyncMock(
            return_value=[
                _make_fake_doc("bm25-hit", "test query result",
                               {"chunk_index": 0, "kb_doc_id": "d2", "kb_id": "kb-b"}),
                _make_fake_doc("bm25-miss", "unrelated",
                               {"chunk_index": 0, "kb_doc_id": "d3", "kb_id": "kb-b"}),
            ],
        )

        kb_options = {
            "kb-a": {"vec_db": fts_vec_db, "top_k_sparse": 10},
            "kb-b": {"vec_db": bm25_vec_db, "top_k_sparse": 10},
        }

        results = await sr.retrieve(query="test", kb_ids=["kb-a", "kb-b"], kb_options=kb_options)

        assert len(results) >= 2
        # Ascending order
        for i in range(len(results) - 1):
            assert results[i].score <= results[i + 1].score, (
                f"Not sorted ascending at index {i}: {results[i].score} > {results[i+1].score}"
            )
        # No out-of-range scores
        for r in results:
            assert r.score >= -1000.0, f"Unexpectedly low score: {r.score}"

    @pytest.mark.asyncio
    async def test_bm25_fallback_honors_chunk_limit(self):
        """BM25 fallback caps loaded chunks at MAX_BM25_DOCS to prevent OOM."""
        sr = SparseRetriever(kb_db=AsyncMock())

        cap = sr.MAX_BM25_DOCS
        # Create more docs than the cap
        many_docs = [
            _make_fake_doc(
                f"chunk-{i}", f"document content {i}",
                {"chunk_index": i, "kb_doc_id": f"d{i//10}", "kb_id": "kb-a"},
            )
            for i in range(cap + 100)
        ]

        vec_db = AsyncMock()
        vec_db.document_storage.search_sparse = AsyncMock(return_value=None)
        vec_db.document_storage.get_documents = AsyncMock(return_value=many_docs)

        kb_options = {"kb-a": {"vec_db": vec_db, "top_k_sparse": 50}}

        results = await sr.retrieve(query="test", kb_ids=["kb-a"], kb_options=kb_options)

        # get_documents was called with the cap as limit
        vec_db.document_storage.get_documents.assert_awaited_once_with(
            metadata_filters={"kb_id": "kb-a"},
            limit=cap,
            offset=0,
        )

        # Results should not exceed the cap (minus what top_k_sparse filters)
        assert len(results) <= 50  # top_k_sparse limit

    @pytest.mark.asyncio
    async def test_bm25_fallback_filters_by_kb_id(self):
        """BM25 fallback now passes kb_id metadata filter to get_documents."""
        sr = SparseRetriever(kb_db=AsyncMock())

        vec_db = AsyncMock()
        vec_db.document_storage.search_sparse = AsyncMock(return_value=None)
        vec_db.document_storage.get_documents = AsyncMock(return_value=[])

        kb_options = {
            "kb-a": {"vec_db": vec_db, "top_k_sparse": 10},
        }

        await sr.retrieve(query="test", kb_ids=["kb-a"], kb_options=kb_options)

        # Verify the kb_id filter is passed (previously was empty {})
        vec_db.document_storage.get_documents.assert_awaited_once_with(
            metadata_filters={"kb_id": "kb-a"},
            limit=sr.MAX_BM25_DOCS,
            offset=0,
        )


# --- Merged from tests/test_kb_stats.py ---

"""Tests for knowledge base statistics accuracy."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase


class TestUpdateKbStatsChunkCountScope:
    """Verify update_kb_stats scopes chunk counts to the correct KB."""

    @staticmethod
    def _patch_get_db(db: KBSQLiteDatabase) -> None:
        """Replace get_db with a mock that simulates the real async-CM flow.

        In production::

            async with self.get_db() as session, session.begin():
                ...

        Broken down:
          1. ``self.get_db()`` → async CM
          2. ``__aenter__()`` → await → session (bound via ``as``)
          3. ``session.begin()`` → second async CM
          4. ``__aenter__()`` → await → enters the transaction

        We must ensure the ``session`` yielded by step 2 has a ``begin`` that
        returns a valid async CM so the second ``async with`` succeeds.
        """
        session = AsyncMock()
        # Step 2: __aenter__ must yield *this* session (with .begin overridden)
        session.__aenter__.return_value = session
        # Step 3-4: session.begin() returns an async CM → we return session itself
        session.begin = MagicMock(return_value=session)

        db.get_db = MagicMock(return_value=session)

    @pytest.mark.asyncio
    async def test_update_kb_stats_filters_chunk_count_by_kb_id(self):
        """chunk_cnt should only count documents belonging to the target KB."""
        db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)
        self._patch_get_db(db)

        vec_db = AsyncMock()
        vec_db.count_documents = AsyncMock(return_value=42)

        await db.update_kb_stats(kb_id="kb-abc", vec_db=vec_db)

        vec_db.count_documents.assert_awaited_once_with(
            metadata_filter={"kb_id": "kb-abc"},
        )

    @pytest.mark.asyncio
    async def test_update_kb_stats_passes_different_kb_ids(self):
        """Each KB update should filter chunks by its own kb_id."""
        db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)
        self._patch_get_db(db)

        vec_db_a = AsyncMock()
        vec_db_a.count_documents = AsyncMock(return_value=10)
        vec_db_b = AsyncMock()
        vec_db_b.count_documents = AsyncMock(return_value=20)

        await db.update_kb_stats(kb_id="kb-alpha", vec_db=vec_db_a)
        await db.update_kb_stats(kb_id="kb-beta", vec_db=vec_db_b)

        vec_db_a.count_documents.assert_awaited_once_with(
            metadata_filter={"kb_id": "kb-alpha"},
        )
        vec_db_b.count_documents.assert_awaited_once_with(
            metadata_filter={"kb_id": "kb-beta"},
        )

    @pytest.mark.asyncio
    async def test_update_kb_stats_zero_chunks(self):
        """When a KB has no chunks, chunk_count should be set to 0."""
        db = KBSQLiteDatabase.__new__(KBSQLiteDatabase)
        self._patch_get_db(db)

        vec_db = AsyncMock()
        vec_db.count_documents = AsyncMock(return_value=0)

        await db.update_kb_stats(kb_id="kb-empty", vec_db=vec_db)

        vec_db.count_documents.assert_awaited_once_with(
            metadata_filter={"kb_id": "kb-empty"},
        )


@pytest.mark.asyncio
async def test_get_kb_stats_returns_status_and_chunk_breakdown(tmp_path):
    from astrbot.core.knowledge_base.models import KBDocument, KBMedia, KnowledgeBase

    kb_db = KBSQLiteDatabase(str(tmp_path / "kb.db"))
    await kb_db.initialize()
    await kb_db.migrate_to_v1()

    kb = KnowledgeBase(
        kb_id="kb-stats",
        kb_name="stats",
        embedding_provider_id="emb-1",
        doc_count=3,
        chunk_count=8,
    )
    docs = [
        KBDocument(
            doc_id="doc-ready-1",
            kb_id="kb-stats",
            doc_name="ready-1.txt",
            file_type="txt",
            file_size=10,
            file_path=str(tmp_path / "ready-1.txt"),
            source_type="file",
            status="ready",
            chunk_count=3,
        ),
        KBDocument(
            doc_id="doc-ready-2",
            kb_id="kb-stats",
            doc_name="ready-2.txt",
            file_type="txt",
            file_size=20,
            file_path="",
            source_type="file",
            status="ready",
            chunk_count=5,
        ),
        KBDocument(
            doc_id="doc-failed",
            kb_id="kb-stats",
            doc_name="failed.txt",
            file_type="txt",
            file_size=30,
            file_path="",
            source_type="file",
            status="failed",
            chunk_count=0,
        ),
        KBDocument(
            doc_id="doc-other",
            kb_id="kb-other",
            doc_name="other.txt",
            file_type="txt",
            file_size=40,
            file_path=str(tmp_path / "other.txt"),
            source_type="file",
            status="ready",
            chunk_count=99,
        ),
    ]
    media = KBMedia(
        media_id="media-1",
        doc_id="doc-ready-1",
        kb_id="kb-stats",
        media_type="image",
        file_name="image.png",
        file_path="",
        file_size=7,
        mime_type="image/png",
    )

    async with kb_db.get_db() as session:
        session.add(kb)
        for doc in docs:
            session.add(doc)
        session.add(media)
        await session.commit()

    stats = await kb_db.get_kb_stats("kb-stats")
    missing = await kb_db.get_kb_stats("missing-kb")

    await kb_db.close()

    assert stats is not None
    assert stats["kb_id"] == "kb-stats"
    assert stats["doc_count"] == 3
    assert stats["chunk_count"] == 8
    assert stats["document_count"] == 3
    assert stats["ready_document_count"] == 2
    assert stats["failed_document_count"] == 1
    assert stats["pending_document_count"] == 0
    assert stats["processing_document_count"] == 0
    assert stats["indexed_chunk_count"] == 8
    assert stats["document_chunk_count"] == 8
    assert stats["media_count"] == 1
    assert stats["source_file_count"] == 1
    assert stats["storage_bytes"] == 17
    assert stats["status_counts"] == {"failed": 1, "ready": 2}
    assert missing is None


# --- Merged from tests/test_kb_update_route.py ---

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from quart import Quart


def _build_route_with_manager(kb_manager: MagicMock):
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
    route._get_kb_manager = MagicMock(return_value=kb_manager)
    return route


def _build_kb_helper(rerank_provider_id: str | None = "rerank-1"):
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
        rerank_provider_id=rerank_provider_id,
    )
    helper = MagicMock()
    helper.kb = kb
    return helper


def _build_kb_helper_with_options(**kwargs):
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_id=kwargs.get("kb_id", "kb-1"),
        kb_name=kwargs.get("kb_name", "kb"),
        embedding_provider_id="emb-1",
        rerank_provider_id=kwargs.get("rerank_provider_id", "rerank-1"),
        chunk_size=kwargs.get("chunk_size", 512),
        chunk_overlap=kwargs.get("chunk_overlap", 50),
        top_k_dense=kwargs.get("top_k_dense", 50),
        top_k_sparse=kwargs.get("top_k_sparse", 50),
        top_m_final=kwargs.get("top_m_final", 5),
        index_type=kwargs.get("index_type", "flat"),
    )
    helper = MagicMock()
    helper.kb = kb
    return helper


@pytest.mark.asyncio
async def test_get_capabilities_returns_backend_limits():
    from astrbot.core.knowledge_base.capabilities import (
        ALLOWED_UPLOAD_EXTENSIONS,
        CHUNK_PAGE_SIZE_OPTIONS,
        DEFAULT_BULK_PAGE_SIZE,
        DEFAULT_CHUNK_OVERLAP,
        DEFAULT_CHUNK_PAGE_SIZE,
        DEFAULT_CHUNK_SIZE,
        DEFAULT_DOCUMENT_PAGE_SIZE,
        DEFAULT_INDEX_TYPE,
        DEFAULT_KB_PAGE_SIZE,
        DEFAULT_TOP_K_DENSE,
        DEFAULT_TOP_K_SPARSE,
        DEFAULT_TOP_M_FINAL,
        DEFAULT_UPLOAD_BATCH_SIZE,
        DEFAULT_UPLOAD_MAX_RETRIES,
        DEFAULT_UPLOAD_TASKS_LIMIT,
        DOCUMENT_FILTER_SOURCE_TYPES,
        DOCUMENT_FILTER_STATUSES,
        DOCUMENT_PAGE_SIZE_OPTIONS,
        FEATURE_BATCH_DELETE,
        FEATURE_BATCH_REBUILD,
        FEATURE_CONSISTENCY_CHECK,
        FEATURE_CONSISTENCY_REPAIR,
        FEATURE_DOCUMENT_REBUILD,
        FEATURE_KB_REBUILD,
        FEATURE_RERANK,
        FEATURE_SPARSE_RETRIEVAL,
        FEATURE_URL_IMPORT,
        MAX_BATCH_DELETE_DOCUMENTS,
        MAX_BATCH_REBUILD_DOCUMENTS,
        MAX_RETRIEVE_TOP_K,
        MAX_UPLOAD_FILE_SIZE,
        MAX_UPLOAD_FILES,
    )
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    route = _build_route_with_manager(MagicMock())

    response = await KnowledgeBaseRoute.get_capabilities(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "upload": {
            "allowed_extensions": sorted(ALLOWED_UPLOAD_EXTENSIONS),
            "max_file_size_bytes": MAX_UPLOAD_FILE_SIZE,
            "max_files_per_upload": MAX_UPLOAD_FILES,
        },
        "defaults": {
            "chunk_size": DEFAULT_CHUNK_SIZE,
            "chunk_overlap": DEFAULT_CHUNK_OVERLAP,
            "batch_size": DEFAULT_UPLOAD_BATCH_SIZE,
            "tasks_limit": DEFAULT_UPLOAD_TASKS_LIMIT,
            "max_retries": DEFAULT_UPLOAD_MAX_RETRIES,
            "top_k_dense": DEFAULT_TOP_K_DENSE,
            "top_k_sparse": DEFAULT_TOP_K_SPARSE,
            "top_m_final": DEFAULT_TOP_M_FINAL,
            "index_type": DEFAULT_INDEX_TYPE,
        },
        "limits": {
            "max_retrieve_top_k": MAX_RETRIEVE_TOP_K,
            "max_batch_delete_documents": MAX_BATCH_DELETE_DOCUMENTS,
            "max_batch_rebuild_documents": MAX_BATCH_REBUILD_DOCUMENTS,
        },
        "pagination": {
            "document_page_size_options": list(DOCUMENT_PAGE_SIZE_OPTIONS),
            "chunk_page_size_options": list(CHUNK_PAGE_SIZE_OPTIONS),
            "default_kb_page_size": DEFAULT_KB_PAGE_SIZE,
            "default_document_page_size": DEFAULT_DOCUMENT_PAGE_SIZE,
            "default_chunk_page_size": DEFAULT_CHUNK_PAGE_SIZE,
            "bulk_page_size": DEFAULT_BULK_PAGE_SIZE,
        },
        "document_filters": {
            "statuses": list(DOCUMENT_FILTER_STATUSES),
            "source_types": list(DOCUMENT_FILTER_SOURCE_TYPES),
        },
        "features": {
            "sparse_retrieval": FEATURE_SPARSE_RETRIEVAL,
            "rerank": FEATURE_RERANK,
            "url_import": FEATURE_URL_IMPORT,
            "document_rebuild": FEATURE_DOCUMENT_REBUILD,
            "kb_rebuild": FEATURE_KB_REBUILD,
            "consistency_check": FEATURE_CONSISTENCY_CHECK,
            "consistency_repair": FEATURE_CONSISTENCY_REPAIR,
            "batch_delete": FEATURE_BATCH_DELETE,
            "batch_rebuild": FEATURE_BATCH_REBUILD,
        },
    }


def test_validate_upload_file_uses_configured_size_limit_in_message():
    from astrbot.core.knowledge_base.capabilities import MAX_UPLOAD_FILE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    with pytest.raises(ValueError, match="文件超过 .* 限制: too-large.md"):
        KnowledgeBaseRoute._validate_upload_file(
            "too-large.md",
            MAX_UPLOAD_FILE_SIZE + 1,
        )


@pytest.mark.asyncio
async def test_update_kb_omits_unprovided_rerank_provider_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=_build_kb_helper_with_options())
    kb_manager.update_kb = AsyncMock(return_value=_build_kb_helper())
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/update",
        method="POST",
        json={"kb_id": "kb-1", "chunk_size": 1024},
    ):
        response = await KnowledgeBaseRoute.update_kb(route)

    assert response["status"] == "ok"
    kwargs = kb_manager.update_kb.await_args.kwargs
    assert kwargs["kb_id"] == "kb-1"
    assert kwargs["chunk_size"] == 1024
    assert "rerank_provider_id" not in kwargs


@pytest.mark.asyncio
async def test_update_kb_explicit_null_forwards_rerank_provider_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=_build_kb_helper_with_options())
    kb_manager.update_kb = AsyncMock(return_value=_build_kb_helper(None))
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/update",
        method="POST",
        json={"kb_id": "kb-1", "rerank_provider_id": None},
    ):
        response = await KnowledgeBaseRoute.update_kb(route)

    assert response["status"] == "ok"
    kwargs = kb_manager.update_kb.await_args.kwargs
    assert kwargs["kb_id"] == "kb-1"
    assert kwargs["rerank_provider_id"] is None


@pytest.mark.asyncio
async def test_update_kb_rejects_overlap_not_less_than_chunk_size():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=_build_kb_helper_with_options())
    kb_manager.update_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/update",
        method="POST",
        json={"kb_id": "kb-1", "chunk_size": 100, "chunk_overlap": 100},
    ):
        response = await KnowledgeBaseRoute.update_kb(route)

    assert response["status"] == "error"
    assert "chunk_overlap" in response["message"]
    kb_manager.update_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_accepts_kb_ids():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock(return_value={"results": []})
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "top_k": 3},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "ok"
    kb_manager.retrieve.assert_awaited_once_with(
        query="hello",
        kb_names=None,
        kb_ids=["kb-1"],
        top_m_final=3,
        include_trace=False,
    )


@pytest.mark.asyncio
async def test_retrieve_includes_trace_when_requested():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    trace = {
        "dense": [{"rank": 1, "chunk_id": "chunk-1", "score": 0.9}],
        "sparse": [],
        "fusion": [],
        "rerank": [],
        "final": [],
    }
    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock(
        return_value={
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "doc_id": "doc-1",
                    "kb_id": "kb-1",
                    "kb_name": "kb",
                    "doc_name": "doc.md",
                    "chunk_index": 0,
                    "content": "hello",
                    "score": 0.9,
                    "char_count": 5,
                },
            ],
            "trace": trace,
        },
    )
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "top_k": 3, "trace": True},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "ok"
    assert response["data"]["trace"] == trace
    kb_manager.retrieve.assert_awaited_once_with(
        query="hello",
        kb_names=None,
        kb_ids=["kb-1"],
        top_m_final=3,
        include_trace=True,
    )


@pytest.mark.asyncio
async def test_retrieve_rejects_invalid_trace_flag():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "trace": "maybe"},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "error"
    assert "trace" in response["message"]
    kb_manager.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_rejects_invalid_top_k():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={"query": "hello", "kb_ids": ["kb-1"], "top_k": 0},
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "error"
    assert "top_k" in response["message"]
    kb_manager.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_retrieve_rejects_top_k_above_capability_limit():
    from astrbot.core.knowledge_base.capabilities import MAX_RETRIEVE_TOP_K
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.retrieve = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/retrieve",
        method="POST",
        json={
            "query": "hello",
            "kb_ids": ["kb-1"],
            "top_k": MAX_RETRIEVE_TOP_K + 1,
        },
    ):
        response = await KnowledgeBaseRoute.retrieve(route)

    assert response["status"] == "error"
    assert str(MAX_RETRIEVE_TOP_K) in response["message"]
    kb_manager.retrieve.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_kbs_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_KB_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb = MagicMock()
    kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "kb"}
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=[kb])
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/list",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    assert response["data"]["page"] == 1
    assert response["data"]["page_size"] == DEFAULT_KB_PAGE_SIZE
    assert response["data"]["total"] == 1


@pytest.mark.asyncio
async def test_list_kbs_returns_requested_page_and_total():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kbs = []
    for index in range(1, 6):
        kb = MagicMock()
        kb.kb_id = f"kb-{index}"
        kb.model_dump.return_value = {
            "kb_id": f"kb-{index}",
            "kb_name": f"kb {index}",
        }
        kbs.append(kb)
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=kbs)
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/list?page=2&page_size=2",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "items": [
            {"kb_id": "kb-3", "kb_name": "kb 3"},
            {"kb_id": "kb-4", "kb_name": "kb 4"},
        ],
        "page": 2,
        "page_size": 2,
        "total": 5,
    }
    kbs[0].model_dump.assert_not_called()
    kbs[1].model_dump.assert_not_called()
    kbs[4].model_dump.assert_not_called()


@pytest.mark.asyncio
async def test_list_kbs_refresh_stats_merges_database_stats():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb = MagicMock()
    kb.kb_id = "kb-1"
    kb.model_dump.return_value = {
        "kb_id": "kb-1",
        "kb_name": "kb",
        "doc_count": 1,
        "chunk_count": 2,
    }
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=[kb])
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(
        return_value={
            "kb_id": "kb-1",
            "kb_name": "kb",
            "document_count": 3,
            "ready_document_count": 2,
            "failed_document_count": 1,
            "indexed_chunk_count": 8,
            "document_chunk_count": 9,
            "storage_bytes": 1024,
            "status_counts": {"ready": 2, "failed": 1},
        },
    )
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/list?refresh_stats=true",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    item = response["data"]["items"][0]
    assert item["document_count"] == 3
    assert item["ready_document_count"] == 2
    assert item["failed_document_count"] == 1
    assert item["indexed_chunk_count"] == 8
    assert item["document_chunk_count"] == 9
    assert item["storage_bytes"] == 1024
    assert item["status_counts"] == {"ready": 2, "failed": 1}
    kb_db.get_kb_stats.assert_awaited_once_with("kb-1")


@pytest.mark.asyncio
async def test_list_kbs_skips_database_stats_without_refresh_flag():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb = MagicMock()
    kb.kb_id = "kb-1"
    kb.model_dump.return_value = {"kb_id": "kb-1", "kb_name": "kb"}
    kb_manager = MagicMock()
    kb_manager.list_kbs = AsyncMock(return_value=[kb])
    kb_manager.get_kb = AsyncMock(return_value=MagicMock(init_error=None))
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(return_value={})
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/list",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_kbs(route)

    assert response["status"] == "ok"
    assert response["data"]["items"] == [{"kb_id": "kb-1", "kb_name": "kb"}]
    kb_db.get_kb_stats.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_documents_returns_total_and_uses_requested_pagination():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    doc = MagicMock()
    doc.model_dump.return_value = {"doc_id": "doc-1", "doc_name": "alpha.md"}
    kb_helper.list_documents = AsyncMock(return_value=[doc])
    kb_helper.count_documents = AsyncMock(side_effect=[12, 123])
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&page=3&page_size=25&search=alpha&status=ready&source_type=file",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_documents(route)

    assert response["status"] == "ok"
    assert response["data"]["items"] == [{"doc_id": "doc-1", "doc_name": "alpha.md"}]
    assert response["data"]["page"] == 3
    assert response["data"]["page_size"] == 25
    assert response["data"]["total"] == 12
    assert response["data"]["filtered_total"] == 12
    assert response["data"]["document_count"] == 123
    kb_helper.list_documents.assert_awaited_once_with(
        offset=50,
        limit=25,
        search="alpha",
        status="ready",
        source_type="file",
    )
    assert kb_helper.count_documents.await_args_list[0].kwargs == {
        "search": "alpha",
        "status": "ready",
        "source_type": "file",
    }
    assert kb_helper.count_documents.await_args_list[1].args == ()
    assert kb_helper.count_documents.await_args_list[1].kwargs == {}


@pytest.mark.asyncio
async def test_list_documents_uses_total_as_document_count_without_search():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.list_documents = AsyncMock(return_value=[])
    kb_helper.count_documents = AsyncMock(return_value=7)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&page=1&page_size=25",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_documents(route)

    assert response["status"] == "ok"
    assert response["data"]["total"] == 7
    assert response["data"]["filtered_total"] == 7
    assert response["data"]["document_count"] == 7
    kb_helper.count_documents.assert_awaited_once_with(
        search=None,
        status=None,
        source_type=None,
    )


@pytest.mark.asyncio
async def test_list_documents_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_DOCUMENT_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.list_documents = AsyncMock(return_value=[])
    kb_helper.count_documents = AsyncMock(return_value=7)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_documents(route)

    assert response["status"] == "ok"
    assert response["data"]["page_size"] == DEFAULT_DOCUMENT_PAGE_SIZE
    kb_helper.list_documents.assert_awaited_once_with(
        offset=0,
        limit=DEFAULT_DOCUMENT_PAGE_SIZE,
        search=None,
        status=None,
        source_type=None,
    )


@pytest.mark.asyncio
async def test_list_documents_rejects_invalid_filters():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=MagicMock())
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&status=deleted",
        method="GET",
    ):
        invalid_status_response = await KnowledgeBaseRoute.list_documents(route)

    async with app.test_request_context(
        "/api/kb/document/list?kb_id=kb-1&source_type=database",
        method="GET",
    ):
        invalid_source_response = await KnowledgeBaseRoute.list_documents(route)

    assert invalid_status_response["status"] == "error"
    assert "status" in invalid_status_response["message"]
    assert invalid_source_response["status"] == "error"
    assert "source_type" in invalid_source_response["message"]


@pytest.mark.asyncio
async def test_get_document_rejects_other_kb_document():
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.models import KBDocument, KnowledgeBase
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = KBHelper.__new__(KBHelper)
    kb_helper.kb = KnowledgeBase(
        kb_id="kb-1",
        kb_name="kb",
        embedding_provider_id="emb-1",
    )
    kb_helper.kb_db = MagicMock()
    kb_helper.kb_db.get_document_by_id = AsyncMock(
        return_value=KBDocument(
            doc_id="doc-1",
            kb_id="kb-2",
            doc_name="doc.md",
            file_type="md",
            file_size=1,
            file_path="",
            status="ready",
        ),
    )
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/get?kb_id=kb-1&doc_id=doc-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_document(route)

    assert response["status"] == "error"
    assert response["message"] == "文档不存在"
    kb_helper.kb_db.get_document_by_id.assert_awaited_once_with("doc-1")


@pytest.mark.asyncio
async def test_list_chunks_forwards_search_and_total():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.search_chunks_by_doc_id = AsyncMock(
        return_value=([{"chunk_id": "c1"}], 7),
    )
    kb_helper.get_chunk_count_by_doc_id = AsyncMock(return_value=42)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/list?kb_id=kb-1&doc_id=doc-1&page=2&page_size=3&search=hello",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_chunks(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "items": [{"chunk_id": "c1"}],
        "page": 2,
        "page_size": 3,
        "total": 7,
        "filtered_total": 7,
        "document_chunk_count": 42,
    }
    kb_helper.search_chunks_by_doc_id.assert_awaited_once_with(
        doc_id="doc-1",
        search="hello",
        offset=3,
        limit=3,
    )
    kb_helper.get_chunk_count_by_doc_id.assert_awaited_once_with("doc-1")


@pytest.mark.asyncio
async def test_list_chunks_uses_filtered_total_as_document_chunk_count_without_search():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.search_chunks_by_doc_id = AsyncMock(
        return_value=([{"chunk_id": "c1"}], 7),
    )
    kb_helper.get_chunk_count_by_doc_id = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/list?kb_id=kb-1&doc_id=doc-1&page=1&page_size=10",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_chunks(route)

    assert response["status"] == "ok"
    assert response["data"]["total"] == 7
    assert response["data"]["filtered_total"] == 7
    assert response["data"]["document_chunk_count"] == 7
    kb_helper.get_chunk_count_by_doc_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_chunks_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_CHUNK_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.search_chunks_by_doc_id = AsyncMock(return_value=([], 0))
    kb_helper.get_chunk_count_by_doc_id = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/list?kb_id=kb-1&doc_id=doc-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_chunks(route)

    assert response["status"] == "ok"
    assert response["data"]["page_size"] == DEFAULT_CHUNK_PAGE_SIZE
    kb_helper.search_chunks_by_doc_id.assert_awaited_once_with(
        doc_id="doc-1",
        search=None,
        offset=0,
        limit=DEFAULT_CHUNK_PAGE_SIZE,
    )


@pytest.mark.asyncio
async def test_get_chunk_context_returns_helper_context():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.get_chunk_context = AsyncMock(
        return_value={
            "previous": None,
            "current": {"chunk_id": "chunk-1"},
            "next": {"chunk_id": "chunk-2"},
        },
    )
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/context?kb_id=kb-1&doc_id=doc-1&chunk_id=chunk-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_chunk_context(route)

    assert response["status"] == "ok"
    assert response["data"]["current"] == {"chunk_id": "chunk-1"}
    kb_manager.get_kb.assert_awaited_once_with("kb-1")
    kb_helper.get_chunk_context.assert_awaited_once_with(
        chunk_id="chunk-1",
        doc_id="doc-1",
    )


@pytest.mark.asyncio
async def test_get_chunk_context_requires_chunk_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/chunk/context?kb_id=kb-1&doc_id=doc-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_chunk_context(route)

    assert response["status"] == "error"
    assert response["message"] == "缺少参数 chunk_id"
    kb_manager.get_kb.assert_not_called()


@pytest.mark.asyncio
async def test_get_kb_stats_returns_extended_database_stats():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = _build_kb_helper_with_options(kb_id="kb-1", kb_name="kb")
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(
        return_value={
            "kb_id": "kb-1",
            "kb_name": "kb",
            "doc_count": 3,
            "chunk_count": 8,
            "document_count": 3,
            "ready_document_count": 2,
            "failed_document_count": 1,
            "pending_document_count": 0,
            "processing_document_count": 0,
            "indexed_chunk_count": 8,
            "document_chunk_count": 8,
            "media_count": 1,
            "source_file_count": 1,
            "storage_bytes": 17,
            "status_counts": {"ready": 2, "failed": 1},
            "created_at": "2026-06-01T00:00:00+00:00",
            "updated_at": "2026-06-01T00:00:00+00:00",
        },
    )
    kb_manager.kb_db = kb_db
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/stats?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_kb_stats(route)

    assert response["status"] == "ok"
    assert response["data"]["document_count"] == 3
    assert response["data"]["ready_document_count"] == 2
    assert response["data"]["failed_document_count"] == 1
    assert response["data"]["source_file_count"] == 1
    assert response["data"]["storage_bytes"] == 17
    assert response["data"]["status_counts"] == {"ready": 2, "failed": 1}
    kb_db.get_kb_stats.assert_awaited_once_with("kb-1")


@pytest.mark.asyncio
async def test_get_kb_stats_fallback_keeps_extended_schema():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = _build_kb_helper_with_options(kb_id="kb-1", kb_name="kb")
    kb_helper.kb.doc_count = 3
    kb_helper.kb.chunk_count = 8
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    kb_db = MagicMock()
    kb_db.get_kb_stats = AsyncMock(return_value=None)
    route = _build_route_with_manager(kb_manager)
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/stats?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_kb_stats(route)

    assert response["status"] == "ok"
    assert response["data"]["document_count"] == 3
    assert response["data"]["ready_document_count"] == 3
    assert response["data"]["indexed_chunk_count"] == 8
    assert response["data"]["document_chunk_count"] == 8
    assert response["data"]["media_count"] == 0
    assert response["data"]["source_file_count"] == 0
    assert response["data"]["storage_bytes"] == 0
    assert response["data"]["status_counts"] == {"ready": 3}
    kb_db.get_kb_stats.assert_awaited_once_with("kb-1")


@pytest.mark.asyncio
async def test_check_kb_consistency_returns_helper_report():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    report = {
        "kb_id": "kb-1",
        "summary": {"healthy": False, "missing_vectors": 1},
        "issues": {"missing_vectors": [{"doc_id": "doc-1"}]},
    }
    kb_helper = MagicMock()
    kb_helper.check_consistency = AsyncMock(return_value=report)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/check?kb_id=kb-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.check_kb_consistency(route)

    assert response["status"] == "ok"
    assert response["data"] == report
    kb_manager.get_kb.assert_awaited_once_with("kb-1")
    kb_helper.check_consistency.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_check_kb_consistency_requires_existing_kb():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=None)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/check?kb_id=missing-kb",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.check_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "知识库不存在"
    kb_manager.get_kb.assert_awaited_once_with("missing-kb")


@pytest.mark.asyncio
async def test_repair_kb_consistency_returns_helper_report():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    report = {
        "kb_id": "kb-1",
        "summary": {"repaired_count": 1, "failed_count": 0},
        "actions": {"repaired": [{"type": "orphan_vectors"}]},
    }
    kb_helper = MagicMock()
    kb_helper.repair_consistency = AsyncMock(return_value=report)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={
            "kb_id": "kb-1",
            "repair_types": ["orphan_vectors"],
        },
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "ok"
    assert response["data"] == report
    kb_manager.get_kb.assert_awaited_once_with("kb-1")
    kb_helper.repair_consistency.assert_awaited_once_with(
        repair_types=["orphan_vectors"],
    )


@pytest.mark.asyncio
async def test_repair_kb_consistency_requires_existing_kb():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=None)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={"kb_id": "missing-kb"},
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "知识库不存在"
    kb_manager.get_kb.assert_awaited_once_with("missing-kb")


@pytest.mark.asyncio
async def test_repair_kb_consistency_rejects_invalid_repair_types():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={"kb_id": "kb-1", "repair_types": "orphan_vectors"},
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "repair_types 格式错误"
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_repair_kb_consistency_returns_helper_validation_errors():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.repair_consistency = AsyncMock(
        side_effect=ValueError("不支持的一致性修复类型: invalid"),
    )
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/consistency/repair",
        method="POST",
        json={"kb_id": "kb-1", "repair_types": ["invalid"]},
    ):
        response = await KnowledgeBaseRoute.repair_kb_consistency(route)

    assert response["status"] == "error"
    assert response["message"] == "不支持的一致性修复类型: invalid"
    kb_helper.repair_consistency.assert_awaited_once_with(
        repair_types=["invalid"],
    )


@pytest.mark.asyncio
async def test_get_upload_progress_falls_back_to_persistent_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route.upload_tasks = {}
    route.upload_progress = {}
    route._get_persistent_task = AsyncMock(
        return_value={
            "task_id": "task-1",
            "status": "completed",
            "progress_stage": "embedding",
            "progress_current": 5,
            "progress_total": 5,
            "progress": {"stage": "embedding", "current": 5, "total": 5},
            "result": {"success_count": 1},
            "error": None,
        },
    )

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": "completed",
        "progress_stage": "embedding",
        "progress_current": 5,
        "progress_total": 5,
        "progress": {"stage": "embedding", "current": 5, "total": 5},
        "result": {"success_count": 1},
    }
    route._get_persistent_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_get_upload_progress_returns_flattened_persistent_progress():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route.upload_tasks = {}
    route.upload_progress = {}
    route._get_persistent_task = AsyncMock(
        return_value={
            "task_id": "task-1",
            "status": "processing",
            "progress_stage": "chunking",
            "progress_current": 2,
            "progress_total": 8,
            "progress": None,
            "result": None,
            "error": None,
        },
    )

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": "processing",
        "progress_stage": "chunking",
        "progress_current": 2,
        "progress_total": 8,
    }
    route._get_persistent_task.assert_awaited_once_with("task-1")


def test_get_persistent_progress_updates_includes_flattened_fields():
    route = _build_route_with_manager(MagicMock())
    route.upload_progress = {
        "task-1": {
            "status": "completed",
            "stage": "completed",
            "current": 3,
            "total": 3,
        },
    }

    assert route._get_persistent_progress_updates("task-1") == {
        "progress_stage": "completed",
        "progress_current": 3,
        "progress_total": 3,
        "progress": {
            "status": "completed",
            "stage": "completed",
            "current": 3,
            "total": 3,
        },
    }
    assert route._get_persistent_progress_updates("missing-task") == {}


def test_batch_task_status_and_error_helpers_report_partial_failures():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    failed_docs = [
        {"file_name": "a.md", "error": "a.md: fail"},
        {"file_name": "b.md", "error": "b.md: fail"},
    ]

    assert KnowledgeBaseRoute._resolve_batch_task_status(2, 0) == "completed"
    assert KnowledgeBaseRoute._resolve_batch_task_status(0, 2) == "failed"
    assert KnowledgeBaseRoute._resolve_batch_task_status(1, 2) == "partial_failed"
    assert (
        KnowledgeBaseRoute._build_batch_failure_error(
            failed_docs,
            success_count=1,
            action="导入",
        )
        == "部分文档导入失败，共 2 个失败。"
    )
    assert (
        KnowledgeBaseRoute._build_batch_failure_error(
            failed_docs,
            success_count=0,
            action="导入",
        )
        == "所有文档导入失败，共 2 个失败。"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "uploaded", "total", "success_count", "progress"),
    [
        (
            "failed",
            [],
            1,
            0,
            {"status": "failed", "stage": "parsing", "current": 0, "total": 100},
        ),
        (
            "partial_failed",
            [{"doc_id": "doc-1"}],
            2,
            1,
            {
                "status": "partial_failed",
                "stage": "completed",
                "current": 2,
                "total": 2,
            },
        ),
    ],
)
async def test_get_upload_progress_returns_terminal_task_result_from_memory(
    status: str,
    uploaded: list[dict],
    total: int,
    success_count: int,
    progress: dict,
):
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    result = {
        "task_id": "task-1",
        "uploaded": uploaded,
        "failed": [{"file_name": "same.md", "error": "same.md: duplicate"}],
        "total": total,
        "success_count": success_count,
        "failed_count": 1,
    }
    route.upload_tasks = {
        "task-1": {
            "status": status,
            "result": result,
            "error": "same.md: duplicate",
        },
    }
    route.upload_progress = {"task-1": progress}
    route._cleanup_task = MagicMock()

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": status,
        "result": result,
        "error": "same.md: duplicate",
    }
    route._cleanup_task.assert_called_once_with("task-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "status",
        "uploaded",
        "total",
        "success_count",
        "progress_stage",
        "progress_current",
        "progress_total",
    ),
    [
        ("failed", [], 1, 0, "parsing", 0, 100),
        ("partial_failed", [{"doc_id": "doc-1"}], 2, 1, "completed", 2, 2),
    ],
)
async def test_get_upload_progress_returns_terminal_persistent_task_result(
    status: str,
    uploaded: list[dict],
    total: int,
    success_count: int,
    progress_stage: str,
    progress_current: int,
    progress_total: int,
):
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route.upload_tasks = {}
    route.upload_progress = {}
    result = {
        "task_id": "task-1",
        "uploaded": uploaded,
        "failed": [{"file_name": "same.md", "error": "same.md: duplicate"}],
        "total": total,
        "success_count": success_count,
        "failed_count": 1,
    }
    route._get_persistent_task = AsyncMock(
        return_value={
            "task_id": "task-1",
            "status": status,
            "progress_stage": progress_stage,
            "progress_current": progress_current,
            "progress_total": progress_total,
            "progress": {
                "stage": progress_stage,
                "current": progress_current,
                "total": progress_total,
            },
            "result": result,
            "error": "same.md: duplicate",
        },
    )

    async with app.test_request_context(
        "/api/kb/document/upload/progress?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_upload_progress(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "status": status,
        "progress_stage": progress_stage,
        "progress_current": progress_current,
        "progress_total": progress_total,
        "progress": {
            "stage": progress_stage,
            "current": progress_current,
            "total": progress_total,
        },
        "result": result,
        "error": "same.md: duplicate",
    }
    route._get_persistent_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_get_task_returns_persistent_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route._get_persistent_task = AsyncMock(
        return_value={"task_id": "task-1", "status": "completed"},
    )

    async with app.test_request_context(
        "/api/kb/task/get?task_id=task-1",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_task(route)

    assert response["status"] == "ok"
    assert response["data"] == {"task_id": "task-1", "status": "completed"}
    route._get_persistent_task.assert_awaited_once_with("task-1")


@pytest.mark.asyncio
async def test_get_task_requires_task_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    route = _build_route_with_manager(MagicMock())
    route._get_persistent_task = AsyncMock()

    async with app.test_request_context(
        "/api/kb/task/get",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.get_task(route)

    assert response["status"] == "error"
    assert "task_id" in response["message"]
    route._get_persistent_task.assert_not_awaited()


@pytest.mark.asyncio
async def test_list_tasks_forwards_filters_and_pagination():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_db = MagicMock()
    kb_db.list_ingestion_tasks = AsyncMock(
        return_value=[{"task_id": "task-1", "status": "completed"}],
    )
    kb_db.count_ingestion_tasks = AsyncMock(return_value=76)
    route = _build_route_with_manager(MagicMock())
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/task/list?kb_id=kb-1&status=completed&task_type=upload&page=3&page_size=25",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_tasks(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "items": [{"task_id": "task-1", "status": "completed"}],
        "total": 76,
        "page": 3,
        "page_size": 25,
    }
    kb_db.list_ingestion_tasks.assert_awaited_once_with(
        kb_id="kb-1",
        status="completed",
        task_type="upload",
        offset=50,
        limit=25,
    )
    kb_db.count_ingestion_tasks.assert_awaited_once_with(
        kb_id="kb-1",
        status="completed",
        task_type="upload",
    )


@pytest.mark.asyncio
async def test_list_tasks_uses_capability_default_page_size():
    from astrbot.core.knowledge_base.capabilities import DEFAULT_DOCUMENT_PAGE_SIZE
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_db = MagicMock()
    kb_db.list_ingestion_tasks = AsyncMock(return_value=[])
    kb_db.count_ingestion_tasks = AsyncMock(return_value=0)
    route = _build_route_with_manager(MagicMock())
    route._get_kb_db = MagicMock(return_value=kb_db)

    async with app.test_request_context(
        "/api/kb/task/list",
        method="GET",
    ):
        response = await KnowledgeBaseRoute.list_tasks(route)

    assert response["status"] == "ok"
    assert response["data"]["page_size"] == DEFAULT_DOCUMENT_PAGE_SIZE
    kb_db.list_ingestion_tasks.assert_awaited_once_with(
        kb_id=None,
        status=None,
        task_type=None,
        offset=0,
        limit=DEFAULT_DOCUMENT_PAGE_SIZE,
    )


@pytest.mark.asyncio
async def test_rebuild_document_route_forwards_options():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    doc = MagicMock()
    doc.model_dump.return_value = {
        "doc_id": "new-doc",
        "parent_doc_id": "old-doc",
        "version": 2,
    }
    kb_helper.rebuild_document = AsyncMock(return_value=doc)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_id": "old-doc",
            "chunk_size": 256,
            "chunk_overlap": 32,
            "batch_size": 4,
            "tasks_limit": 2,
            "max_retries": 1,
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "ok"
    assert response["data"]["doc_id"] == "new-doc"
    kb_helper.rebuild_document.assert_awaited_once_with(
        "old-doc",
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )


@pytest.mark.asyncio
async def test_rebuild_document_route_can_start_background_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.rebuild_document = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)
    route.upload_tasks = {}
    route.upload_progress = {}
    route._create_persistent_task = AsyncMock()
    background_call = object()
    route._background_rebuild_document_task = MagicMock(return_value=background_call)

    with (
        patch(
            "astrbot.dashboard.routes.knowledge_base.uuid.uuid4",
            return_value="task-1",
        ),
        patch(
            "astrbot.dashboard.routes.knowledge_base.asyncio.create_task"
        ) as create_task,
    ):
        async with app.test_request_context(
            "/api/kb/document/rebuild",
            method="POST",
            json={
                "kb_id": "kb-1",
                "doc_id": "old-doc",
                "chunk_size": 256,
                "chunk_overlap": 32,
                "batch_size": 4,
                "tasks_limit": 2,
                "max_retries": 1,
                "background": True,
            },
        ):
            response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "doc_id": "old-doc",
        "message": "document rebuild task created, processing in background",
    }
    assert route.upload_tasks["task-1"]["status"] == "pending"
    route._create_persistent_task.assert_awaited_once_with(
        task_id="task-1",
        kb_id="kb-1",
        task_type="document_rebuild",
        status="pending",
        progress={
            "status": "pending",
            "file_index": 0,
            "file_total": 1,
            "file_name": "old-doc",
            "stage": "waiting",
            "current": 0,
            "total": 100,
        },
    )
    route._background_rebuild_document_task.assert_called_once_with(
        task_id="task-1",
        kb_helper=kb_helper,
        doc_id="old-doc",
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )
    create_task.assert_called_once_with(background_call)
    kb_helper.rebuild_document.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_document_route_rejects_invalid_background_flag():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_id": "doc-1",
            "background": "later",
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "error"
    assert "background" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_document_route_rejects_invalid_options():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_id": "doc-1",
            "chunk_size": 10,
            "chunk_overlap": 10,
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_document(route)

    assert response["status"] == "error"
    assert "chunk_overlap" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_kb_route_forwards_options():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.rebuild_all_documents = AsyncMock(
        return_value={
            "total": 1,
            "success_count": 1,
            "failed_count": 0,
            "rebuilt": [{"doc_id": "doc-new"}],
            "failed": [],
        },
    )
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "chunk_size": 256,
            "chunk_overlap": 32,
            "batch_size": 4,
            "tasks_limit": 2,
            "max_retries": 1,
        },
    ):
        response = await KnowledgeBaseRoute.rebuild_kb(route)

    assert response["status"] == "ok"
    assert response["data"]["success_count"] == 1
    kb_helper.rebuild_all_documents.assert_awaited_once_with(
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )


@pytest.mark.asyncio
async def test_rebuild_kb_route_can_start_background_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = _build_kb_helper_with_options(kb_id="kb-1", kb_name="docs")
    kb_helper.rebuild_all_documents = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)
    route.upload_tasks = {}
    route.upload_progress = {}
    route._create_persistent_task = AsyncMock()
    background_call = object()
    route._background_rebuild_kb_task = MagicMock(return_value=background_call)

    with (
        patch(
            "astrbot.dashboard.routes.knowledge_base.uuid.uuid4",
            return_value="task-1",
        ),
        patch(
            "astrbot.dashboard.routes.knowledge_base.asyncio.create_task"
        ) as create_task,
    ):
        async with app.test_request_context(
            "/api/kb/rebuild",
            method="POST",
            json={
                "kb_id": "kb-1",
                "chunk_size": 256,
                "chunk_overlap": 32,
                "batch_size": 4,
                "tasks_limit": 2,
                "max_retries": 1,
                "background": True,
            },
        ):
            response = await KnowledgeBaseRoute.rebuild_kb(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "kb_id": "kb-1",
        "message": "knowledge base rebuild task created, processing in background",
    }
    assert route.upload_tasks["task-1"]["status"] == "pending"
    route._create_persistent_task.assert_awaited_once_with(
        task_id="task-1",
        kb_id="kb-1",
        task_type="kb_rebuild",
        status="pending",
        progress={
            "status": "pending",
            "file_index": 0,
            "file_total": 1,
            "file_name": "docs",
            "stage": "waiting",
            "current": 0,
            "total": 100,
        },
    )
    route._background_rebuild_kb_task.assert_called_once_with(
        task_id="task-1",
        kb_helper=kb_helper,
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )
    create_task.assert_called_once_with(background_call)
    kb_helper.rebuild_all_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_rebuild_kb_route_requires_kb_id():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/rebuild",
        method="POST",
        json={},
    ):
        response = await KnowledgeBaseRoute.rebuild_kb(route)

    assert response["status"] == "error"
    assert "kb_id" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_rebuild_documents_route_starts_background_task():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_helper = MagicMock()
    kb_helper.rebuild_documents = AsyncMock()
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock(return_value=kb_helper)
    route = _build_route_with_manager(kb_manager)
    route.upload_tasks = {}
    route.upload_progress = {}
    route._create_persistent_task = AsyncMock()
    background_call = object()
    route._background_rebuild_documents_task = MagicMock(
        return_value=background_call,
    )

    with (
        patch(
            "astrbot.dashboard.routes.knowledge_base.uuid.uuid4",
            return_value="task-1",
        ),
        patch(
            "astrbot.dashboard.routes.knowledge_base.asyncio.create_task"
        ) as create_task,
    ):
        async with app.test_request_context(
            "/api/kb/document/batch-rebuild",
            method="POST",
            json={
                "kb_id": "kb-1",
                "doc_ids": ["doc-1", "doc-2", "doc-1"],
                "chunk_size": 256,
                "chunk_overlap": 32,
                "batch_size": 4,
                "tasks_limit": 2,
                "max_retries": 1,
            },
        ):
            response = await KnowledgeBaseRoute.batch_rebuild_documents(route)

    assert response["status"] == "ok"
    assert response["data"] == {
        "task_id": "task-1",
        "doc_ids": ["doc-1", "doc-2"],
        "message": "document batch rebuild task created, processing in background",
    }
    assert route.upload_tasks["task-1"]["status"] == "pending"
    route._create_persistent_task.assert_awaited_once_with(
        task_id="task-1",
        kb_id="kb-1",
        task_type="document_batch_rebuild",
        status="pending",
        progress={
            "status": "pending",
            "file_index": 0,
            "file_total": 2,
            "file_name": "2 selected documents",
            "stage": "waiting",
            "current": 0,
            "total": 2,
        },
    )
    route._background_rebuild_documents_task.assert_called_once_with(
        task_id="task-1",
        kb_helper=kb_helper,
        doc_ids=["doc-1", "doc-2"],
        chunk_size=256,
        chunk_overlap=32,
        batch_size=4,
        tasks_limit=2,
        max_retries=1,
    )
    create_task.assert_called_once_with(background_call)
    kb_helper.rebuild_documents.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_rebuild_documents_route_rejects_invalid_doc_ids():
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/batch-rebuild",
        method="POST",
        json={"kb_id": "kb-1", "doc_ids": []},
    ):
        response = await KnowledgeBaseRoute.batch_rebuild_documents(route)

    assert response["status"] == "error"
    assert "doc_ids" in response["message"]
    kb_manager.get_kb.assert_not_awaited()


@pytest.mark.asyncio
async def test_batch_rebuild_documents_route_rejects_limit_excess():
    from astrbot.core.knowledge_base.capabilities import MAX_BATCH_REBUILD_DOCUMENTS
    from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

    app = Quart(__name__)
    kb_manager = MagicMock()
    kb_manager.get_kb = AsyncMock()
    route = _build_route_with_manager(kb_manager)

    async with app.test_request_context(
        "/api/kb/document/batch-rebuild",
        method="POST",
        json={
            "kb_id": "kb-1",
            "doc_ids": [
                f"doc-{index}" for index in range(MAX_BATCH_REBUILD_DOCUMENTS + 1)
            ],
        },
    ):
        response = await KnowledgeBaseRoute.batch_rebuild_documents(route)

    assert response["status"] == "error"
    assert str(MAX_BATCH_REBUILD_DOCUMENTS) in response["message"]
    kb_manager.get_kb.assert_not_awaited()


# --- Merged from tests/test_kb_upload_memory_leak.py ---

"""Tests for #1: Memory leak fix in upload_tasks / upload_progress.

Verifies:
- Completed/failed tasks are cleaned up on poll (get_upload_progress)
- Processing/pending tasks are NOT cleaned up
- Delayed cleanup is scheduled by background tasks (finally block)
- Delayed cleanup actually removes after sleep
- Cleanup is idempotent
- CancelledError is handled gracefully
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest


def _persistent_progress_kwargs(progress: dict) -> dict:
    return {
        "progress_stage": progress.get("stage"),
        "progress_current": progress.get("current"),
        "progress_total": progress.get("total"),
        "progress": progress,
    }


class TestUploadTaskCleanup:
    """Verify task cleanup in get_upload_progress."""

    @pytest.mark.asyncio
    async def test_create_persistent_task_writes_to_kb_db(self):
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        kb_db = MagicMock()
        kb_db.create_ingestion_task = AsyncMock()
        route._get_kb_db = MagicMock(return_value=kb_db)

        await route._create_persistent_task(
            task_id="task-1",
            kb_id="kb-1",
            task_type="upload",
            status="pending",
            progress={
                "stage": "waiting",
                "current": 0,
                "total": 100,
            },
        )

        kb_db.create_ingestion_task.assert_awaited_once_with(
            task_id="task-1",
            kb_id="kb-1",
            task_type="upload",
            status="pending",
            progress_stage="waiting",
            progress_current=0,
            progress_total=100,
            progress={
                "stage": "waiting",
                "current": 0,
                "total": 100,
            },
        )

    @pytest.mark.asyncio
    async def test_persist_progress_updates_kb_db_from_memory(self):
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_progress = {
            "task-1": {
                "status": "processing",
                "stage": "embedding",
                "current": 2,
                "total": 5,
            },
        }
        route._update_persistent_task = AsyncMock()

        await route._persist_progress("task-1")

        route._update_persistent_task.assert_awaited_once_with(
            "task-1",
            status="processing",
            progress_stage="embedding",
            progress_current=2,
            progress_total=5,
            progress={
                "status": "processing",
                "stage": "embedding",
                "current": 2,
                "total": 5,
            },
        )

    def test_format_failed_doc_error_only_skips_exact_file_prefix(self):
        """File names that are only a prefix of another word still get prepended."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        assert (
            KnowledgeBaseRoute._format_failed_doc_error(
                "doc",
                ValueError("document parse error"),
            )
            == "doc: document parse error"
        )
        assert (
            KnowledgeBaseRoute._format_failed_doc_error(
                "doc",
                ValueError("doc: parse error"),
            )
            == "doc: parse error"
        )

    def test_build_batch_failure_error_uses_single_document_reason(self):
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        assert (
            KnowledgeBaseRoute._build_batch_failure_error(
                [{"file_name": "doc.md", "error": "doc.md: duplicate"}],
            )
            == "doc.md: duplicate"
        )
        assert KnowledgeBaseRoute._build_batch_failure_error([]) is None

    @pytest.mark.asyncio
    async def test_cleanup_on_completed_poll(self):
        """Completed task cleaned up when client polls for result."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {
            "task-1": {
                "status": "completed",
                "result": {"uploaded": []},
                "error": None,
            },
        }
        route.upload_progress = {
            "task-1": {"status": "completed", "file_index": 0, "file_total": 1},
        }

        route._cleanup_task("task-1")

        assert "task-1" not in route.upload_tasks
        assert "task-1" not in route.upload_progress

    @pytest.mark.asyncio
    async def test_cleanup_on_failed_poll(self):
        """Failed task cleaned up when client polls for result."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {
            "task-1": {
                "status": "failed",
                "result": None,
                "error": "upload failed",
            },
        }
        route.upload_progress = {
            "task-1": {"status": "failed", "file_index": 0, "file_total": 1},
        }

        route._cleanup_task("task-1")

        assert "task-1" not in route.upload_tasks
        assert "task-1" not in route.upload_progress

    def test_no_cleanup_for_processing(self):
        """_cleanup_task only removes what it's told — caller decides status filter."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {
            "task-1": {"status": "processing", "result": None, "error": None},
        }
        route.upload_progress = {
            "task-1": {"status": "processing", "file_index": 1, "file_total": 5},
        }

        # _cleanup_task is status-agnostic; the caller (get_upload_progress)
        # only calls it for completed/failed.  This test verifies that
        # processing entries CAN be cleaned up by the method, not that
        # get_upload_progress cleans them up.
        route._cleanup_task("task-1")

        assert "task-1" not in route.upload_tasks
        assert "task-1" not in route.upload_progress

    def test_cleanup_task_idempotent(self):
        """Calling _cleanup_task twice is safe (idempotent)."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {"task-1": {}}
        route.upload_progress = {"task-1": {}}

        route._cleanup_task("task-1")
        route._cleanup_task("task-1")  # second call should not raise
        route._cleanup_task("never-existed")  # non-existent should not raise

        assert "task-1" not in route.upload_tasks
        assert "task-1" not in route.upload_progress

    @pytest.mark.asyncio
    async def test_delayed_cleanup_removes_after_sleep(self):
        """_schedule_delayed_cleanup removes task after delay."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {"task-1": {"status": "completed"}}
        route.upload_progress = {"task-1": {"status": "completed"}}

        # Use a very short delay for test
        await route._schedule_delayed_cleanup("task-1", delay_seconds=0.01)

        assert "task-1" not in route.upload_tasks
        assert "task-1" not in route.upload_progress

    @pytest.mark.asyncio
    async def test_delayed_cleanup_idempotent(self):
        """Delayed cleanup is safe even if task already removed by poll."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}

        # Should not raise even though task doesn't exist
        await route._schedule_delayed_cleanup("task-1", delay_seconds=0.01)

    @pytest.mark.asyncio
    async def test_delayed_cleanup_cancelled_error_graceful(self):
        """CancelledError inside _schedule_delayed_cleanup is caught, task not cleaned."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {"task-1": {"status": "completed"}}
        route.upload_progress = {"task-1": {"status": "completed"}}

        # Create the cleanup task
        cleanup_task = asyncio.create_task(
            route._schedule_delayed_cleanup("task-1", delay_seconds=10)
        )
        await asyncio.sleep(0.02)  # let it start sleeping
        cleanup_task.cancel()

        # The outer task will get CancelledError, but the inner method catches it
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass  # the asyncio.create_task wrapper gets cancelled

        # Since CancelledError was caught internally and returned early,
        # the task data should still be there
        assert "task-1" in route.upload_tasks
        assert "task-1" in route.upload_progress

    # ── Background task finally-block tests ──

    @pytest.mark.asyncio
    async def test_background_upload_schedules_cleanup_on_success(self):
        """_background_upload_task schedules delayed cleanup in finally block."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._init_task = MagicMock()
        route._set_task_result = MagicMock()
        route._update_progress = MagicMock()
        route._make_progress_callback = MagicMock(return_value=AsyncMock())
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.upload_document = AsyncMock(
            return_value=MagicMock(
                model_dump=MagicMock(return_value={"doc_id": "doc-1"}),
            )
        )

        files = [
            {"file_name": "test.txt", "file_content": b"hello", "file_type": "txt"}
        ]

        await route._background_upload_task(
            task_id="task-1",
            kb_helper=kb_helper,
            files_to_upload=files,
            chunk_size=512,
            chunk_overlap=50,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        # The finally block should have triggered _cleanup_task via
        # the asyncio.create_task(_schedule_delayed_cleanup) call.
        # Since we used a real async sleep of 0, the task should complete.
        await asyncio.sleep(0.05)
        route._cleanup_task.assert_called_with("task-1")

    @pytest.mark.asyncio
    async def test_background_upload_schedules_cleanup_on_failure(self):
        """Finally block still runs even when task fails."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._init_task = MagicMock()
        route._set_task_result = MagicMock()
        route._update_progress = MagicMock()
        route._make_progress_callback = MagicMock(return_value=AsyncMock())
        route._cleanup_task = MagicMock()
        route._format_failed_doc_error = MagicMock(return_value="test error")

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.upload_document = AsyncMock(
            side_effect=RuntimeError("upload exploded"),
        )

        files = [
            {"file_name": "test.txt", "file_content": b"hello", "file_type": "txt"}
        ]

        await route._background_upload_task(
            task_id="task-1",
            kb_helper=kb_helper,
            files_to_upload=files,
            chunk_size=512,
            chunk_overlap=50,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)
        route._cleanup_task.assert_called_with("task-1")

    @pytest.mark.asyncio
    async def test_background_upload_marks_task_failed_when_all_files_fail(self):
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._update_persistent_task = AsyncMock()
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.upload_document = AsyncMock(
            side_effect=RuntimeError("重复文档：same.md 已存在"),
        )

        files = [{"file_name": "same.md", "file_content": b"same", "file_type": "md"}]

        await route._background_upload_task(
            task_id="task-dup",
            kb_helper=kb_helper,
            files_to_upload=files,
            chunk_size=512,
            chunk_overlap=50,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)

        result = route.upload_tasks["task-dup"]["result"]
        error = route.upload_tasks["task-dup"]["error"]
        assert route.upload_tasks["task-dup"]["status"] == "failed"
        assert result["success_count"] == 0
        assert result["failed_count"] == 1
        assert result["failed"][0]["error"] == ("same.md: 重复文档：same.md 已存在")
        assert error == "same.md: 重复文档：same.md 已存在"
        route._update_persistent_task.assert_any_await(
            "task-dup",
            status="failed",
            result=result,
            error=error,
            **_persistent_progress_kwargs(route.upload_progress["task-dup"]),
        )
        route._cleanup_task.assert_called_with("task-dup")

    @pytest.mark.asyncio
    async def test_background_import_schedules_cleanup(self):
        """_background_import_task schedules delayed cleanup in finally block."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._init_task = MagicMock()
        route._set_task_result = MagicMock()
        route._update_progress = MagicMock()
        route._make_progress_callback = MagicMock(return_value=AsyncMock())
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.upload_document = AsyncMock(
            return_value=MagicMock(
                model_dump=MagicMock(return_value={"doc_id": "doc-1"}),
            )
        )

        documents = [{"file_name": "test.txt", "chunks": ["chunk 1", "chunk 2"]}]

        await route._background_import_task(
            task_id="task-2",
            kb_helper=kb_helper,
            documents=documents,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)
        route._cleanup_task.assert_called_with("task-2")

    @pytest.mark.asyncio
    async def test_background_url_upload_schedules_cleanup(self):
        """_background_upload_from_url_task schedules delayed cleanup."""
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._init_task = MagicMock()
        route._set_task_result = MagicMock()
        route._update_progress = MagicMock()
        route._make_progress_callback = MagicMock(return_value=AsyncMock())
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.upload_from_url = AsyncMock(
            return_value=MagicMock(
                model_dump=MagicMock(return_value={"doc_id": "doc-1"}),
            )
        )

        await route._background_upload_from_url_task(
            task_id="task-3",
            kb_helper=kb_helper,
            url="https://example.com",
            chunk_size=512,
            chunk_overlap=50,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
            enable_cleaning=False,
            cleaning_provider_id=None,
        )

        await asyncio.sleep(0.05)
        route._cleanup_task.assert_called_with("task-3")

    @pytest.mark.asyncio
    async def test_background_rebuild_document_records_success_and_cleanup(self):
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._update_persistent_task = AsyncMock()
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        doc = MagicMock()
        doc.model_dump.return_value = {"doc_id": "doc-new", "version": 2}
        kb_helper = AsyncMock()
        kb_helper.rebuild_document = AsyncMock(return_value=doc)

        await route._background_rebuild_document_task(
            task_id="task-4",
            kb_helper=kb_helper,
            doc_id="doc-old",
            chunk_size=512,
            chunk_overlap=50,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)

        kb_helper.rebuild_document.assert_awaited_once()
        rebuild_call = kb_helper.rebuild_document.await_args
        assert rebuild_call.args == ("doc-old",)
        assert rebuild_call.kwargs["chunk_size"] == 512
        assert rebuild_call.kwargs["chunk_overlap"] == 50
        assert rebuild_call.kwargs["batch_size"] == 32
        assert rebuild_call.kwargs["tasks_limit"] == 3
        assert rebuild_call.kwargs["max_retries"] == 3
        assert rebuild_call.kwargs["progress_callback"] is not None
        assert route.upload_tasks["task-4"]["status"] == "completed"
        assert route.upload_tasks["task-4"]["result"] == {
            "task_id": "task-4",
            "rebuilt": [{"doc_id": "doc-new", "version": 2}],
            "failed": [],
            "total": 1,
            "success_count": 1,
            "failed_count": 0,
        }
        route._update_persistent_task.assert_any_await(
            "task-4",
            status="completed",
            result=route.upload_tasks["task-4"]["result"],
            error=None,
            **_persistent_progress_kwargs(route.upload_progress["task-4"]),
        )
        route._cleanup_task.assert_called_with("task-4")

    @pytest.mark.asyncio
    async def test_background_rebuild_document_records_failure_and_cleanup(self):
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._update_persistent_task = AsyncMock()
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.rebuild_document = AsyncMock(side_effect=RuntimeError("boom"))

        await route._background_rebuild_document_task(
            task_id="task-5",
            kb_helper=kb_helper,
            doc_id="doc-old",
            chunk_size=None,
            chunk_overlap=None,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)

        assert route.upload_tasks["task-5"] == {
            "status": "failed",
            "result": None,
            "error": "boom",
        }
        route._update_persistent_task.assert_any_await(
            "task-5",
            status="failed",
            error="boom",
            **_persistent_progress_kwargs(route.upload_progress["task-5"]),
        )
        route._cleanup_task.assert_called_with("task-5")

    @pytest.mark.asyncio
    async def test_background_rebuild_kb_records_success_and_cleanup(self):
        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._update_persistent_task = AsyncMock()
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.kb = KnowledgeBase(
            kb_id="kb-1",
            kb_name="docs",
            embedding_provider_id="emb-1",
        )
        kb_helper.rebuild_all_documents = AsyncMock(
            return_value={
                "rebuilt": [{"doc_id": "doc-new"}],
                "failed": [],
                "total": 1,
                "success_count": 1,
                "failed_count": 0,
            },
        )

        await route._background_rebuild_kb_task(
            task_id="task-6",
            kb_helper=kb_helper,
            chunk_size=512,
            chunk_overlap=50,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)

        kb_helper.rebuild_all_documents.assert_awaited_once()
        rebuild_call = kb_helper.rebuild_all_documents.await_args
        assert rebuild_call.kwargs["chunk_size"] == 512
        assert rebuild_call.kwargs["chunk_overlap"] == 50
        assert rebuild_call.kwargs["batch_size"] == 32
        assert rebuild_call.kwargs["tasks_limit"] == 3
        assert rebuild_call.kwargs["max_retries"] == 3
        assert rebuild_call.kwargs["progress_callback"] is not None
        assert route.upload_tasks["task-6"]["status"] == "completed"
        assert route.upload_tasks["task-6"]["result"] == {
            "task_id": "task-6",
            "rebuilt": [{"doc_id": "doc-new"}],
            "failed": [],
            "total": 1,
            "success_count": 1,
            "failed_count": 0,
        }
        route._update_persistent_task.assert_any_await(
            "task-6",
            status="completed",
            result=route.upload_tasks["task-6"]["result"],
            error=None,
            **_persistent_progress_kwargs(route.upload_progress["task-6"]),
        )
        route._cleanup_task.assert_called_with("task-6")

    @pytest.mark.asyncio
    async def test_background_rebuild_kb_records_failure_and_cleanup(self):
        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._update_persistent_task = AsyncMock()
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.kb = KnowledgeBase(
            kb_id="kb-1",
            kb_name="docs",
            embedding_provider_id="emb-1",
        )
        kb_helper.rebuild_all_documents = AsyncMock(
            side_effect=RuntimeError("rebuild exploded"),
        )

        await route._background_rebuild_kb_task(
            task_id="task-7",
            kb_helper=kb_helper,
            chunk_size=None,
            chunk_overlap=None,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)

        assert route.upload_tasks["task-7"] == {
            "status": "failed",
            "result": None,
            "error": "rebuild exploded",
        }
        route._update_persistent_task.assert_any_await(
            "task-7",
            status="failed",
            error="rebuild exploded",
            **_persistent_progress_kwargs(route.upload_progress["task-7"]),
        )
        route._cleanup_task.assert_called_with("task-7")

    @pytest.mark.asyncio
    async def test_background_rebuild_kb_marks_empty_kb_progress_completed(self):
        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._update_persistent_task = AsyncMock()
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.kb = KnowledgeBase(
            kb_id="kb-1",
            kb_name="empty-docs",
            embedding_provider_id="emb-1",
        )
        kb_helper.rebuild_all_documents = AsyncMock(
            return_value={
                "rebuilt": [],
                "failed": [],
                "total": 0,
                "success_count": 0,
                "failed_count": 0,
            },
        )

        await route._background_rebuild_kb_task(
            task_id="task-8",
            kb_helper=kb_helper,
            chunk_size=None,
            chunk_overlap=None,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)

        assert route.upload_tasks["task-8"]["result"]["total"] == 0
        assert route.upload_progress["task-8"]["status"] == "completed"
        assert route.upload_progress["task-8"]["stage"] == "completed"
        assert route.upload_progress["task-8"]["current"] == 1
        assert route.upload_progress["task-8"]["total"] == 1
        route._update_persistent_task.assert_any_await(
            "task-8",
            status="completed",
            result=route.upload_tasks["task-8"]["result"],
            error=None,
            **_persistent_progress_kwargs(route.upload_progress["task-8"]),
        )
        route._cleanup_task.assert_called_with("task-8")

    @pytest.mark.asyncio
    async def test_background_rebuild_documents_records_success_and_cleanup(self):
        from astrbot.dashboard.routes.knowledge_base import KnowledgeBaseRoute

        route = KnowledgeBaseRoute.__new__(KnowledgeBaseRoute)
        route.upload_tasks = {}
        route.upload_progress = {}
        route._update_persistent_task = AsyncMock()
        route._cleanup_task = MagicMock()

        async def fake_schedule(*args, **kwargs):
            route._cleanup_task(*args)
            await asyncio.sleep(0)

        route._schedule_delayed_cleanup = fake_schedule

        kb_helper = AsyncMock()
        kb_helper.rebuild_documents = AsyncMock(
            return_value={
                "rebuilt": [{"doc_id": "doc-new"}],
                "failed": [],
                "total": 2,
                "success_count": 2,
                "failed_count": 0,
            },
        )

        await route._background_rebuild_documents_task(
            task_id="task-9",
            kb_helper=kb_helper,
            doc_ids=["doc-1", "doc-2"],
            chunk_size=512,
            chunk_overlap=50,
            batch_size=32,
            tasks_limit=3,
            max_retries=3,
        )

        await asyncio.sleep(0.05)

        kb_helper.rebuild_documents.assert_awaited_once()
        rebuild_call = kb_helper.rebuild_documents.await_args
        assert rebuild_call.args == (["doc-1", "doc-2"],)
        assert rebuild_call.kwargs["chunk_size"] == 512
        assert rebuild_call.kwargs["chunk_overlap"] == 50
        assert rebuild_call.kwargs["batch_size"] == 32
        assert rebuild_call.kwargs["tasks_limit"] == 3
        assert rebuild_call.kwargs["max_retries"] == 3
        assert rebuild_call.kwargs["progress_callback"] is not None
        assert route.upload_tasks["task-9"]["status"] == "completed"
        assert route.upload_tasks["task-9"]["result"] == {
            "task_id": "task-9",
            "rebuilt": [{"doc_id": "doc-new"}],
            "failed": [],
            "total": 2,
            "success_count": 2,
            "failed_count": 0,
        }
        route._update_persistent_task.assert_any_await(
            "task-9",
            status="completed",
            result=route.upload_tasks["task-9"]["result"],
            error=None,
            **_persistent_progress_kwargs(route.upload_progress["task-9"]),
        )
        route._cleanup_task.assert_called_with("task-9")


# --- Merged from tests/test_kb_upload_rollback.py ---

"""Tests for upload metadata persistence and failure rollback."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest


def _build_helper():
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test-kb",
        kb_id="kb-test-1",
        embedding_provider_id="emb-1",
        chunk_size=512,
        chunk_overlap=50,
    )
    helper = KBHelper.__new__(KBHelper)
    helper.kb = kb
    helper.kb_db = MagicMock()
    helper.kb_db.get_document_by_content_hash = AsyncMock(return_value=None)
    helper.kb_db.get_db.side_effect = RuntimeError("test db is not configured")
    helper.kb_dir = MagicMock()
    helper.kb_medias_dir = MagicMock()
    helper.kb_files_dir = MagicMock()
    helper.prov_mgr = MagicMock()
    helper.chunker = AsyncMock()
    helper.vec_db = AsyncMock()
    helper._ensure_vec_db = AsyncMock()
    helper.init_error = None
    return helper


def _build_helper_with_real_dirs(tmp_path):
    helper = _build_helper()
    helper.kb_files_dir = tmp_path / "files"
    helper.kb_medias_dir = tmp_path / "medias"
    helper.kb_files_dir.mkdir(parents=True)
    helper.kb_medias_dir.mkdir(parents=True)
    return helper


def _mock_parser(mock_select, text="hello world test content", text_segments=None):
    parser = AsyncMock()
    result = MagicMock()
    type(result).text = PropertyMock(return_value=text)
    type(result).media = PropertyMock(return_value=[])
    type(result).text_segments = PropertyMock(return_value=text_segments)
    parser.parse = AsyncMock(return_value=result)
    mock_select.return_value = parser


def _make_session_context():
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.begin = MagicMock(return_value=session)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    return session


def _existing_doc():
    from astrbot.core.knowledge_base.models import KBDocument

    return KBDocument(
        doc_id="existing-doc",
        kb_id="kb-test-1",
        doc_name="existing.txt",
        file_type="txt",
        file_size=11,
        file_path="",
        content_hash="existing-hash",
        status="ready",
    )


def _chunk_doc(
    *,
    chunk_id: str,
    text: str,
    doc_id: str = "doc-1",
    index: int = 0,
    previous_chunk_id: str | None = None,
    next_chunk_id: str | None = None,
):
    import json

    return {
        "doc_id": chunk_id,
        "text": text,
        "metadata": json.dumps(
            {
                "kb_id": "kb-test-1",
                "kb_doc_id": doc_id,
                "chunk_index": index,
                "previous_chunk_id": previous_chunk_id,
                "next_chunk_id": next_chunk_id,
            },
        ),
    }


class TestUploadDocumentRollback:
    """Verify vectors are cleaned up when metadata save fails after insert."""

    @pytest.mark.asyncio
    async def test_rollback_when_metadata_save_fails(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1", "chunk 2", "chunk 3"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2, 3])
            helper.vec_db.delete_documents = AsyncMock()
            helper.kb_db.get_db.side_effect = RuntimeError("DB connection lost")

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt",
                    file_content=b"hello world",
                    file_type="txt",
                )

            assert exc_info.value.stage == "metadata"
            helper.vec_db.delete_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_rollback_when_insert_fails(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch.side_effect = KnowledgeBaseUploadError(
                stage="embedding",
                user_message="模拟失败",
                details={},
            )
            helper.vec_db.delete_documents = AsyncMock()

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt",
                    file_content=b"hello",
                    file_type="txt",
                )

            assert exc_info.value.stage == "embedding"
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_parse_failure_persists_failed_document_record(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            parser = AsyncMock()
            parser.parse = AsyncMock(side_effect=RuntimeError("broken parser"))
            mock_select.return_value = parser

            helper = _build_helper_with_real_dirs(tmp_path)
            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock()
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=0)

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="broken.txt",
                    file_content=b"not parseable",
                    file_type="txt",
                )

            failed_doc = session.add.call_args.args[0]
            assert exc_info.value.stage == "parsing"
            assert failed_doc.status == "failed"
            assert failed_doc.error_stage == "parsing"
            assert "文档解析失败" in failed_doc.error_message
            assert failed_doc.source_type == "file"
            assert failed_doc.source_uri == "broken.txt"
            assert failed_doc.content_hash == build_content_hash(b"not parseable")
            assert failed_doc.file_size == len(b"not parseable")
            assert Path(failed_doc.file_path).exists()
            assert Path(failed_doc.file_path).read_bytes() == b"not parseable"
            helper.vec_db.insert_batch.assert_not_awaited()
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_pre_chunked_import_persists_failed_document_record(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="empty-import.txt",
                file_content=None,
                file_type="txt",
                pre_chunked_text=[" ", ""],
                source_type="import",
                source_uri="manual-import",
            )

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "validation"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "validation"
        assert "预分块文本为空" in failed_doc.error_message
        assert failed_doc.source_type == "import"
        assert failed_doc.source_uri == "manual-import"
        assert failed_doc.file_path == ""
        assert failed_doc.file_size == 0
        assert failed_doc.content_hash == build_content_hash([])
        assert failed_doc.chunker_name == "pre_chunked"
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_failure_does_not_suppress_original_error(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1])
            helper.vec_db.delete_documents.side_effect = RuntimeError("cleanup fail")
            helper.kb_db.get_db.side_effect = RuntimeError("DB lost")

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt",
                    file_content=b"hello",
                    file_type="txt",
                )

            assert exc_info.value.stage == "metadata"
            helper.vec_db.delete_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_metadata_refresh_failure_preserves_committed_source_file(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock(
                side_effect=RuntimeError("stats fail"),
            )
            helper.vec_db.insert_batch = AsyncMock(return_value=[1])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=1)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="committed.txt",
                    file_content=b"hello world",
                    file_type="txt",
                )

            assert exc_info.value.stage == "metadata"
            saved_files = list(helper.kb_files_dir.glob("*/committed.txt"))
            assert len(saved_files) == 1
            assert saved_files[0].read_bytes() == b"hello world"
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_rollback_on_success(self):
        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1", "chunk 2"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper()

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            doc = await helper.upload_document(
                file_name="test.txt",
                file_content=b"hello world",
                file_type="txt",
            )

            assert doc is not None
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_document_persists_source_metadata_and_original_file(
        self,
        tmp_path,
    ):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["chunk 1", "chunk 2"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            doc = await helper.upload_document(
                file_name="../../unsafe.md",
                file_content=b"# Title\nhello world",
                file_type="md",
            )

            saved_path = Path(doc.file_path)
            assert doc.source_type == "file"
            assert doc.source_uri == "../../unsafe.md"
            assert doc.content_hash == build_content_hash(b"# Title\nhello world")
            assert doc.parser_name is not None
            assert doc.parser_version == "1"
            assert doc.chunker_name == "MarkdownChunker"
            assert doc.chunker_version == "1"
            assert doc.status == "ready"
            assert doc.indexed_at is not None
            assert saved_path.exists()
            assert saved_path.read_bytes() == b"# Title\nhello world"
            assert saved_path.name == "unsafe.md"
            assert saved_path.is_relative_to(helper.kb_files_dir)
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_document_stores_chunk_metadata(self, tmp_path):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.select_parser",
                new_callable=AsyncMock,
            ) as mock_select,
            patch(
                "astrbot.core.knowledge_base.kb_helper._compact_chunks",
                return_value=["first chunk", "second"],
            ),
        ):
            _mock_parser(mock_select)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="chunks.txt",
                file_content=b"source",
                file_type="txt",
            )

        kwargs = helper.vec_db.insert_batch.await_args.kwargs
        chunk_ids = kwargs["ids"]
        metadatas = kwargs["metadatas"]
        assert len(chunk_ids) == 2
        assert len(set(chunk_ids)) == 2
        assert metadatas == [
            {
                "kb_id": "kb-test-1",
                "kb_doc_id": session.add.call_args.args[0].doc_id,
                "chunk_index": 0,
                "section_index": 0,
                "content_hash": build_content_hash("first chunk"),
                "char_count": len("first chunk"),
                "token_count_estimate": 3,
                "start_offset": 0,
                "end_offset": len("first chunk"),
                "previous_chunk_id": None,
                "next_chunk_id": chunk_ids[1],
            },
            {
                "kb_id": "kb-test-1",
                "kb_doc_id": session.add.call_args.args[0].doc_id,
                "chunk_index": 1,
                "section_index": 1,
                "content_hash": build_content_hash("second"),
                "char_count": len("second"),
                "token_count_estimate": 1,
                "start_offset": len("first chunk"),
                "end_offset": len("first chunk") + len("second"),
                "previous_chunk_id": chunk_ids[0],
                "next_chunk_id": None,
            },
        ]

    @pytest.mark.asyncio
    async def test_upload_markdown_document_stores_title_path_metadata(self, tmp_path):
        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(
                mock_select,
                text=("# Guide\nIntro\n\n## Install\nStep one\n\n## Usage\nStep two"),
            )
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2, 3])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=3)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="guide.md",
                file_content=b"# Guide\nIntro",
                file_type="md",
            )

        metadatas = helper.vec_db.insert_batch.await_args.kwargs["metadatas"]
        assert [metadata.get("title_path") for metadata in metadatas] == [
            ["Guide"],
            ["Guide", "Install"],
            ["Guide", "Usage"],
        ]
        assert [metadata.get("section_index") for metadata in metadatas] == [0, 1, 2]
        assert all(
            metadata.get("token_count_estimate") is not None for metadata in metadatas
        )

    @pytest.mark.asyncio
    async def test_upload_markdown_document_keeps_title_path_on_split_chunks(
        self,
        tmp_path,
    ):
        markdown_text = "# Guide\n" + "\n".join(
            f"Long installation paragraph {idx}." for idx in range(16)
        )

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(mock_select, text=markdown_text)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=1)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="guide.md",
                file_content=markdown_text.encode(),
                file_type="md",
                chunk_size=90,
                chunk_overlap=0,
            )

        metadatas = helper.vec_db.insert_batch.await_args.kwargs["metadatas"]
        assert len(metadatas) > 1
        assert all(metadata.get("title_path") == ["Guide"] for metadata in metadatas)
        assert all(metadata.get("section_index") == 0 for metadata in metadatas)

    @pytest.mark.asyncio
    async def test_upload_xlsx_uses_markdown_chunker_for_table_protection(
        self,
        tmp_path,
    ):
        table_text = (
            "# Sheet1\n"
            "| Name | Value |\n"
            "| --- | --- |\n"
            + "\n".join(f"| row-{idx} | value-{idx} |" for idx in range(8))
        )

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(mock_select, text=table_text)
            helper = _build_helper_with_real_dirs(tmp_path)

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2, 3])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=3)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            doc = await helper.upload_document(
                file_name="sheet.xlsx",
                file_content=b"xlsx-bytes",
                file_type="xlsx",
                chunk_size=90,
                chunk_overlap=0,
            )

        contents = helper.vec_db.insert_batch.await_args.kwargs["contents"]
        table_chunks = [content for content in contents if "| Name | Value |" in content]

        assert doc.chunker_name == "MarkdownChunker"
        assert len(table_chunks) > 1
        assert all("| --- | --- |" in content for content in table_chunks)

    @pytest.mark.asyncio
    async def test_upload_document_stores_page_number_from_text_segments(
        self,
        tmp_path,
    ):
        from astrbot.core.knowledge_base.chunking.recursive import (
            RecursiveCharacterChunker,
        )
        from astrbot.core.knowledge_base.parsers.base import TextSegment

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select:
            _mock_parser(
                mock_select,
                text="Page one text\n\nPage two text",
                text_segments=[
                    TextSegment(text="Page one text", metadata={"page_number": 1}),
                    TextSegment(text="Page two text", metadata={"page_number": 2}),
                ],
            )
            helper = _build_helper_with_real_dirs(tmp_path)
            helper.chunker = RecursiveCharacterChunker()

            session = _make_session_context()
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            await helper.upload_document(
                file_name="guide.pdf",
                file_content=b"%PDF-1.7",
                file_type="pdf",
            )

        metadatas = helper.vec_db.insert_batch.await_args.kwargs["metadatas"]
        assert [metadata.get("page_number") for metadata in metadatas] == [1, 2]
        assert [metadata["chunk_index"] for metadata in metadatas] == [0, 1]
        assert [metadata["section_index"] for metadata in metadatas] == [0, 1]

    @pytest.mark.asyncio
    async def test_get_chunks_by_doc_id_returns_chunk_metadata(self):
        import json

        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()
        helper.vec_db.document_storage.get_documents = AsyncMock(
            return_value=[
                {
                    "doc_id": "chunk-1",
                    "text": "first chunk",
                    "metadata": json.dumps(
                        {
                            "kb_id": "kb-test-1",
                            "kb_doc_id": "doc-1",
                            "chunk_index": 0,
                            "section_index": 0,
                            "content_hash": "hash-1",
                            "char_count": 11,
                            "token_count_estimate": 3,
                            "start_offset": 0,
                            "end_offset": 11,
                            "previous_chunk_id": None,
                            "next_chunk_id": "chunk-2",
                        },
                    ),
                },
                {
                    "doc_id": "legacy-chunk",
                    "text": "legacy",
                    "metadata": json.dumps(
                        {
                            "kb_id": "kb-test-1",
                            "kb_doc_id": "doc-1",
                            "chunk_index": 1,
                        },
                    ),
                },
            ],
        )

        chunks = await helper.get_chunks_by_doc_id("doc-1", offset=2, limit=3)

        helper.vec_db.document_storage.get_documents.assert_awaited_once_with(
            metadata_filters={"kb_doc_id": "doc-1"},
            offset=2,
            limit=3,
        )
        assert chunks[0] == {
            "chunk_id": "chunk-1",
            "doc_id": "doc-1",
            "kb_id": "kb-test-1",
            "chunk_index": 0,
            "section_index": 0,
            "content": "first chunk",
            "char_count": 11,
            "token_count_estimate": 3,
            "content_hash": "hash-1",
            "start_offset": 0,
            "end_offset": 11,
            "previous_chunk_id": None,
            "next_chunk_id": "chunk-2",
            "title_path": None,
            "page_number": None,
            "parent_chunk_id": None,
        }
        assert chunks[1]["chunk_id"] == "legacy-chunk"
        assert chunks[1]["char_count"] == len("legacy")
        assert chunks[1]["section_index"] is None
        assert chunks[1]["token_count_estimate"] is None
        assert chunks[1]["content_hash"] is None

    @pytest.mark.asyncio
    async def test_search_chunks_by_doc_id_uses_document_storage_search(self):
        import json

        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()
        helper.vec_db.document_storage.search_documents = AsyncMock(
            return_value=(
                [
                    {
                        "doc_id": "chunk-1",
                        "text": "matched chunk",
                        "metadata": json.dumps(
                            {
                                "kb_id": "kb-test-1",
                                "kb_doc_id": "doc-1",
                                "chunk_index": 0,
                            },
                        ),
                    },
                ],
                3,
            ),
        )

        chunks, total = await helper.search_chunks_by_doc_id(
            "doc-1",
            search="matched",
            offset=2,
            limit=1,
        )

        helper.vec_db.document_storage.search_documents.assert_awaited_once_with(
            "matched",
            metadata_filters={"kb_doc_id": "doc-1"},
            offset=2,
            limit=1,
        )
        assert total == 3
        assert chunks[0]["chunk_id"] == "chunk-1"

    @pytest.mark.asyncio
    async def test_get_chunk_context_returns_adjacent_chunks(self):
        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()

        docs = {
            "chunk-1": _chunk_doc(
                chunk_id="chunk-1",
                text="previous",
                index=0,
                next_chunk_id="chunk-2",
            ),
            "chunk-2": _chunk_doc(
                chunk_id="chunk-2",
                text="current",
                index=1,
                previous_chunk_id="chunk-1",
                next_chunk_id="chunk-3",
            ),
            "chunk-3": _chunk_doc(
                chunk_id="chunk-3",
                text="next",
                index=2,
                previous_chunk_id="chunk-2",
            ),
        }
        helper.vec_db.document_storage.get_document_by_doc_id = AsyncMock(
            side_effect=lambda chunk_id: docs.get(chunk_id),
        )

        context = await helper.get_chunk_context("chunk-2", "doc-1")

        assert context["previous"]["chunk_id"] == "chunk-1"
        assert context["current"]["chunk_id"] == "chunk-2"
        assert context["next"]["chunk_id"] == "chunk-3"
        assert (
            helper.vec_db.document_storage.get_document_by_doc_id.await_args_list[
                0
            ].args[0]
            == "chunk-2"
        )

    @pytest.mark.asyncio
    async def test_get_chunk_context_filters_adjacent_chunks_from_other_docs(self):
        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()

        docs = {
            "chunk-2": _chunk_doc(
                chunk_id="chunk-2",
                text="current",
                index=1,
                previous_chunk_id="other-doc-chunk",
            ),
            "other-doc-chunk": _chunk_doc(
                chunk_id="other-doc-chunk",
                text="wrong document",
                doc_id="doc-2",
                index=0,
            ),
        }
        helper.vec_db.document_storage.get_document_by_doc_id = AsyncMock(
            side_effect=lambda chunk_id: docs.get(chunk_id),
        )

        context = await helper.get_chunk_context("chunk-2", "doc-1")

        assert context["current"]["chunk_id"] == "chunk-2"
        assert context["previous"] is None
        assert context["next"] is None

    @pytest.mark.asyncio
    async def test_get_chunk_context_raises_when_chunk_is_missing(self):
        helper = _build_helper()
        helper.vec_db = MagicMock()
        helper.vec_db.document_storage = MagicMock()
        helper.vec_db.document_storage.get_document_by_doc_id = AsyncMock(
            return_value=None,
        )

        with pytest.raises(ValueError, match="无法找到"):
            await helper.get_chunk_context("missing", "doc-1")

    @pytest.mark.asyncio
    async def test_upload_document_rejects_duplicate_before_storage(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.kb_db.get_document_by_content_hash = AsyncMock(
            return_value=_existing_doc(),
        )
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="duplicate.txt",
                file_content=b"hello world",
                file_type="txt",
            )

        assert exc_info.value.stage == "deduplication"
        assert exc_info.value.details == {
            "file_name": "duplicate.txt",
            "content_hash": build_content_hash(b"hello world"),
            "existing_doc_id": "existing-doc",
            "existing_doc_name": "existing.txt",
        }
        helper.kb_db.get_document_by_content_hash.assert_awaited_once_with(
            kb_id="kb-test-1",
            content_hash=build_content_hash(b"hello world"),
        )
        assert list(helper.kb_files_dir.glob("**/*")) == []
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_document_wraps_duplicate_lookup_failure(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.kb_db.get_document_by_content_hash = AsyncMock(
            side_effect=RuntimeError("db unavailable"),
        )
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="lookup-fails.txt",
                file_content=b"hello world",
                file_type="txt",
            )

        assert exc_info.value.stage == "deduplication"
        assert "重复检测失败" in exc_info.value.user_message
        assert list(helper.kb_files_dir.glob("**/*")) == []
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pre_chunked_upload_persists_import_metadata(self, tmp_path):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)

        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
        helper.vec_db.delete_documents = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=2)
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()

        doc = await helper.upload_document(
            file_name="imported.txt",
            file_content=None,
            file_type="txt",
            pre_chunked_text=["chunk 1", "chunk 2"],
            source_type="import",
            source_uri="manual-import",
        )

        assert doc.source_type == "import"
        assert doc.source_uri == "manual-import"
        assert doc.file_path == ""
        assert doc.file_size == len("chunk 1") + len("chunk 2")
        assert doc.content_hash == build_content_hash(["chunk 1", "chunk 2"])
        assert doc.parser_name is None
        assert doc.parser_version is None
        assert doc.chunker_name == "pre_chunked"
        assert doc.chunker_version == "1"
        assert doc.status == "ready"
        assert doc.indexed_at is not None
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pre_chunked_upload_rejects_duplicate_before_embedding(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.kb_db.get_document_by_content_hash = AsyncMock(
            return_value=_existing_doc(),
        )
        helper.vec_db.insert_batch = AsyncMock()
        helper.vec_db.delete_documents = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.upload_document(
                file_name="duplicate-import.txt",
                file_content=None,
                file_type="txt",
                pre_chunked_text=["chunk 1", "chunk 2"],
                source_type="import",
            )

        assert exc_info.value.stage == "deduplication"
        helper.kb_db.get_document_by_content_hash.assert_awaited_once_with(
            kb_id="kb-test-1",
            content_hash=build_content_hash(["chunk 1", "chunk 2"]),
        )
        assert list(helper.kb_files_dir.glob("**/*")) == []
        helper.vec_db.insert_batch.assert_not_awaited()
        helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_pre_chunked_upload_uses_explicit_url_metadata(self, tmp_path):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash
        from astrbot.core.knowledge_base.parsers.url_parser import URLExtractor

        helper = _build_helper_with_real_dirs(tmp_path)

        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.vec_db.insert_batch = AsyncMock(return_value=[1])
        helper.vec_db.delete_documents = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=1)
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()

        doc = await helper.upload_document(
            file_name="example.url",
            file_content=None,
            file_type="url",
            pre_chunked_text=["cleaned chunk"],
            source_type="url",
            source_uri="https://example.com/a",
            source_content_hash=build_content_hash("raw page text"),
            source_parser_name=URLExtractor.__name__,
            source_chunker_name="RecursiveCharacterChunker",
        )

        assert doc.source_type == "url"
        assert doc.source_uri == "https://example.com/a"
        assert doc.content_hash == build_content_hash("raw page text")
        assert doc.parser_name == URLExtractor.__name__
        assert doc.parser_version == "1"
        assert doc.chunker_name == "RecursiveCharacterChunker"
        assert doc.chunker_version == "1"
        assert doc.file_path == ""

    @pytest.mark.asyncio
    async def test_url_upload_missing_tavily_key_persists_failed_document(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.prov_mgr.acm.default_conf = {"provider_settings": {}}
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
                new_callable=AsyncMock,
            ) as mock_extract,
            pytest.raises(KnowledgeBaseUploadError) as exc_info,
        ):
            await helper.upload_from_url("https://example.com/page")

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "configuration"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "configuration"
        assert "Tavily API key" in failed_doc.error_message
        assert failed_doc.source_type == "url"
        assert failed_doc.source_uri == "https://example.com/page"
        assert failed_doc.doc_name == "page.url"
        assert failed_doc.file_type == "url"
        assert failed_doc.file_size == 0
        assert failed_doc.file_path == ""
        assert failed_doc.content_hash is None
        mock_extract.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_url_upload_extract_failure_persists_failed_document(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.prov_mgr.acm.default_conf = {
            "provider_settings": {"websearch_tavily_key": ["key-1"]},
        }
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
                new_callable=AsyncMock,
                side_effect=RuntimeError("network down"),
            ) as mock_extract,
            pytest.raises(KnowledgeBaseUploadError) as exc_info,
        ):
            await helper.upload_from_url("https://example.com/a")

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "extracting"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "extracting"
        assert "无法提取网页内容" in failed_doc.error_message
        assert failed_doc.source_type == "url"
        assert failed_doc.source_uri == "https://example.com/a"
        assert failed_doc.content_hash is None
        mock_extract.assert_awaited_once_with("https://example.com/a", ["key-1"])

    @pytest.mark.asyncio
    async def test_url_upload_empty_cleaning_result_persists_failed_document(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper_with_real_dirs(tmp_path)
        helper.prov_mgr.acm.default_conf = {
            "provider_settings": {"websearch_tavily_key": ["key-1"]},
        }
        helper._clean_and_rechunk_content = AsyncMock(return_value=[])
        helper.upload_document = AsyncMock()
        session = _make_session_context()
        helper.kb_db.get_db = MagicMock(return_value=session)
        helper.kb_db.update_kb_stats = AsyncMock()
        helper.refresh_kb = AsyncMock()
        helper.refresh_document = AsyncMock()
        helper.vec_db.count_documents = AsyncMock(return_value=0)

        with (
            patch(
                "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
                new_callable=AsyncMock,
                return_value="raw page text",
            ) as mock_extract,
            pytest.raises(KnowledgeBaseUploadError) as exc_info,
        ):
            await helper.upload_from_url(
                "https://example.com/docs",
                enable_cleaning=True,
                cleaning_provider_id="llm-1",
            )

        failed_doc = session.add.call_args.args[0]
        assert exc_info.value.stage == "cleaning"
        assert failed_doc.status == "failed"
        assert failed_doc.error_stage == "cleaning"
        assert "内容清洗后未提取到有效文本" in failed_doc.error_message
        assert failed_doc.source_type == "url"
        assert failed_doc.source_uri == "https://example.com/docs"
        assert failed_doc.file_size == len("raw page text")
        assert failed_doc.content_hash == build_content_hash("raw page text")
        mock_extract.assert_awaited_once_with("https://example.com/docs", ["key-1"])
        helper.upload_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rebuild_document_reuploads_saved_source_as_next_version(
        self,
        tmp_path,
    ):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        source_path = helper.kb_files_dir / "old-doc" / "source.md"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"# Title\nhello")
        old_doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="source.md",
            file_type="md",
            file_size=13,
            file_path=str(source_path),
            source_type="file",
            source_uri="source.md",
            version=2,
        )
        new_doc = KBDocument(
            doc_id="new-doc",
            kb_id="kb-test-1",
            doc_name="source.md",
            file_type="md",
            file_size=13,
            file_path="",
            version=3,
            parent_doc_id="old-doc",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.delete_document = AsyncMock()
        helper.upload_document = AsyncMock(return_value=new_doc)

        rebuilt = await helper.rebuild_document("old-doc", batch_size=8)

        assert rebuilt is new_doc
        helper.upload_document.assert_awaited_once_with(
            file_name="source.md",
            file_content=b"# Title\nhello",
            file_type="md",
            chunk_size=512,
            chunk_overlap=50,
            batch_size=8,
            tasks_limit=3,
            max_retries=3,
            progress_callback=None,
            source_type="file",
            source_uri="source.md",
            parent_doc_id="old-doc",
            document_version=3,
            skip_duplicate_check=True,
        )
        helper.delete_document.assert_awaited_once_with("old-doc")

    @pytest.mark.asyncio
    async def test_rebuild_url_document_reimports_source_as_next_version(self):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        old_doc = KBDocument(
            doc_id="old-url-doc",
            kb_id="kb-test-1",
            doc_name="page.url",
            file_type="url",
            file_size=13,
            file_path="",
            source_type="url",
            source_uri="https://example.com/page",
            version=4,
        )
        new_doc = KBDocument(
            doc_id="new-url-doc",
            kb_id="kb-test-1",
            doc_name="page.url",
            file_type="url",
            file_size=15,
            file_path="",
            source_type="url",
            source_uri="https://example.com/page",
            version=5,
            parent_doc_id="old-url-doc",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.delete_document = AsyncMock()
        helper.upload_from_url = AsyncMock(return_value=new_doc)

        rebuilt = await helper.rebuild_document(
            "old-url-doc",
            chunk_size=256,
            chunk_overlap=32,
            batch_size=8,
        )

        assert rebuilt is new_doc
        helper.upload_from_url.assert_awaited_once_with(
            url="https://example.com/page",
            chunk_size=256,
            chunk_overlap=32,
            batch_size=8,
            tasks_limit=3,
            max_retries=3,
            progress_callback=None,
            parent_doc_id="old-url-doc",
            document_version=5,
            skip_duplicate_check=True,
        )
        helper.delete_document.assert_awaited_once_with("old-url-doc")

    @pytest.mark.asyncio
    async def test_rebuild_url_document_rejects_missing_source_uri(self):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        doc = KBDocument(
            doc_id="old-url-doc",
            kb_id="kb-test-1",
            doc_name="page.url",
            file_type="url",
            file_size=13,
            file_path="",
            source_type="url",
            source_uri=None,
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=doc)
        helper.delete_document = AsyncMock()
        helper.upload_from_url = AsyncMock()

        with pytest.raises(ValueError, match="URL 来源"):
            await helper.rebuild_document("old-url-doc")

        helper.delete_document.assert_not_awaited()
        helper.upload_from_url.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_upload_from_url_forwards_rebuild_version_metadata(self):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash

        helper = _build_helper()
        helper.prov_mgr.acm.default_conf = {
            "provider_settings": {"websearch_tavily_key": ["key-1"]},
        }
        helper._clean_and_rechunk_content = AsyncMock(return_value=["new chunk"])
        helper.upload_document = AsyncMock(return_value=object())

        with patch(
            "astrbot.core.knowledge_base.kb_helper.extract_text_from_url",
            new_callable=AsyncMock,
            return_value="fresh page text",
        ):
            await helper.upload_from_url(
                "https://example.com/page",
                parent_doc_id="old-url-doc",
                document_version=5,
                skip_duplicate_check=True,
            )

        helper.upload_document.assert_awaited_once()
        upload_kwargs = helper.upload_document.await_args.kwargs
        assert upload_kwargs["pre_chunked_text"] == ["new chunk"]
        assert upload_kwargs["source_type"] == "url"
        assert upload_kwargs["source_uri"] == "https://example.com/page"
        assert upload_kwargs["source_content_hash"] == build_content_hash(
            "fresh page text",
        )
        assert upload_kwargs["parent_doc_id"] == "old-url-doc"
        assert upload_kwargs["document_version"] == 5
        assert upload_kwargs["skip_duplicate_check"] is True

    @pytest.mark.asyncio
    async def test_rebuild_import_document_reuses_indexed_chunks_as_next_version(
        self,
    ):
        from astrbot.core.knowledge_base.document_metadata import build_content_hash
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        old_doc = KBDocument(
            doc_id="old-import-doc",
            kb_id="kb-test-1",
            doc_name="manual.txt",
            file_type="txt",
            file_size=18,
            file_path="",
            source_type="import",
            source_uri="manual-import",
            chunker_name="pre_chunked",
            version=2,
        )
        new_doc = KBDocument(
            doc_id="new-import-doc",
            kb_id="kb-test-1",
            doc_name="manual.txt",
            file_type="txt",
            file_size=18,
            file_path="",
            source_type="import",
            source_uri="manual-import",
            version=3,
            parent_doc_id="old-import-doc",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.get_chunks_by_doc_id = AsyncMock(
            return_value=[
                {"chunk_index": 1, "content": "second chunk"},
                {"chunk_index": 0, "content": "first chunk"},
            ],
        )
        helper.upload_document = AsyncMock(return_value=new_doc)
        helper.delete_document = AsyncMock()

        rebuilt = await helper.rebuild_document("old-import-doc", batch_size=8)

        assert rebuilt is new_doc
        helper.upload_document.assert_awaited_once_with(
            file_name="manual.txt",
            file_content=None,
            file_type="txt",
            chunk_size=512,
            chunk_overlap=50,
            batch_size=8,
            tasks_limit=3,
            max_retries=3,
            progress_callback=None,
            pre_chunked_text=["first chunk", "second chunk"],
            source_type="import",
            source_uri="manual-import",
            source_content_hash=build_content_hash(["first chunk", "second chunk"]),
            source_chunker_name="pre_chunked",
            parent_doc_id="old-import-doc",
            document_version=3,
            skip_duplicate_check=True,
        )
        helper.delete_document.assert_awaited_once_with("old-import-doc")

    @pytest.mark.asyncio
    async def test_rebuild_import_document_rejects_missing_indexed_chunks(self):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper()
        doc = KBDocument(
            doc_id="old-import-doc",
            kb_id="kb-test-1",
            doc_name="manual.txt",
            file_type="txt",
            file_size=18,
            file_path="",
            source_type="import",
            source_uri="manual-import",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=doc)
        helper.get_chunks_by_doc_id = AsyncMock(return_value=[])
        helper.upload_document = AsyncMock()
        helper.delete_document = AsyncMock()

        with pytest.raises(ValueError, match="导入文本块"):
            await helper.rebuild_document("old-import-doc")

        helper.upload_document.assert_not_awaited()
        helper.delete_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_import_rebuild_chunks_reads_every_page(self):
        from astrbot.core.knowledge_base.kb_helper import DOCUMENT_REBUILD_PAGE_SIZE

        helper = _build_helper()
        first_page = [
            {"chunk_index": index + 1, "content": f"chunk {index + 1}"}
            for index in range(DOCUMENT_REBUILD_PAGE_SIZE)
        ]
        second_page = [{"chunk_index": 0, "content": "chunk 0"}]
        helper.get_chunks_by_doc_id = AsyncMock(side_effect=[first_page, second_page])

        chunks = await helper._get_import_rebuild_chunks("doc-1")

        assert chunks == ["chunk 0", *[f"chunk {index + 1}" for index in range(100)]]
        assert helper.get_chunks_by_doc_id.await_args_list[0].kwargs == {
            "offset": 0,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }
        assert helper.get_chunks_by_doc_id.await_args_list[1].kwargs == {
            "offset": DOCUMENT_REBUILD_PAGE_SIZE,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }

    @pytest.mark.asyncio
    async def test_rebuild_document_rejects_missing_source_file(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="missing.txt",
            file_type="txt",
            file_size=1,
            file_path=str(helper.kb_files_dir / "missing" / "missing.txt"),
            source_type="file",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=doc)
        helper.delete_document = AsyncMock()
        helper.upload_document = AsyncMock()

        with pytest.raises(ValueError, match="原始文件"):
            await helper.rebuild_document("old-doc")

        helper.delete_document.assert_not_awaited()
        helper.upload_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rebuild_document_keeps_old_doc_when_upload_fails(self, tmp_path):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        source_path = helper.kb_files_dir / "old-doc" / "source.txt"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"hello")
        old_doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="source.txt",
            file_type="txt",
            file_size=5,
            file_path=str(source_path),
            source_type="file",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.upload_document = AsyncMock(
            side_effect=KnowledgeBaseUploadError(
                stage="embedding",
                user_message="embedding failed",
            ),
        )
        helper.delete_document = AsyncMock()

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.rebuild_document("old-doc")

        assert exc_info.value.stage == "embedding"
        helper.delete_document.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_rebuild_document_rolls_back_new_doc_when_replace_fails(
        self,
        tmp_path,
    ):
        from astrbot.core.exceptions import KnowledgeBaseUploadError
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        source_path = helper.kb_files_dir / "old-doc" / "source.txt"
        source_path.parent.mkdir(parents=True)
        source_path.write_bytes(b"hello")
        old_doc = KBDocument(
            doc_id="old-doc",
            kb_id="kb-test-1",
            doc_name="source.txt",
            file_type="txt",
            file_size=5,
            file_path=str(source_path),
            source_type="file",
        )
        new_doc = KBDocument(
            doc_id="new-doc",
            kb_id="kb-test-1",
            doc_name="source.txt",
            file_type="txt",
            file_size=5,
            file_path="",
        )
        helper.kb_db.get_document_by_id = AsyncMock(return_value=old_doc)
        helper.upload_document = AsyncMock(return_value=new_doc)
        helper.delete_document = AsyncMock(
            side_effect=[RuntimeError("old delete failed"), None],
        )

        with pytest.raises(KnowledgeBaseUploadError) as exc_info:
            await helper.rebuild_document("old-doc")

        assert exc_info.value.stage == "rebuild"
        assert exc_info.value.details == {
            "doc_id": "old-doc",
            "new_doc_id": "new-doc",
        }
        assert helper.delete_document.await_args_list[0].args == ("old-doc",)
        assert helper.delete_document.await_args_list[1].args == ("new-doc",)

    @pytest.mark.asyncio
    async def test_rebuild_all_documents_preserves_partial_failures(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        docs = [
            KBDocument(
                doc_id="doc-ok",
                kb_id="kb-test-1",
                doc_name="ok.txt",
                file_type="txt",
                file_size=2,
                file_path="",
            ),
            KBDocument(
                doc_id="doc-fail",
                kb_id="kb-test-1",
                doc_name="fail.txt",
                file_type="txt",
                file_size=4,
                file_path="",
            ),
        ]
        rebuilt_doc = KBDocument(
            doc_id="doc-new",
            kb_id="kb-test-1",
            doc_name="ok.txt",
            file_type="txt",
            file_size=2,
            file_path="",
        )
        helper.list_documents = AsyncMock(return_value=docs)
        helper.rebuild_document = AsyncMock(
            side_effect=[rebuilt_doc, ValueError("missing source")],
        )

        result = await helper.rebuild_all_documents(batch_size=6)

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["failed_count"] == 1
        assert result["rebuilt"][0]["doc_id"] == "doc-new"
        assert result["failed"] == [
            {
                "doc_id": "doc-fail",
                "doc_name": "fail.txt",
                "error": "missing source",
            },
        ]
        assert helper.rebuild_document.await_args_list[0].kwargs["batch_size"] == 6
        assert helper.rebuild_document.await_args_list[1].kwargs["batch_size"] == 6

    @pytest.mark.asyncio
    async def test_rebuild_all_documents_reads_every_page(self, tmp_path):
        from astrbot.core.knowledge_base.kb_helper import DOCUMENT_REBUILD_PAGE_SIZE
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        docs = [
            KBDocument(
                doc_id=f"doc-{index}",
                kb_id="kb-test-1",
                doc_name=f"doc-{index}.txt",
                file_type="txt",
                file_size=2,
                file_path="",
            )
            for index in range(DOCUMENT_REBUILD_PAGE_SIZE + 1)
        ]

        async def list_documents(offset=0, limit=100, search=None):
            return docs[offset : offset + limit]

        helper.list_documents = AsyncMock(side_effect=list_documents)
        helper.rebuild_document = AsyncMock(
            side_effect=[
                KBDocument(
                    doc_id=f"rebuilt-{index}",
                    kb_id="kb-test-1",
                    doc_name=f"doc-{index}.txt",
                    file_type="txt",
                    file_size=2,
                    file_path="",
                )
                for index in range(DOCUMENT_REBUILD_PAGE_SIZE + 1)
            ],
        )

        result = await helper.rebuild_all_documents()

        assert result["total"] == DOCUMENT_REBUILD_PAGE_SIZE + 1
        assert result["success_count"] == DOCUMENT_REBUILD_PAGE_SIZE + 1
        assert helper.list_documents.await_args_list[0].kwargs == {
            "offset": 0,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }
        assert helper.list_documents.await_args_list[1].kwargs == {
            "offset": DOCUMENT_REBUILD_PAGE_SIZE,
            "limit": DOCUMENT_REBUILD_PAGE_SIZE,
        }

    @pytest.mark.asyncio
    async def test_rebuild_documents_preserves_partial_failures(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument

        helper = _build_helper_with_real_dirs(tmp_path)
        failed_doc = KBDocument(
            doc_id="doc-fail",
            kb_id="kb-test-1",
            doc_name="fail.txt",
            file_type="txt",
            file_size=4,
            file_path="",
        )
        rebuilt_doc = KBDocument(
            doc_id="doc-new",
            kb_id="kb-test-1",
            doc_name="ok.txt",
            file_type="txt",
            file_size=2,
            file_path="",
        )
        helper.rebuild_document = AsyncMock(
            side_effect=[rebuilt_doc, ValueError("missing source")],
        )
        helper.get_document = AsyncMock(return_value=failed_doc)

        result = await helper.rebuild_documents(
            ["doc-ok", "doc-fail", "doc-ok"],
            batch_size=6,
        )

        assert result["total"] == 2
        assert result["success_count"] == 1
        assert result["failed_count"] == 1
        assert result["rebuilt"][0]["doc_id"] == "doc-new"
        assert result["failed"] == [
            {
                "doc_id": "doc-fail",
                "doc_name": "fail.txt",
                "error": "missing source",
            },
        ]
        assert helper.rebuild_document.await_args_list[0].args == ("doc-ok",)
        assert helper.rebuild_document.await_args_list[1].args == ("doc-fail",)
        assert helper.rebuild_document.await_args_list[0].kwargs["batch_size"] == 6
        assert helper.rebuild_document.await_args_list[1].kwargs["batch_size"] == 6
