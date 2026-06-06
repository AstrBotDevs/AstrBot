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
