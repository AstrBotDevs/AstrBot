"""知识库内存泄漏和性能测试

测试长时间运行和大规模数据场景下的内存占用。
"""

import asyncio
import gc
import tempfile
import tracemalloc
from pathlib import Path

import pytest


def get_memory_usage_mb() -> float:
    """获取当前进程的内存占用（MB）"""
    import psutil

    process = psutil.Process()
    return process.memory_info().rss / 1024 / 1024


@pytest.mark.asyncio
async def test_embedding_cache_no_memory_leak():
    """测试嵌入缓存长时间运行无内存泄漏"""
    from astrbot.core.db.vec_db.faiss_impl.vec_db import EmbeddingCache

    tracemalloc.start()
    initial_snapshot = tracemalloc.take_snapshot()

    cache = EmbeddingCache(max_size=100)

    import numpy as np

    # 模拟长时间运行，循环插入和读取
    for iteration in range(10):
        for i in range(200):
            text = f"iteration_{iteration}_text_{i}"
            embedding = np.random.randn(128).astype("float32")
            await cache.put(text, embedding)

        # 读取一些缓存
        for i in range(50):
            text = f"iteration_{iteration}_text_{i + 150}"
            await cache.get(text)

        # 每次迭代后触发 GC
        gc.collect()

    final_snapshot = tracemalloc.take_snapshot()
    tracemalloc.stop()

    # 检查内存增长
    top_stats = final_snapshot.compare_to(initial_snapshot, "lineno")

    # 计算总内存增长
    total_growth = sum(stat.size_diff for stat in top_stats)
    total_growth_mb = total_growth / 1024 / 1024

    # 预期：由于 LRU 限制，内存增长应该很小（< 10MB）
    assert (
        total_growth_mb < 10
    ), f"Memory grew by {total_growth_mb:.2f}MB, possible leak"

    # 验证缓存大小被正确限制
    cache_size = await cache.__len__()
    assert cache_size <= 100


@pytest.mark.asyncio
async def test_large_scale_document_upload():
    """测试大规模文档上传的内存稳定性"""
    pytest.importorskip("psutil")

    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
        from astrbot.core.knowledge_base.kb_helper import KBHelper
        from astrbot.core.knowledge_base.models import KnowledgeBase
        from tests.test_kb_concurrent_stress import MockChunker, MockProviderManager

        kb_db = KBSQLiteDatabase(str(db_path))
        await kb_db.initialize()

        provider_mgr = MockProviderManager()
        chunker = MockChunker()

        kb = KnowledgeBase(
            kb_name="large_scale_test",
            embedding_provider_id="mock",
            chunk_size=512,
            chunk_overlap=50,
        )

        async with kb_db.get_db() as session:
            session.add(kb)
            await session.commit()
            await session.refresh(kb)

        kb_helper = KBHelper(
            kb_db=kb_db,
            kb=kb,
            provider_manager=provider_mgr,
            kb_root_dir=str(kb_root),
            chunker=chunker,
        )
        await kb_helper.initialize()

        initial_memory = get_memory_usage_mb()
        doc_count = 50  # 上传 50 个文档

        for i in range(doc_count):
            # 每个文档约 10KB
            content = f"Document {i} content. " * 500
            await kb_helper.upload_document(
                file_name=f"doc_{i}.txt",
                file_content=content.encode(),
                file_type="txt",
            )

            # 每 10 个文档触发一次 GC
            if i % 10 == 0:
                gc.collect()

        final_memory = get_memory_usage_mb()
        memory_growth = final_memory - initial_memory

        # 预期：50 个文档的内存增长应该在合理范围内（< 100MB）
        # 这取决于向量维度和缓存大小
        assert memory_growth < 100, f"Memory grew by {memory_growth:.2f}MB"

        await kb_helper.terminate()


@pytest.mark.asyncio
async def test_kb_manager_instance_cache_no_leak():
    """测试知识库管理器实例缓存无泄漏"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
        from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
        from tests.test_kb_concurrent_stress import MockProviderManager

        provider_mgr = MockProviderManager()

        kb_mgr = KnowledgeBaseManager(provider_manager=provider_mgr)
        kb_mgr.kb_db = KBSQLiteDatabase(str(db_path))
        await kb_mgr.kb_db.initialize()

        # 创建多个知识库
        kb_ids = []
        for i in range(10):
            kb_helper = await kb_mgr.create_kb(
                kb_name=f"kb_{i}",
                embedding_provider_id="mock",
            )
            kb_ids.append(kb_helper.kb.kb_id)

        # 验证实例缓存大小
        assert len(kb_mgr.kb_insts) == 10

        # 删除一些知识库
        for kb_id in kb_ids[:5]:
            kb_mgr._remove_kb_instance(kb_id)

        # 验证缓存被正确清理
        assert len(kb_mgr.kb_insts) == 5

        # 验证名称索引也被更新
        assert len(kb_mgr._kb_name_index) == 5


@pytest.mark.asyncio
async def test_retrieval_manager_memory_efficiency():
    """测试检索管理器在大量结果下的内存效率"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
        from astrbot.core.knowledge_base.kb_helper import KBHelper
        from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.core.knowledge_base.retrieval.manager import RetrievalManager
        from tests.test_kb_concurrent_stress import MockChunker, MockProviderManager

        kb_db = KBSQLiteDatabase(str(db_path))
        await kb_db.initialize()

        provider_mgr = MockProviderManager()
        chunker = MockChunker()

        kb = KnowledgeBase(
            kb_name="retrieval_test",
            embedding_provider_id="mock",
            chunk_size=512,
            chunk_overlap=50,
        )

        async with kb_db.get_db() as session:
            session.add(kb)
            await session.commit()
            await session.refresh(kb)

        kb_helper = KBHelper(
            kb_db=kb_db,
            kb=kb,
            provider_manager=provider_mgr,
            kb_root_dir=str(kb_root),
            chunker=chunker,
        )
        await kb_helper.initialize()

        # 上传一些文档
        for i in range(20):
            await kb_helper.upload_document(
                file_name=f"doc_{i}.txt",
                file_content=f"Document content {i}".encode() * 50,
                file_type="txt",
            )

        # 创建检索管理器
        from astrbot.core.knowledge_base.retrieval.rank_fusion import RankFusion
        from astrbot.core.knowledge_base.retrieval.sparse_retriever import (
            SparseRetriever,
        )

        sparse_retriever = SparseRetriever(kb_db)
        rank_fusion = RankFusion(kb_db)
        # 注意参数顺序: sparse_retriever, rank_fusion, kb_db
        retrieval_mgr = RetrievalManager(sparse_retriever, rank_fusion, kb_db)

        # 执行多次检索
        initial_memory = get_memory_usage_mb()

        for i in range(50):
            results = await retrieval_mgr.retrieve(
                query=f"test query {i}",
                kb_ids=[kb.kb_id],
                kb_id_helper_map={kb.kb_id: kb_helper},
            )

            # 验证返回结果
            assert isinstance(results, list)

        gc.collect()
        final_memory = get_memory_usage_mb()
        memory_growth = final_memory - initial_memory

        # 预期：重复检索不应该导致显著内存增长
        assert memory_growth < 50, f"Memory grew by {memory_growth:.2f}MB"

        await kb_helper.terminate()


@pytest.mark.asyncio
async def test_faiss_index_memory_scaling():
    """测试 FAISS 索引随向量数量增长的内存占用"""
    pytest.importorskip("psutil")

    with tempfile.TemporaryDirectory() as tmp_dir:
        index_path = Path(tmp_dir) / "scaling_test.faiss"

        from astrbot.core.db.vec_db.faiss_impl.embedding_storage import (
            EmbeddingStorage,
        )

        storage = EmbeddingStorage(dimension=128, path=str(index_path), index_type="flat")

        import numpy as np

        initial_memory = get_memory_usage_mb()
        vector_counts = []
        memory_usages = []

        # 插入不同数量的向量，记录内存占用
        for batch in range(10):
            batch_size = 100
            vectors = np.random.randn(batch_size, 128).astype("float32")
            ids = list(range(batch * batch_size, (batch + 1) * batch_size))

            await storage.insert_batch(vectors, ids)

            vector_count = storage.index.ntotal
            memory_usage = get_memory_usage_mb() - initial_memory

            vector_counts.append(vector_count)
            memory_usages.append(memory_usage)

        # 验证内存增长大致线性
        # 1000 个 128 维 float32 向量 ≈ 1000 * 128 * 4 = 512KB
        # 加上索引结构开销，应该 < 10MB
        final_memory_growth = memory_usages[-1]
        assert final_memory_growth < 10, f"Memory grew by {final_memory_growth:.2f}MB for 1000 vectors"


@pytest.mark.asyncio
async def test_long_running_session_stability():
    """测试长时间会话的稳定性（模拟持续操作）"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
        from astrbot.core.knowledge_base.kb_helper import KBHelper
        from astrbot.core.knowledge_base.models import KnowledgeBase
        from tests.test_kb_concurrent_stress import MockChunker, MockProviderManager

        kb_db = KBSQLiteDatabase(str(db_path))
        await kb_db.initialize()

        provider_mgr = MockProviderManager()
        chunker = MockChunker()

        kb = KnowledgeBase(
            kb_name="long_running_test",
            embedding_provider_id="mock",
            chunk_size=512,
            chunk_overlap=50,
        )

        async with kb_db.get_db() as session:
            session.add(kb)
            await session.commit()
            await session.refresh(kb)

        kb_helper = KBHelper(
            kb_db=kb_db,
            kb=kb,
            provider_manager=provider_mgr,
            kb_root_dir=str(kb_root),
            chunker=chunker,
        )
        await kb_helper.initialize()

        # 模拟长时间运行：上传、删除、查询循环
        for iteration in range(5):
            # 上传 5 个文档
            doc_ids = []
            for i in range(5):
                doc = await kb_helper.upload_document(
                    file_name=f"iter_{iteration}_doc_{i}.txt",
                    file_content=f"Iteration {iteration} document {i}".encode() * 20,
                    file_type="txt",
                )
                doc_ids.append(doc.doc_id)

            # 删除前 3 个
            for doc_id in doc_ids[:3]:
                await kb_helper.delete_document(doc_id)

            # 触发 GC
            gc.collect()

        # 验证最终状态
        async with kb_db.get_db() as session:
            from sqlmodel import select

            from astrbot.core.knowledge_base.models import KBDocument

            stmt = select(KBDocument).where(KBDocument.kb_id == kb.kb_id)
            result = await session.execute(stmt)
            docs = result.scalars().all()

            # 每轮保留 2 个，5 轮应该有 10 个
            assert len(docs) == 10

        await kb_helper.terminate()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
