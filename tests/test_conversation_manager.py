"""Tests for astrbot.core.conversation_mgr module."""

from unittest.mock import MagicMock

import pytest

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db import BaseDatabase


class TestConversationManager:
    """Smoke tests for ConversationManager."""

    def test_module_import(self):
        """Verify the conversation_mgr module can be imported."""
        import astrbot.core.conversation_mgr  # noqa: F811
        assert hasattr(
            astrbot.core.conversation_mgr,
            "ConversationManager",
        )

    def test_class_exists(self):
        """Verify ConversationManager class exists."""
        assert ConversationManager.__name__ == "ConversationManager"

    def test_init_requires_db_helper(self):
        """Verify ConversationManager init requires BaseDatabase."""
        db = MagicMock(spec=BaseDatabase)
        mgr = ConversationManager(db)
        assert mgr.db is db
        assert mgr.session_conversations == {}
        assert mgr.save_interval == 60

    def test_register_on_session_deleted_adds_callback(self):
        """Verify register_on_session_deleted adds a callback."""
        db = MagicMock(spec=BaseDatabase)
        mgr = ConversationManager(db)

        async def dummy_callback(unified_msg_origin: str) -> None:
            pass

        assert len(mgr._on_session_deleted_callbacks) == 0
        mgr.register_on_session_deleted(dummy_callback)
        assert len(mgr._on_session_deleted_callbacks) == 1
        assert mgr._on_session_deleted_callbacks[0] is dummy_callback
