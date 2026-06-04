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
