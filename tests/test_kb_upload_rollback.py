"""Tests for vector rollback on upload failure.

The knowledge_base package has a circular import chain:
  kb_helper → provider.manager → persona_mgr → ... → kb_mgr → provider.manager

We break the chain by stubbing provider.manager in sys.modules before any
import, then patch what we need at the instance level.
"""

import sys
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

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
    helper.kb_dir = MagicMock()
    helper.kb_medias_dir = MagicMock()
    helper.kb_files_dir = MagicMock()
    helper.prov_mgr = MagicMock()
    helper.chunker = AsyncMock()
    helper.vec_db = AsyncMock()
    helper._ensure_vec_db = AsyncMock()
    helper.init_error = None
    return helper


def _mock_parser(mock_select):
    parser = AsyncMock()
    result = MagicMock()
    type(result).text = PropertyMock(return_value="hello world test content")
    type(result).media = PropertyMock(return_value=[])
    parser.parse = AsyncMock(return_value=result)
    mock_select.return_value = parser


class TestUploadDocumentRollback:
    """Verify vectors are cleaned up when metadata save fails after insert."""

    @pytest.mark.asyncio
    async def test_rollback_when_metadata_save_fails(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select, patch(
            "astrbot.core.knowledge_base.kb_helper._compact_chunks",
            return_value=["chunk 1", "chunk 2", "chunk 3"],
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

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select, patch(
            "astrbot.core.knowledge_base.kb_helper._compact_chunks",
            return_value=["chunk 1"],
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch.side_effect = KnowledgeBaseUploadError(
                stage="embedding", user_message="模拟失败", details={},
            )
            helper.vec_db.delete_documents = AsyncMock()

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt", file_content=b"hello", file_type="txt",
                )

            assert exc_info.value.stage == "embedding"
            helper.vec_db.delete_documents.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cleanup_failure_does_not_suppress_original_error(self):
        from astrbot.core.exceptions import KnowledgeBaseUploadError

        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select, patch(
            "astrbot.core.knowledge_base.kb_helper._compact_chunks",
            return_value=["chunk 1"],
        ):
            _mock_parser(mock_select)
            helper = _build_helper()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1])
            helper.vec_db.delete_documents.side_effect = RuntimeError("cleanup fail")
            helper.kb_db.get_db.side_effect = RuntimeError("DB lost")

            with pytest.raises(KnowledgeBaseUploadError) as exc_info:
                await helper.upload_document(
                    file_name="test.txt", file_content=b"hello", file_type="txt",
                )

            assert exc_info.value.stage == "metadata"
            helper.vec_db.delete_documents.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_rollback_on_success(self):
        with patch(
            "astrbot.core.knowledge_base.kb_helper.select_parser",
            new_callable=AsyncMock,
        ) as mock_select, patch(
            "astrbot.core.knowledge_base.kb_helper._compact_chunks",
            return_value=["chunk 1", "chunk 2"],
        ):
            _mock_parser(mock_select)
            helper = _build_helper()

            # session mock that survives `async with ... as session, session.begin():`
            session = AsyncMock()
            session.__aenter__.return_value = session  # as clause gets this session
            session.begin = MagicMock(return_value=session)  # second async with
            helper.kb_db.get_db = MagicMock(return_value=session)
            helper.kb_db.update_kb_stats = AsyncMock()
            helper.vec_db.insert_batch = AsyncMock(return_value=[1, 2])
            helper.vec_db.delete_documents = AsyncMock()
            helper.vec_db.count_documents = AsyncMock(return_value=2)
            helper.refresh_kb = AsyncMock()
            helper.refresh_document = AsyncMock()

            doc = await helper.upload_document(
                file_name="test.txt", file_content=b"hello world", file_type="txt",
            )

            assert doc is not None
            helper.vec_db.delete_documents.assert_not_awaited()
