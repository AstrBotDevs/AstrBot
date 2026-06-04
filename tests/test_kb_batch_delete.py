"""Tests for #3: Batch delete documents API.

Verifies:
- Batch delete from kb.db (single SQL IN clause)
- Parallel vec_db cleanup
- Single update_kb_stats call (not N calls)
- Best-effort semantics: one failure doesn't block others
- Empty list edge case

NOTE: The knowledge_base package has a circular import chain:
  kb_helper → provider.manager → persona_mgr → ... → kb_mgr → provider.manager
We break the chain by stubbing provider.manager in sys.modules before any import.
"""

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
        """Documents deleted from kb.db via single IN-clause SQL."""
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
