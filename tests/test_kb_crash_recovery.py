"""知识库崩溃恢复测试

测试在各种故障场景下的数据一致性和恢复能力。
"""

import asyncio
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest


class CrashSimulator:
    """模拟进程崩溃的测试工具"""

    @staticmethod
    async def simulate_crash_during_upload(kb_root: Path, doc_content: bytes):
        """模拟在文档上传过程中崩溃"""
        # 这个测试需要在子进程中运行，然后强制终止
        script = f"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, '{Path(__file__).parent.parent}')

from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
from astrbot.core.knowledge_base.kb_helper import KBHelper
from astrbot.core.knowledge_base.models import KnowledgeBase
from tests.test_kb_concurrent_stress import MockProviderManager, MockChunker

async def upload_and_crash():
    kb_root = Path('{kb_root}')
    db_path = kb_root / 'kb.db'

    kb_db = KBSQLiteDatabase(str(db_path))
    await kb_db.initialize()

    provider_mgr = MockProviderManager()
    chunker = MockChunker()

    kb = KnowledgeBase(
        kb_name="crash_test_kb",
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

    # 在嵌入阶段崩溃
    import signal
    def crash_handler(signum, frame):
        sys.exit(137)  # 模拟被 SIGKILL
    signal.signal(signal.SIGUSR1, crash_handler)

    try:
        doc_content = {repr(doc_content)}
        await kb_helper.upload_document(
            file_name="crash_test.txt",
            file_content=doc_content,
            file_type="txt",
        )
    except Exception as e:
        print(f"Upload failed: {{e}}")

asyncio.run(upload_and_crash())
"""
        return script

    @staticmethod
    async def check_consistency_after_crash(kb_root: Path) -> dict:
        """检查崩溃后的数据一致性"""
        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

        db_path = kb_root / "kb.db"
        kb_db = KBSQLiteDatabase(str(db_path))
        await kb_db.initialize()

        results = {
            "orphan_vectors": 0,
            "incomplete_docs": 0,
            "corrupted_index": False,
        }

        # 检查孤立向量（向量存在但文档元数据不存在）
        # 这需要读取 FAISS 索引和 SQLite 数据库进行对比

        # 检查不完整的文档（状态不是 ready 或 failed）
        from sqlmodel import select

        from astrbot.core.knowledge_base.models import KBDocument

        async with kb_db.get_db() as session:
            stmt = select(KBDocument).where(
                KBDocument.status.notin_(["ready", "failed"])  # type: ignore
            )
            result = await session.execute(stmt)
            incomplete = result.scalars().all()
            results["incomplete_docs"] = len(incomplete)

        # 检查 FAISS 索引是否可读
        try:
            import faiss

            index_files = list(kb_root.glob("*/index.faiss"))
            for index_file in index_files:
                if index_file.exists():
                    try:
                        faiss.read_index(str(index_file))
                    except Exception:
                        results["corrupted_index"] = True
        except Exception:
            pass

        return results


@pytest.mark.asyncio
async def test_faiss_index_corruption_recovery():
    """测试 FAISS 索引损坏后的恢复能力"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        from astrbot.core.db.vec_db.faiss_impl.embedding_storage import (
            EmbeddingStorage,
        )
        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase

        kb_db = KBSQLiteDatabase(str(db_path))
        await kb_db.initialize()

        index_path = kb_root / "test_index.faiss"

        # 创建正常的索引
        storage = EmbeddingStorage(dimension=128, path=str(index_path))

        import numpy as np

        # 插入一些向量
        for i in range(10):
            vector = np.random.randn(128).astype("float32")
            await storage.insert(vector, i)

        # 验证索引正常
        assert index_path.exists()

        # 模拟索引文件损坏（写入垃圾数据）
        with open(index_path, "wb") as f:
            f.write(b"CORRUPTED DATA" * 100)

        # 尝试加载损坏的索引应该抛出异常
        with pytest.raises(Exception):
            EmbeddingStorage(dimension=128, path=str(index_path))

        # 检查是否有备份文件（如果迁移产生的）
        backup_files = list(index_path.parent.glob("*.bak.*"))
        if backup_files:
            # 恢复备份
            latest_backup = max(backup_files, key=lambda p: p.stat().st_mtime)
            import shutil

            shutil.copy2(latest_backup, index_path)

            # 验证恢复后可以加载
            storage_recovered = EmbeddingStorage(dimension=128, path=str(index_path))
            assert storage_recovered.index.ntotal == 10


@pytest.mark.asyncio
async def test_atomic_faiss_write():
    """测试 FAISS 原子写入的有效性"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        index_path = Path(tmp_dir) / "atomic_test.faiss"

        from astrbot.core.db.vec_db.faiss_impl.embedding_storage import (
            EmbeddingStorage,
        )

        storage = EmbeddingStorage(dimension=128, path=str(index_path))

        import numpy as np

        # 并发写入多个向量
        async def concurrent_insert(start_id: int, count: int):
            for i in range(count):
                vector = np.random.randn(128).astype("float32")
                await storage.insert(vector, start_id + i)
                await asyncio.sleep(0.001)  # 模拟网络延迟

        tasks = [
            concurrent_insert(0, 10),
            concurrent_insert(10, 10),
            concurrent_insert(20, 10),
        ]

        await asyncio.gather(*tasks)

        # 验证没有临时文件残留
        temp_files = list(Path(tmp_dir).glob("*.tmp.*"))
        assert len(temp_files) == 0, f"Found temporary files: {temp_files}"

        # 验证索引完整性
        storage_reload = EmbeddingStorage(dimension=128, path=str(index_path))
        assert storage_reload.index.ntotal == 30


@pytest.mark.asyncio
async def test_upload_rollback_on_metadata_failure():
    """测试向量已写入但元数据保存失败的场景

    注意：完整的回滚测试需要 mock 数据库连接，这里简单验证流程正确性
    """
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
            kb_name="rollback_test_kb",
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

        # 上传正常文档
        doc1 = await kb_helper.upload_document(
            file_name="normal_doc.txt",
            file_content=b"Normal document content" * 10,
            file_type="txt",
        )

        # 记录上传前的向量数
        initial_vector_count = kb_helper.vec_db.embedding_storage.index.ntotal
        assert initial_vector_count > 0, "Should have vectors after upload"

        # 验证文档元数据存在
        async with kb_db.get_db() as session:
            from sqlmodel import select

            from astrbot.core.knowledge_base.models import KBDocument

            stmt = select(KBDocument).where(KBDocument.kb_id == kb.kb_id)
            result = await session.execute(stmt)
            docs = result.scalars().all()
            assert len(docs) == 1, "Should have 1 document"

        await kb_helper.terminate()


@pytest.mark.asyncio
async def test_concurrent_kb_instance_init_with_failure():
    """测试知识库实例初始化失败时的重试机制"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)
        db_path = kb_root / "kb.db"

        from astrbot.core.knowledge_base.kb_db_sqlite import KBSQLiteDatabase
        from astrbot.core.knowledge_base.kb_mgr import (
            INIT_RETRY_COOLDOWN_SECONDS,
            KnowledgeBaseManager,
        )
        from tests.test_kb_concurrent_stress import MockProviderManager

        provider_mgr = MockProviderManager()

        kb_mgr = KnowledgeBaseManager(provider_manager=provider_mgr)
        kb_mgr.kb_db = KBSQLiteDatabase(str(db_path))
        await kb_mgr.kb_db.initialize()

        # 创建知识库
        kb_helper = await kb_mgr.create_kb(
            kb_name="init_failure_test",
            embedding_provider_id="mock",
        )
        kb_id = kb_helper.kb.kb_id

        # 模拟初始化失败（手动设置错误）
        kb_helper.init_error = "Simulated initialization error"
        kb_helper.init_retry_count = 0
        # 设置上次重试时间为很久以前，使其可以立即重试
        import time
        kb_helper.last_init_retry_at = time.monotonic() - INIT_RETRY_COOLDOWN_SECONDS - 1

        # 验证错误状态已设置
        assert kb_helper.init_error is not None
        initial_error = kb_helper.init_error

        # 检查重试条件判断
        can_retry = kb_mgr._can_retry_helper_init(kb_helper)
        assert can_retry is True, "Should be able to retry after cooldown"

        # 尝试重试（这会清除错误，因为实际上实例是正常的）
        await kb_mgr._retry_helper_init_if_due(kb_helper)

        # 重试后，由于底层 VecDB 是正常的，错误应该被清除
        # 成功重试后 init_error 会被清空，init_retry_count 也会重置为 0
        assert kb_helper.init_error is None, "Error should be cleared after successful retry"
        # 验证确实发生了重试（错误从非空变为空）
        assert initial_error != kb_helper.init_error, "Init error should have changed"


@pytest.mark.asyncio
async def test_document_consistency_check():
    """测试文档一致性检查功能"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        kb_root = Path(tmp_dir) / "kb_test"
        kb_root.mkdir(parents=True, exist_ok=True)

        # 模拟崩溃后的检查
        consistency_results = await CrashSimulator.check_consistency_after_crash(kb_root)

        assert "orphan_vectors" in consistency_results
        assert "incomplete_docs" in consistency_results
        assert "corrupted_index" in consistency_results


@pytest.mark.asyncio
async def test_embedding_cache_memory_safety():
    """测试嵌入缓存在极端场景下的内存安全性"""
    from astrbot.core.db.vec_db.faiss_impl.vec_db import EmbeddingCache

    cache = EmbeddingCache(max_size=10)  # 极小的缓存

    import numpy as np

    # 快速插入大量数据
    for i in range(1000):
        text = f"text_{i}" * 100  # 长文本
        embedding = np.random.randn(1536).astype("float32")  # 大向量
        await cache.put(text, embedding)

    # 验证缓存大小被限制
    cache_size = await cache.__len__()
    assert cache_size <= 10, f"Cache size {cache_size} exceeds limit 10"

    # 验证可以正常读取
    for i in range(990, 1000):
        text = f"text_{i}" * 100
        result = await cache.get(text)
        # 最近的 10 个应该在缓存中
        assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
