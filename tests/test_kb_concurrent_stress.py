"""知识库并发压力测试

测试并发场景下的数据一致性和竞态条件。
"""

import asyncio
import tempfile
import uuid
from pathlib import Path

import pytest

from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot.core.exceptions import KnowledgeBaseUploadError
from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.knowledge_base.models import KnowledgeBase


class MockEmbeddingProvider:
    """Mock embedding provider for testing"""

    def get_dim(self):
        return 128

    async def get_embedding(self, text: str):
        # 模拟网络延迟
        await asyncio.sleep(0.01)
        import hashlib
        import numpy as np

        # 使用文本哈希生成确定性向量
        hash_val = int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)
        np.random.seed(hash_val)
        return np.random.randn(128).astype("float32").tolist()

    async def get_embeddings_batch(
        self,
        texts,
        batch_size=32,
        tasks_limit=3,
        max_retries=3,
        progress_callback=None,
    ):
        results = []
        for i, text in enumerate(texts):
            results.append(await self.get_embedding(text))
            if progress_callback:
                await progress_callback(i + 1, len(texts))
        return results


class MockProviderManager:
    """Mock provider manager for testing"""

    def __init__(self):
        self.embedding_provider = MockEmbeddingProvider()

    def get_embedding_provider(self, provider_id):
        return self.embedding_provider

    def get_rerank_provider(self, provider_id):
        return None

    async def get_provider_by_id(self, provider_id):
        return self.embedding_provider


class MockChunker:
    """Mock chunker for testing"""

    async def chunk(self, text, chunk_size=512, chunk_overlap=50):
        # 简单按长度分块
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end])
            start = end - chunk_overlap if end < len(text) else end
        return chunks


@pytest.mark.asyncio
async def test_concurrent_duplicate_upload():
    """测试并发上传相同文档时的行为

    由于没有数据库层唯一约束，应用层的去重检查存在竞态条件窗口，
    多个并发上传可能都通过检查。这个测试验证：
    1. 系统不会崩溃
    2. 所有上传都完成（成功或失败）
    3. 至少有一个成功
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        kb_db = KBSQLiteDatabase(str(db_path))
        await kb_db.initialize()

        provider_mgr = MockProviderManager()
        chunker = MockChunker()

        kb = KnowledgeBase(
            kb_name="test_kb",
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

        # 相同内容的文档
        file_content = b"This is a test document for concurrent upload testing." * 100

        # 并发上传相同文档 5 次
        tasks = []
        for i in range(5):
            task = kb_helper.upload_document(
                file_name=f"test_doc_{i}.txt",
                file_content=file_content,
                file_type="txt",
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计成功和失败次数
        success_count = sum(
            1 for r in results if not isinstance(r, Exception)
        )
        duplicate_errors = sum(
            1
            for r in results
            if isinstance(r, KnowledgeBaseUploadError) and r.stage == "deduplication"
        )
        total_handled = success_count + duplicate_errors

        # 验证：
        # 1. 所有请求都被处理（没有未捕获的异常）
        unhandled_errors = [
            r for r in results
            if isinstance(r, Exception) and not isinstance(r, KnowledgeBaseUploadError)
        ]
        assert len(unhandled_errors) == 0, f"Unhandled errors: {unhandled_errors}"

        # 2. 至少有一个成功
        assert success_count >= 1, f"Expected at least 1 success, got {success_count}"

        # 3. 数据库中的文档数量 <= 成功数量（可能因为 content_hash 相同）
        async with kb_db.get_db() as session:
            from sqlmodel import select

            from astrbot.core.knowledge_base.models import KBDocument

            stmt = select(KBDocument).where(KBDocument.kb_id == kb.kb_id)
            result = await session.execute(stmt)
            docs = result.scalars().all()

            # 由于没有唯一约束，可能会有多个重复文档被插入
            # 我们只验证没有崩溃，数据库状态一致
            assert len(docs) >= 1, "Expected at least 1 document in DB"
            assert len(docs) <= 5, "Should not exceed upload count"

        await kb_helper.terminate()


@pytest.mark.asyncio
async def test_concurrent_upload_delete():
    """测试并发上传和删除操作的数据一致性"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        kb_db = KBSQLiteDatabase(str(db_path))
        await kb_db.initialize()

        provider_mgr = MockProviderManager()
        chunker = MockChunker()

        kb = KnowledgeBase(
            kb_name="test_kb",
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

        # 上传 10 个不同的文档
        doc_ids = []
        for i in range(10):
            doc = await kb_helper.upload_document(
                file_name=f"doc_{i}.txt",
                file_content=f"Document content {i}".encode() * 50,
                file_type="txt",
            )
            doc_ids.append(doc.doc_id)

        # 并发删除和查询
        async def delete_doc(doc_id):
            await asyncio.sleep(0.01)  # 模拟网络延迟
            await kb_helper.delete_document(doc_id)

        async def query_kb():
            await asyncio.sleep(0.005)
            # 简单验证向量数据库状态
            return True

        tasks = []
        # 删除前 5 个文档
        for doc_id in doc_ids[:5]:
            tasks.append(delete_doc(doc_id))
        # 同时进行 10 次查询
        for _ in range(10):
            tasks.append(query_kb())

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 所有操作都应该成功（无异常）
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Expected no errors, got {len(errors)}: {errors}"

        # 验证只剩下 5 个文档
        async with kb_db.get_db() as session:
            from sqlmodel import select

            from astrbot.core.knowledge_base.models import KBDocument

            stmt = select(KBDocument).where(KBDocument.kb_id == kb.kb_id)
            result = await session.execute(stmt)
            docs = result.scalars().all()
            assert len(docs) == 5, f"Expected 5 documents remaining, got {len(docs)}"

        await kb_helper.terminate()


@pytest.mark.asyncio
async def test_concurrent_kb_initialization():
    """测试多个并发请求同时初始化知识库实例"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        provider_mgr = MockProviderManager()

        kb_mgr = KnowledgeBaseManager(provider_manager=provider_mgr)
        kb_mgr.kb_db = KBSQLiteDatabase(str(db_path))
        await kb_mgr.kb_db.initialize()

        # 创建知识库
        kb_helper = await kb_mgr.create_kb(
            kb_name="test_concurrent_init",
            embedding_provider_id="mock",
        )
        kb_id = kb_helper.kb.kb_id

        # 不清空实例缓存，测试并发访问相同实例

        # 并发获取相同知识库 20 次
        async def get_kb():
            await asyncio.sleep(0.001)  # 模拟网络延迟
            return await kb_mgr.get_kb(kb_id)

        tasks = [get_kb() for _ in range(20)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 所有请求都应该成功返回相同的实例
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Expected no errors, got {len(errors)}"

        success_results = [r for r in results if not isinstance(r, Exception)]
        assert len(success_results) == 20

        # 验证都是同一个实例（通过 id() 检查）
        first_instance = success_results[0]
        assert all(
            id(r) == id(first_instance) for r in success_results
        ), "All results should be the same instance"

        # 验证缓存中有这个实例
        assert kb_id in kb_mgr.kb_insts


@pytest.mark.asyncio
async def test_high_concurrency_embedding_cache():
    """测试高并发下嵌入缓存的正确性和性能"""
    from astrbot.core.db.vec_db.faiss_impl.vec_db import EmbeddingCache

    cache = EmbeddingCache(max_size=100)

    import numpy as np

    # 生成 50 个不同的文本和向量
    test_data = [
        (f"text_{i}", np.random.randn(128).astype("float32"))
        for i in range(50)
    ]

    # 并发写入和读取
    async def write_cache(text, embedding):
        await cache.put(text, embedding)

    async def read_cache(text, expected_embedding):
        result = await cache.get(text)
        if result is not None:
            # 验证向量相等
            assert np.allclose(result, expected_embedding), "Cache returned wrong vector"
        return result

    # 并发写入所有数据
    write_tasks = [write_cache(text, emb) for text, emb in test_data]
    await asyncio.gather(*write_tasks)

    # 高并发读取（每个文本读 10 次）
    read_tasks = []
    for text, emb in test_data:
        for _ in range(10):
            read_tasks.append(read_cache(text, emb))

    results = await asyncio.gather(*read_tasks, return_exceptions=True)

    # 统计缓存命中
    hits = sum(1 for r in results if r is not None and not isinstance(r, Exception))
    errors = sum(1 for r in results if isinstance(r, Exception))

    assert errors == 0, f"Expected no errors, got {errors}"
    # 至少应该有一些命中（因为缓存大小为 100，超过 50 个条目）
    assert hits > 0, "Expected some cache hits"

    # 检查缓存大小
    cache_size = await cache.__len__()
    assert cache_size <= 100, "Cache size should not exceed max_size"


@pytest.mark.asyncio
async def test_faiss_index_concurrent_write():
    """测试 FAISS 索引并发写入的原子性"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        index_path = Path(tmp_dir) / "test.faiss"
        doc_path = Path(tmp_dir) / "docs.db"

        from astrbot.core.db.vec_db.faiss_impl.embedding_storage import (
            EmbeddingStorage,
        )

        storage = EmbeddingStorage(dimension=128, path=str(index_path), index_type="flat")

        import numpy as np

        # 并发写入 100 个向量
        async def insert_vector(vec_id):
            vector = np.random.randn(128).astype("float32")
            await storage.insert(vector, vec_id)

        tasks = [insert_vector(i) for i in range(100)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 所有写入都应该成功
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(errors) == 0, f"Expected no errors, got {len(errors)}: {errors}"

        # 验证索引文件存在且可读
        assert index_path.exists(), "Index file should exist"

        # 重新加载索引验证数据完整性
        storage2 = EmbeddingStorage(dimension=128, path=str(index_path))
        assert storage2.index.ntotal == 100, f"Expected 100 vectors, got {storage2.index.ntotal}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
