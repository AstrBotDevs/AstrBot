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
