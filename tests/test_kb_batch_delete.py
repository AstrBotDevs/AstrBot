"""Tests for batch knowledge-base document deletion."""

import sqlite3
import sys
from unittest.mock import AsyncMock, MagicMock, call

import pytest

# ── Break circular import BEFORE any knowledge_base module is touched ──
_mock_pm = MagicMock()
_mock_pm.ProviderManager = MagicMock()
sys.modules["astrbot.core.provider.manager"] = _mock_pm


def _build_helper():
    from astrbot.core.knowledge_base.kb_helper import KBHelper
    from astrbot.core.knowledge_base.models import KnowledgeBase

    kb = KnowledgeBase(
        kb_name="test-kb", kb_id="kb-test-1",
        embedding_provider_id="emb-1",
        chunk_size=512, chunk_overlap=50,
    )
    helper = KBHelper.__new__(KBHelper)
    helper.kb = kb
    helper.kb_db = AsyncMock()
    helper.vec_db = AsyncMock()
    helper.refresh_kb = AsyncMock()
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
            ["doc-1", "doc-2", "doc-3"], vec_db,
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
            ["doc-1", "doc-2", "doc-3"], vec_db,
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
        helper = _build_helper()
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
            kb_id="kb-test-1", vec_db=helper.vec_db,
        )
        helper.refresh_kb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_documents_empty_list(self):
        """Empty list delegates to kb_db layer (returns empty dict)."""
        helper = _build_helper()
        helper.kb_db.delete_documents_by_ids = AsyncMock(return_value={})

        results = await helper.delete_documents([])

        assert results == {}
        helper.kb_db.update_kb_stats.assert_awaited_once()
        helper.refresh_kb.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_documents_preserves_failures(self):
        """Failures from kb_db layer are propagated in the result dict."""
        helper = _build_helper()
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
        helper = _build_helper()
        helper.vec_db.delete = AsyncMock(return_value=False)

        with pytest.raises(ValueError, match="无法找到 ID 为 chunk-missing 的文本块"):
            await helper.delete_chunk("chunk-missing", "doc-1")

        helper.vec_db.delete.assert_awaited_once_with("chunk-missing")
        helper.kb_db.update_kb_stats.assert_not_awaited()
        helper.refresh_kb.assert_not_awaited()


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
