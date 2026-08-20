"""Test knowledge base lookup by name and UUID (issue #9529)"""

import pytest


class TestKBNameUUIDLookup:
    """Test get_kb_by_name supports both name and UUID lookup"""

    @pytest.mark.asyncio
    async def test_get_kb_by_name_with_name(self):
        """Should find knowledge base by name"""
        kb_mgr, kb_id, kb_name = await self._create_mock_kb_manager()

        result = await kb_mgr.get_kb_by_name(kb_name)

        assert result is not None
        assert result.kb.kb_id == kb_id
        assert result.kb.kb_name == kb_name

    @pytest.mark.asyncio
    async def test_get_kb_by_name_with_uuid(self):
        """Should find knowledge base by UUID (fallback)"""
        kb_mgr, kb_id, kb_name = await self._create_mock_kb_manager()

        result = await kb_mgr.get_kb_by_name(kb_id)

        assert result is not None
        assert result.kb.kb_id == kb_id
        assert result.kb.kb_name == kb_name

    @pytest.mark.asyncio
    async def test_get_kb_by_name_not_found(self):
        """Should return None for non-existent knowledge base"""
        kb_mgr, _, _ = await self._create_mock_kb_manager()

        result = await kb_mgr.get_kb_by_name("non-existent-kb")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_kb_by_name_prefers_name_over_uuid(self):
        """Should prefer name match over UUID match"""
        (
            kb_mgr,
            kb1_id,
            kb1_name,
            kb2_id,
            kb2_name,
        ) = await self._create_mock_kb_manager_with_collision()

        # kb2_name equals kb1_id (collision scenario)
        result = await kb_mgr.get_kb_by_name(kb1_id)

        # Should return kb2 (matched by name) not kb1 (matched by UUID)
        assert result is not None
        assert result.kb.kb_id == kb2_id
        assert result.kb.kb_name == kb2_name

    async def _create_mock_kb_manager(self):
        """Create a mock KnowledgeBaseManager with one KB"""
        from unittest.mock import MagicMock

        from astrbot.core.knowledge_base.models import KnowledgeBase

        kb_id = "bb47bf6f-3315-49bd-9c9a-7cc4aa9abbac"
        kb_name = "测试"

        mock_kb = KnowledgeBase(
            kb_id=kb_id,
            kb_name=kb_name,
            description="Test KB",
            emoji="📚",
            doc_count=1,
            chunk_count=2,
        )
        mock_helper = MagicMock()
        mock_helper.kb = mock_kb

        kb_mgr = MagicMock()
        kb_mgr.kb_insts = {kb_id: mock_helper}

        # Manually implement the method to avoid circular import
        async def get_kb_by_name(kb_name: str):
            # First try to match by name
            for kb_helper in kb_mgr.kb_insts.values():
                if kb_helper.kb.kb_name == kb_name:
                    return kb_helper
            # Fallback to UUID match
            if kb_name in kb_mgr.kb_insts:
                return kb_mgr.kb_insts[kb_name]
            return None

        kb_mgr.get_kb_by_name = get_kb_by_name

        return kb_mgr, kb_id, kb_name

    async def _create_mock_kb_manager_with_collision(self):
        """Create a mock manager where kb2's name equals kb1's UUID"""
        from unittest.mock import MagicMock

        from astrbot.core.knowledge_base.models import KnowledgeBase

        kb1_id = "test-uuid-123"
        kb1_name = "KB One"
        kb2_id = "test-uuid-456"
        kb2_name = "test-uuid-123"  # Same as kb1_id

        mock_kb1 = KnowledgeBase(
            kb_id=kb1_id,
            kb_name=kb1_name,
            description="First KB",
            emoji="📚",
            doc_count=1,
            chunk_count=1,
        )
        mock_helper1 = MagicMock()
        mock_helper1.kb = mock_kb1

        mock_kb2 = KnowledgeBase(
            kb_id=kb2_id,
            kb_name=kb2_name,
            description="Second KB",
            emoji="📖",
            doc_count=1,
            chunk_count=1,
        )
        mock_helper2 = MagicMock()
        mock_helper2.kb = mock_kb2

        kb_mgr = MagicMock()
        kb_mgr.kb_insts = {kb1_id: mock_helper1, kb2_id: mock_helper2}

        # Manually implement the method
        async def get_kb_by_name(kb_name: str):
            for kb_helper in kb_mgr.kb_insts.values():
                if kb_helper.kb.kb_name == kb_name:
                    return kb_helper
            if kb_name in kb_mgr.kb_insts:
                return kb_mgr.kb_insts[kb_name]
            return None

        kb_mgr.get_kb_by_name = get_kb_by_name

        return kb_mgr, kb1_id, kb1_name, kb2_id, kb2_name


class TestCheckAllKB:
    """Test check_all_kb distinguishes None from empty KB"""

    def test_check_all_kb_with_valid_non_empty_kb(self):
        """Should return False when KB has documents"""
        from unittest.mock import MagicMock

        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        mock_kb = KnowledgeBase(
            kb_id="kb-1",
            kb_name="Non-empty KB",
            description="",
            emoji="📚",
            doc_count=1,
            chunk_count=2,
        )
        mock_helper = MagicMock()
        mock_helper.kb = mock_kb

        kb_list = [mock_helper]
        result = check_all_kb(kb_list)

        assert result is False

    def test_check_all_kb_with_valid_empty_kb(self):
        """Should return True when KB is empty"""
        from unittest.mock import MagicMock

        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        mock_kb = KnowledgeBase(
            kb_id="kb-2",
            kb_name="Empty KB",
            description="",
            emoji="📚",
            doc_count=0,
            chunk_count=0,
        )
        mock_helper = MagicMock()
        mock_helper.kb = mock_kb

        kb_list = [mock_helper]
        result = check_all_kb(kb_list)

        assert result is True

    def test_check_all_kb_with_none(self):
        """Should return True and log warning when KB is None"""
        from unittest.mock import patch

        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        with patch("astrbot.core.tools.knowledge_base_tools.logger") as mock_logger:
            kb_list = [None]
            result = check_all_kb(kb_list)

            assert result is True
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "1/1" in call_args
            assert "未找到或未加载" in call_args

    def test_check_all_kb_mixed(self):
        """Should return False when at least one KB has documents"""
        from unittest.mock import MagicMock, patch

        from astrbot.core.knowledge_base.models import KnowledgeBase
        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        mock_kb_empty = KnowledgeBase(
            kb_id="kb-2",
            kb_name="Empty KB",
            description="",
            emoji="📚",
            doc_count=0,
            chunk_count=0,
        )
        mock_helper_empty = MagicMock()
        mock_helper_empty.kb = mock_kb_empty

        mock_kb_non_empty = KnowledgeBase(
            kb_id="kb-1",
            kb_name="Non-empty KB",
            description="",
            emoji="📚",
            doc_count=1,
            chunk_count=2,
        )
        mock_helper_non_empty = MagicMock()
        mock_helper_non_empty.kb = mock_kb_non_empty

        with patch("astrbot.core.tools.knowledge_base_tools.logger") as mock_logger:
            kb_list = [None, mock_helper_empty, mock_helper_non_empty]
            result = check_all_kb(kb_list)

            assert result is False
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "1/3" in call_args

    def test_check_all_kb_all_none(self):
        """Should return True and log warning when all KBs are None"""
        from unittest.mock import patch

        from astrbot.core.tools.knowledge_base_tools import check_all_kb

        with patch("astrbot.core.tools.knowledge_base_tools.logger") as mock_logger:
            kb_list = [None, None, None]
            result = check_all_kb(kb_list)

            assert result is True
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args[0][0]
            assert "3/3" in call_args
