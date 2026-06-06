"""Tests for batch knowledge-base document deletion."""

import sqlite3
from unittest.mock import AsyncMock, MagicMock, call

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
    helper.kb_db = AsyncMock()
    helper.kb_db.get_document_by_id = AsyncMock(return_value=None)
    helper.kb_db.list_media_by_doc = AsyncMock(return_value=[])
    helper.vec_db = AsyncMock()
    helper.refresh_kb = AsyncMock()
    return helper


def _build_helper_with_real_dirs(tmp_path):
    helper = _build_helper()
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
            kb_id="kb-test-1",
            vec_db=helper.vec_db,
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
    async def test_delete_document_cleans_source_and_media_files(self, tmp_path):
        from astrbot.core.knowledge_base.models import KBDocument, KBMedia

        helper = _build_helper_with_real_dirs(tmp_path)
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

        helper = _build_helper_with_real_dirs(tmp_path)
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
