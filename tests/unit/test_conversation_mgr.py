"""Tests for ConversationManager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import ConversationV2


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.create_conversation = AsyncMock()
    db.get_conversation_by_id = AsyncMock()
    db.delete_conversation = AsyncMock()
    db.delete_conversations_by_user_id = AsyncMock()
    db.update_conversation = AsyncMock()
    db.get_conversations = AsyncMock(return_value=[])
    db.get_filtered_conversations = AsyncMock(return_value=([], 0))
    return db


@pytest.fixture
def conversation_manager(mock_db):
    """Create a ConversationManager instance."""
    return ConversationManager(mock_db)


class TestConversationManagerInit:
    """Tests for ConversationManager initialization."""

    def test_init(self, mock_db):
        """Test initialization."""
        manager = ConversationManager(mock_db)
        assert manager.db == mock_db
        assert manager.session_conversations == {}
        assert manager.save_interval == 60
        assert manager._on_session_deleted_callbacks == []

    def test_register_on_session_deleted(self, conversation_manager):
        """Test registering a session deleted callback."""
        callback = AsyncMock()
        conversation_manager.register_on_session_deleted(callback)
        assert callback in conversation_manager._on_session_deleted_callbacks

    @pytest.mark.asyncio
    async def test_trigger_session_deleted_callback_exception(
        self, conversation_manager
    ):
        """Test that exception in one callback doesn't affect others.

        When one session deleted callback raises an exception,
        other callbacks should still be executed.
        This verifies the exception handling at lines 49-57 in conversation_mgr.py.
        """
        # Register two callbacks: one that fails, one that succeeds
        failing_callback = AsyncMock(side_effect=RuntimeError("Callback error"))
        success_callback = AsyncMock()

        conversation_manager.register_on_session_deleted(failing_callback)
        conversation_manager.register_on_session_deleted(success_callback)

        # Trigger the callbacks - should not raise exception
        with patch("astrbot.core.logger") as mock_logger:
            await conversation_manager._trigger_session_deleted("test:group:123")

        # Both callbacks should have been called
        failing_callback.assert_called_once_with("test:group:123")
        success_callback.assert_called_once_with("test:group:123")

        # Error should have been logged
        mock_logger.error.assert_called_once()
        error_msg = mock_logger.error.call_args[0][0]
        assert "test:group:123" in error_msg
        assert "Callback error" in str(error_msg)


class TestNewConversation:
    """Tests for new_conversation method."""

    @pytest.mark.asyncio
    async def test_new_conversation_basic(self, conversation_manager, mock_db):
        """Test creating a new conversation."""
        mock_conv = MagicMock()
        mock_conv.conversation_id = "test-conv-id"
        mock_db.create_conversation.return_value = mock_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            conv_id = await conversation_manager.new_conversation(
                unified_msg_origin="test_platform:group:123456"
            )

        assert conv_id == "test-conv-id"
        assert (
            conversation_manager.session_conversations["test_platform:group:123456"]
            == "test-conv-id"
        )
        mock_db.create_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_conversation_with_platform_id(
        self, conversation_manager, mock_db
    ):
        """Test creating a new conversation with explicit platform_id."""
        mock_conv = MagicMock()
        mock_conv.conversation_id = "test-conv-id"
        mock_db.create_conversation.return_value = mock_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            conv_id = await conversation_manager.new_conversation(
                unified_msg_origin="test:group:123", platform_id="custom_platform"
            )

        assert conv_id == "test-conv-id"
        mock_db.create_conversation.assert_called_once_with(
            user_id="test:group:123",
            platform_id="custom_platform",
            content=None,
            title=None,
            persona_id=None,
        )

    @pytest.mark.asyncio
    async def test_new_conversation_with_content(self, conversation_manager, mock_db):
        """Test creating a new conversation with content."""
        mock_conv = MagicMock()
        mock_conv.conversation_id = "test-conv-id"
        mock_db.create_conversation.return_value = mock_conv

        content = [{"role": "user", "content": "Hello"}]

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            conv_id = await conversation_manager.new_conversation(
                unified_msg_origin="test:group:123",
                content=content,
                title="Test Title",
                persona_id="test-persona",
            )

        assert conv_id == "test-conv-id"
        mock_db.create_conversation.assert_called_once_with(
            user_id="test:group:123",
            platform_id="test",
            content=content,
            title="Test Title",
            persona_id="test-persona",
        )

    @pytest.mark.asyncio
    async def test_new_conversation_platform_id_fallback(
        self, conversation_manager, mock_db
    ):
        """Test creating conversation with malformed unified_msg_origin falls back to 'unknown'.

        When unified_msg_origin format is not 'platform:type:id', platform_id should fallback to 'unknown'.
        This verifies the defensive coding at lines 91-97 in conversation_mgr.py.
        """
        mock_conv = MagicMock()
        mock_conv.conversation_id = "test-conv-id"
        mock_db.create_conversation.return_value = mock_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            # Test with malformed format (no colons)
            conv_id = await conversation_manager.new_conversation(
                unified_msg_origin="invalid_format_without_colons"
            )

        assert conv_id == "test-conv-id"
        # Verify platform_id fallback to 'unknown'
        mock_db.create_conversation.assert_called_once_with(
            user_id="invalid_format_without_colons",
            platform_id="unknown",
            content=None,
            title=None,
            persona_id=None,
        )

    @pytest.mark.asyncio
    async def test_new_conversation_platform_id_partial_fallback(
        self, conversation_manager, mock_db
    ):
        """Test fallback with partial format (only 1 colon).

        When unified_msg_origin has fewer than 3 parts after splitting by ':',
        platform_id should fallback to 'unknown'.
        """
        mock_conv = MagicMock()
        mock_conv.conversation_id = "test-conv-id"
        mock_db.create_conversation.return_value = mock_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            # Test with partial format (only 1 colon, needs at least 2 for 3 parts)
            conv_id = await conversation_manager.new_conversation(
                unified_msg_origin="platform:only_two_parts"
            )

        assert conv_id == "test-conv-id"
        # Verify platform_id fallback to 'unknown' because len(parts) == 2 < 3
        mock_db.create_conversation.assert_called_once_with(
            user_id="platform:only_two_parts",
            platform_id="unknown",
            content=None,
            title=None,
            persona_id=None,
        )


class TestSwitchConversation:
    """Tests for switch_conversation method."""

    @pytest.mark.asyncio
    async def test_switch_conversation(self, conversation_manager):
        """Test switching conversation."""
        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            await conversation_manager.switch_conversation(
                unified_msg_origin="test:group:123", conversation_id="new-conv-id"
            )

        assert (
            conversation_manager.session_conversations["test:group:123"]
            == "new-conv-id"
        )
        mock_sp.session_put.assert_called_once()


class TestDeleteConversation:
    """Tests for delete_conversation method."""

    @pytest.mark.asyncio
    async def test_delete_conversation_by_id(self, conversation_manager, mock_db):
        """Test deleting a specific conversation."""
        conversation_manager.session_conversations["test:group:123"] = "conv-to-delete"

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_remove = AsyncMock()
            conversation_manager.get_curr_conversation_id = AsyncMock(
                return_value="conv-to-delete"
            )

            await conversation_manager.delete_conversation(
                unified_msg_origin="test:group:123", conversation_id="conv-to-delete"
            )

        mock_db.delete_conversation.assert_called_once_with(cid="conv-to-delete")
        mock_sp.session_remove.assert_called_once_with("test:group:123", "sel_conv_id")
        assert "test:group:123" not in conversation_manager.session_conversations

    @pytest.mark.asyncio
    async def test_delete_current_conversation(self, conversation_manager, mock_db):
        """Test deleting current conversation when no ID provided."""
        conversation_manager.session_conversations["test:group:123"] = "current-conv"

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_remove = AsyncMock()
            conversation_manager.get_curr_conversation_id = AsyncMock(
                return_value="current-conv"
            )

            await conversation_manager.delete_conversation(
                unified_msg_origin="test:group:123"
            )

        mock_db.delete_conversation.assert_called_once_with(cid="current-conv")
        mock_sp.session_remove.assert_called_once_with("test:group:123", "sel_conv_id")
        assert "test:group:123" not in conversation_manager.session_conversations

    @pytest.mark.asyncio
    async def test_delete_conversations_by_user_id(self, conversation_manager, mock_db):
        """Test deleting all conversations for a user."""
        conversation_manager.session_conversations["test:group:123"] = "conv-id"

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_remove = AsyncMock()

            await conversation_manager.delete_conversations_by_user_id(
                unified_msg_origin="test:group:123"
            )

        mock_db.delete_conversations_by_user_id.assert_called_once_with(
            user_id="test:group:123"
        )
        assert "test:group:123" not in conversation_manager.session_conversations

    @pytest.mark.asyncio
    async def test_delete_conversations_triggers_callback(
        self, conversation_manager, mock_db
    ):
        """Test that deleting conversations triggers registered callbacks."""
        callback = AsyncMock()
        conversation_manager.register_on_session_deleted(callback)

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_remove = AsyncMock()

            await conversation_manager.delete_conversations_by_user_id(
                unified_msg_origin="test:group:123"
            )

        callback.assert_called_once_with("test:group:123")

    @pytest.mark.asyncio
    async def test_delete_conversation_not_current(self, conversation_manager, mock_db):
        """Test deleting a non-current conversation doesn't affect session state.

        When deleting a conversation that is NOT the current one,
        session_conversations should remain unchanged.
        This verifies the conditional logic at lines 139-141 in conversation_mgr.py.
        """
        # Setup: current conversation is "current-conv", we delete "other-conv"
        conversation_manager.session_conversations["test:group:123"] = "current-conv"

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_remove = AsyncMock()
            # Mock get_curr_conversation_id to return the current conversation
            conversation_manager.get_curr_conversation_id = AsyncMock(
                return_value="current-conv"
            )

            await conversation_manager.delete_conversation(
                unified_msg_origin="test:group:123",
                conversation_id="other-conv",  # Different from current
            )

        # Verify the conversation was deleted from DB
        mock_db.delete_conversation.assert_called_once_with(cid="other-conv")
        # Verify session state is NOT affected (not cleared)
        assert "test:group:123" in conversation_manager.session_conversations
        assert (
            conversation_manager.session_conversations["test:group:123"]
            == "current-conv"
        )
        # Verify session_remove was NOT called
        mock_sp.session_remove.assert_not_called()


class TestGetConversation:
    """Tests for get_conversation methods."""

    @pytest.mark.asyncio
    async def test_get_curr_conversation_id_from_cache(self, conversation_manager):
        """Test getting current conversation ID from cache."""
        conversation_manager.session_conversations["test:group:123"] = "cached-conv-id"

        result = await conversation_manager.get_curr_conversation_id(
            unified_msg_origin="test:group:123"
        )

        assert result == "cached-conv-id"

    @pytest.mark.asyncio
    async def test_get_curr_conversation_id_from_storage(self, conversation_manager):
        """Test getting current conversation ID from storage."""
        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_get = AsyncMock(return_value="stored-conv-id")

            result = await conversation_manager.get_curr_conversation_id(
                unified_msg_origin="test:group:123"
            )

        assert result == "stored-conv-id"
        assert (
            conversation_manager.session_conversations["test:group:123"]
            == "stored-conv-id"
        )

    @pytest.mark.asyncio
    async def test_get_curr_conversation_id_not_found(self, conversation_manager):
        """Test getting current conversation ID when not found."""
        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_get = AsyncMock(return_value=None)

            result = await conversation_manager.get_curr_conversation_id(
                unified_msg_origin="test:group:123"
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_conversation_by_id(self, conversation_manager, mock_db):
        """Test getting conversation by ID."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "test-conv-id"
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = []
        mock_conv_v2.title = "Test Title"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0

        mock_db.get_conversation_by_id.return_value = mock_conv_v2

        result = await conversation_manager.get_conversation(
            unified_msg_origin="test:group:123", conversation_id="test-conv-id"
        )

        assert result is not None
        mock_db.get_conversation_by_id.assert_called_once_with(cid="test-conv-id")

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, conversation_manager, mock_db):
        """Test getting conversation when not found."""
        mock_db.get_conversation_by_id.return_value = None

        result = await conversation_manager.get_conversation(
            unified_msg_origin="test:group:123", conversation_id="non-existent"
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_get_conversations_maps_conversation_v2_structure(
        self, conversation_manager, mock_db
    ):
        """Ensure get_conversations maps ConversationV2 to the expected public structure."""
        # Arrange - Create mock ConversationV2 with specific attributes
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "conv1"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.title = "First conversation"
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567999
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.persona_id = "test_persona"
        mock_conv_v2.token_usage = 100
        mock_conv_v2.content = []  # Must be JSON serializable

        mock_db.get_conversations.return_value = [mock_conv_v2]

        # Act
        result = await conversation_manager.get_conversations(
            unified_msg_origin="test:group:123"
        )

        # Assert - Verify ordering and structure of the public response
        assert isinstance(result, list)
        assert len(result) == 1

        conv_public = result[0]
        # Verify public API structure - returns Conversation object with attributes
        assert conv_public.cid == "conv1"
        assert conv_public.user_id == "test:group:123"
        assert conv_public.title == "First conversation"
        assert conv_public.created_at == 1234567890
        assert conv_public.updated_at == 1234567999
        assert conv_public.platform_id == "test_platform"
        assert conv_public.persona_id == "test_persona"
        assert conv_public.token_usage == 100

        mock_db.get_conversations.assert_awaited_once_with(
            user_id="test:group:123", platform_id=None
        )

    @pytest.mark.asyncio
    async def test_get_conversation_create_if_not_exists(
        self, conversation_manager, mock_db
    ):
        """Test getting conversation with create_if_not_exists=True creates new conversation.

        When conversation doesn't exist and create_if_not_exists=True,
        a new conversation should be created automatically.
        This verifies the logic at lines 190-193 in conversation_mgr.py.
        """
        # Setup: first call returns None (not found), second call returns the new conversation
        mock_new_conv = MagicMock(spec=ConversationV2)
        mock_new_conv.conversation_id = "new-conv-id"
        mock_new_conv.platform_id = "test_platform"
        mock_new_conv.user_id = "test:group:123"
        mock_new_conv.content = []
        mock_new_conv.title = "New Conversation"
        mock_new_conv.persona_id = None
        mock_new_conv.created_at = MagicMock()
        mock_new_conv.created_at.timestamp.return_value = 1234567890
        mock_new_conv.updated_at = MagicMock()
        mock_new_conv.updated_at.timestamp.return_value = 1234567890
        mock_new_conv.token_usage = 0

        # First call returns None, second call returns the conversation
        mock_db.get_conversation_by_id.side_effect = [None, mock_new_conv]
        mock_db.create_conversation.return_value = mock_new_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            result = await conversation_manager.get_conversation(
                unified_msg_origin="test:group:123",
                conversation_id="non-existent-id",
                create_if_not_exists=True,
            )

        # Verify new conversation was created
        mock_db.create_conversation.assert_called_once()
        # Verify get_conversation_by_id was called twice (first: None, second: new conv)
        assert mock_db.get_conversation_by_id.call_count == 2
        assert result is not None
        assert result.cid == "new-conv-id"

    @pytest.mark.asyncio
    async def test_get_conversation_create_if_not_exists_false(
        self, conversation_manager, mock_db
    ):
        """Test getting non-existent conversation with create_if_not_exists=False (default).

        When conversation doesn't exist and create_if_not_exists=False (default),
        should return None without creating a new conversation.
        """
        mock_db.get_conversation_by_id.return_value = None

        result = await conversation_manager.get_conversation(
            unified_msg_origin="test:group:123",
            conversation_id="non-existent-id",
            create_if_not_exists=False,  # explicit False
        )

        # Verify no new conversation was created
        mock_db.create_conversation.assert_not_called()
        assert result is None


class TestUpdateConversation:
    """Tests for update_conversation method."""

    @pytest.mark.asyncio
    async def test_update_conversation_with_id(self, conversation_manager, mock_db):
        """Test updating conversation with explicit ID."""
        await conversation_manager.update_conversation(
            unified_msg_origin="test:group:123",
            conversation_id="conv-id",
            title="New Title",
            persona_id="new-persona",
        )

        mock_db.update_conversation.assert_called_once_with(
            cid="conv-id",
            title="New Title",
            persona_id="new-persona",
            content=None,
            token_usage=None,
        )

    @pytest.mark.asyncio
    async def test_update_conversation_without_id(self, conversation_manager, mock_db):
        """Test updating conversation using current ID."""
        conversation_manager.get_curr_conversation_id = AsyncMock(
            return_value="current-conv-id"
        )

        await conversation_manager.update_conversation(
            unified_msg_origin="test:group:123",
            history=[{"role": "user", "content": "Hello"}],
        )

        conversation_manager.get_curr_conversation_id.assert_called_once_with(
            "test:group:123"
        )
        mock_db.update_conversation.assert_called_once_with(
            cid="current-conv-id",
            title=None,
            persona_id=None,
            content=[{"role": "user", "content": "Hello"}],
            token_usage=None,
        )

    @pytest.mark.asyncio
    async def test_update_conversation_no_current_id(
        self, conversation_manager, mock_db
    ):
        """Test updating conversation when no current ID exists."""
        conversation_manager.get_curr_conversation_id = AsyncMock(return_value=None)

        await conversation_manager.update_conversation(
            unified_msg_origin="test:group:123", title="New Title"
        )

        mock_db.update_conversation.assert_not_called()


class TestAddMessagePair:
    """Tests for add_message_pair method."""

    @pytest.mark.asyncio
    async def test_add_message_pair_dicts(self, conversation_manager, mock_db):
        """Test adding message pair as dicts."""
        mock_conv = MagicMock()
        mock_conv.content = []
        mock_db.get_conversation_by_id.return_value = mock_conv

        user_msg = {"role": "user", "content": "Hello"}
        assistant_msg = {"role": "assistant", "content": "Hi there!"}

        await conversation_manager.add_message_pair(
            cid="conv-id", user_message=user_msg, assistant_message=assistant_msg
        )

        mock_db.update_conversation.assert_called_once()
        call_args = mock_db.update_conversation.call_args
        assert len(call_args.kwargs["content"]) == 2

    @pytest.mark.asyncio
    async def test_add_message_pair_conversation_not_found(
        self, conversation_manager, mock_db
    ):
        """Test adding message pair when conversation not found."""
        mock_db.get_conversation_by_id.return_value = None

        with pytest.raises(Exception, match="Conversation with id .* not found"):
            await conversation_manager.add_message_pair(
                cid="non-existent",
                user_message={"role": "user", "content": "Hello"},
                assistant_message={"role": "assistant", "content": "Hi"},
            )


class TestConvertConversation:
    """Tests for _convert_conv_from_v2_to_v1 method."""

    def test_convert_conversation(self, conversation_manager):
        """Test converting ConversationV2 to Conversation."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "test-conv-id"
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = [{"role": "user", "content": "Hello"}]
        mock_conv_v2.title = "Test Title"
        mock_conv_v2.persona_id = "test-persona"
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567900
        mock_conv_v2.token_usage = 100

        result = conversation_manager._convert_conv_from_v2_to_v1(mock_conv_v2)

        assert result.cid == "test-conv-id"
        assert result.platform_id == "test_platform"
        assert result.user_id == "test:group:123"
        assert result.title == "Test Title"
        assert result.persona_id == "test-persona"
        assert result.token_usage == 100


class TestGetFilteredConversations:
    """Tests for get_filtered_conversations method."""

    @pytest.mark.asyncio
    async def test_get_filtered_conversations_basic(
        self, conversation_manager, mock_db
    ):
        """Test getting filtered conversations."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "conv-1"
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = []
        mock_conv_v2.title = "Test"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0

        mock_db.get_filtered_conversations.return_value = ([mock_conv_v2], 1)

        result, count = await conversation_manager.get_filtered_conversations(
            page=1, page_size=20
        )

        assert len(result) == 1
        assert count == 1
        mock_db.get_filtered_conversations.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_filtered_conversations_with_platform_filter(
        self, conversation_manager, mock_db
    ):
        """Test getting filtered conversations with platform filter."""
        mock_db.get_filtered_conversations.return_value = ([], 0)

        result, count = await conversation_manager.get_filtered_conversations(
            page=1, page_size=20, platform_ids=["platform1", "platform2"]
        )

        assert len(result) == 0
        assert count == 0
        mock_db.get_filtered_conversations.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_filtered_conversations_with_search(
        self, conversation_manager, mock_db
    ):
        """Test getting filtered conversations with search query."""
        mock_db.get_filtered_conversations.return_value = ([], 0)

        result, count = await conversation_manager.get_filtered_conversations(
            page=1, page_size=20, search_query="test query"
        )

        assert len(result) == 0
        assert count == 0
        mock_db.get_filtered_conversations.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_filtered_conversations_pagination_filters_and_total(
        self, conversation_manager, mock_db
    ):
        """Ensure get_filtered_conversations forwards filters/pagination and maps items & total correctly."""
        # Arrange
        conv1 = MagicMock(spec=ConversationV2)
        conv1.conversation_id = "conv1"
        conv1.user_id = "test:group:123"
        conv1.title = "First conversation"
        conv1.created_at = MagicMock()
        conv1.created_at.timestamp.return_value = 1
        conv1.updated_at = MagicMock()
        conv1.updated_at.timestamp.return_value = 2
        conv1.platform_id = "platform1"
        conv1.persona_id = None
        conv1.token_usage = 0
        conv1.content = []  # Must be JSON serializable

        conv2 = MagicMock(spec=ConversationV2)
        conv2.conversation_id = "conv2"
        conv2.user_id = "test:group:123"
        conv2.title = "Second conversation"
        conv2.created_at = MagicMock()
        conv2.created_at.timestamp.return_value = 3
        conv2.updated_at = MagicMock()
        conv2.updated_at.timestamp.return_value = 4
        conv2.platform_id = "platform1"
        conv2.persona_id = None
        conv2.token_usage = 0
        conv2.content = []  # Must be JSON serializable

        db_items = [conv1, conv2]
        db_total = 10

        mock_db.get_filtered_conversations.return_value = (db_items, db_total)

        # Act
        items, total = await conversation_manager.get_filtered_conversations(
            page=1,
            page_size=2,
            platform_ids=["platform1"],
            search_query="First",
        )

        # Assert: underlying DB called with correct parameters
        mock_db.get_filtered_conversations.assert_awaited_once()
        call_args = mock_db.get_filtered_conversations.call_args
        assert call_args.kwargs["page"] == 1
        assert call_args.kwargs["page_size"] == 2
        assert call_args.kwargs["platform_ids"] == ["platform1"]
        assert call_args.kwargs["search_query"] == "First"

        # Assert: total is passed through correctly
        assert total == db_total

        # Assert: items length, ordering, and structure are preserved/mapped correctly
        assert isinstance(items, list)
        assert len(items) == 2
        # Returns Conversation objects, not dicts
        assert items[0].cid == "conv1"
        assert items[1].cid == "conv2"
        assert items[0].title == "First conversation"
        assert items[1].title == "Second conversation"
        assert items[0].created_at == 1
        assert items[1].created_at == 3


class TestGetConversations:
    """Tests for get_conversations method with explicit mapping verification."""

    @pytest.mark.asyncio
    async def test_get_conversations_maps_conversation_v2_structure(
        self, conversation_manager, mock_db
    ):
        """Ensure get_conversations maps ConversationV2 to the expected public structure."""
        # Arrange - Create mock ConversationV2 with specific attributes
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "conv1"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.title = "First conversation"
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567999
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.persona_id = "test_persona"
        mock_conv_v2.token_usage = 100
        mock_conv_v2.content = []  # Must be JSON serializable

        mock_db.get_conversations.return_value = [mock_conv_v2]

        # Act
        result = await conversation_manager.get_conversations(
            unified_msg_origin="test:group:123"
        )

        # Assert - Verify ordering and structure of the public response
        assert isinstance(result, list)
        assert len(result) == 1

        conv_public = result[0]
        # Verify public API structure - returns Conversation object with attributes
        assert conv_public.cid == "conv1"
        assert conv_public.user_id == "test:group:123"
        assert conv_public.title == "First conversation"
        assert conv_public.created_at == 1234567890
        assert conv_public.updated_at == 1234567999
        assert conv_public.platform_id == "test_platform"
        assert conv_public.persona_id == "test_persona"
        assert conv_public.token_usage == 100

        mock_db.get_conversations.assert_awaited_once_with(
            user_id="test:group:123", platform_id=None
        )


class TestGetFilteredConversationsDetailed:
    """Detailed tests for get_filtered_conversations with full verification."""

    @pytest.mark.asyncio
    async def test_get_filtered_conversations_pagination_filters_and_total(
        self, conversation_manager, mock_db
    ):
        """Ensure get_filtered_conversations forwards filters/pagination and maps items & total correctly."""
        # Arrange
        conv1 = MagicMock(spec=ConversationV2)
        conv1.conversation_id = "conv1"
        conv1.user_id = "test:group:123"
        conv1.title = "First conversation"
        conv1.created_at = MagicMock()
        conv1.created_at.timestamp.return_value = 1
        conv1.updated_at = MagicMock()
        conv1.updated_at.timestamp.return_value = 2
        conv1.platform_id = "platform1"
        conv1.persona_id = None
        conv1.token_usage = 0
        conv1.content = []  # Must be JSON serializable

        conv2 = MagicMock(spec=ConversationV2)
        conv2.conversation_id = "conv2"
        conv2.user_id = "test:group:123"
        conv2.title = "Second conversation"
        conv2.created_at = MagicMock()
        conv2.created_at.timestamp.return_value = 3
        conv2.updated_at = MagicMock()
        conv2.updated_at.timestamp.return_value = 4
        conv2.platform_id = "platform1"
        conv2.persona_id = None
        conv2.token_usage = 0
        conv2.content = []  # Must be JSON serializable

        db_items = [conv1, conv2]
        db_total = 10

        mock_db.get_filtered_conversations.return_value = (db_items, db_total)

        # Act
        items, total = await conversation_manager.get_filtered_conversations(
            page=1,
            page_size=2,
            platform_ids=["platform1"],
            search_query="First",
        )

        # Assert: underlying DB called with correct parameters
        mock_db.get_filtered_conversations.assert_awaited_once()
        call_args = mock_db.get_filtered_conversations.call_args
        assert call_args.kwargs["page"] == 1
        assert call_args.kwargs["page_size"] == 2
        assert call_args.kwargs["platform_ids"] == ["platform1"]
        assert call_args.kwargs["search_query"] == "First"

        # Assert: total is passed through correctly
        assert total == db_total

        # Assert: items length, ordering, and structure are preserved/mapped correctly
        assert isinstance(items, list)
        assert len(items) == 2
        # Returns Conversation objects, not dicts
        assert items[0].cid == "conv1"
        assert items[1].cid == "conv2"
        assert items[0].title == "First conversation"
        assert items[1].title == "Second conversation"
        assert items[0].created_at == 1
        assert items[1].created_at == 3


class TestGetHumanReadableContext:
    """Tests for get_human_readable_context method."""

    @pytest.mark.asyncio
    async def test_get_human_readable_context_basic(
        self, conversation_manager, mock_db
    ):
        """Test getting human readable context."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "conv-1"
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        mock_conv_v2.title = "Test"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0
        mock_db.get_conversation_by_id.return_value = mock_conv_v2

        result, total_pages = await conversation_manager.get_human_readable_context(
            unified_msg_origin="test:group:123", conversation_id="conv-1"
        )

        assert len(result) == 2
        assert "User: Hello" in result
        assert "Assistant: Hi there!" in result

    @pytest.mark.asyncio
    async def test_get_human_readable_context_not_found(
        self, conversation_manager, mock_db
    ):
        """Test getting context when conversation not found."""
        mock_db.get_conversation_by_id.return_value = None

        result, total_pages = await conversation_manager.get_human_readable_context(
            unified_msg_origin="test:group:123", conversation_id="non-existent"
        )

        assert result == []
        assert total_pages == 0

    @pytest.mark.asyncio
    async def test_get_human_readable_context_with_tool_calls(
        self, conversation_manager, mock_db
    ):
        """Test getting context with tool calls."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "conv-1"
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = [
            {"role": "user", "content": "What time is it?"},
            {
                "role": "assistant",
                "tool_calls": [{"name": "get_time", "args": {}}],
            },
        ]
        mock_conv_v2.title = "Test"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0
        mock_db.get_conversation_by_id.return_value = mock_conv_v2

        result, total_pages = await conversation_manager.get_human_readable_context(
            unified_msg_origin="test:group:123", conversation_id="conv-1"
        )

        assert len(result) == 2
        assert "[函数调用]" in result[1]

    @pytest.mark.asyncio
    async def test_get_human_readable_context_pagination(
        self, conversation_manager, mock_db
    ):
        """Test getting context with pagination."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "conv-1"
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.user_id = "test:group:123"
        # Create 30 message pairs (60 messages total)
        history = []
        for i in range(30):
            history.append({"role": "user", "content": f"Question {i}"})
            history.append({"role": "assistant", "content": f"Answer {i}"})
        mock_conv_v2.content = history
        mock_conv_v2.title = "Test"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0
        mock_db.get_conversation_by_id.return_value = mock_conv_v2

        result, total_pages = await conversation_manager.get_human_readable_context(
            unified_msg_origin="test:group:123",
            conversation_id="conv-1",
            page=1,
            page_size=10,
        )

        # Each pair generates 2 entries
        assert len(result) == 10
        assert total_pages == 6


class TestConcurrentAccess:
    """Tests for concurrent access to conversations."""

    @pytest.mark.asyncio
    async def test_concurrent_access(self, conversation_manager, mock_db):
        """Test multiple concurrent requests accessing the same conversation."""
        mock_conv = MagicMock()
        mock_conv.conversation_id = "shared-conv-id"
        mock_conv.content = []
        mock_db.get_conversation_by_id.return_value = mock_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_get = AsyncMock(return_value="shared-conv-id")

            async def access_conversation():
                """Simulate accessing a conversation."""
                return await conversation_manager.get_curr_conversation_id(
                    unified_msg_origin="test:group:123"
                )

            # Create multiple concurrent tasks
            tasks = [access_conversation() for _ in range(10)]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All requests should succeed and return the same conversation ID
        assert all(
            result == "shared-conv-id"
            for result in results
            if not isinstance(result, Exception)
        )
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, conversation_manager, mock_db):
        """Test multiple concurrent updates to the same conversation."""
        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_get = AsyncMock(return_value="conv-id")

            async def update_conversation(title: str):
                """Simulate updating a conversation."""
                await conversation_manager.update_conversation(
                    unified_msg_origin="test:group:123",
                    conversation_id="conv-id",
                    title=title,
                )
                return title

            # Create multiple concurrent update tasks
            titles = [f"Title {i}" for i in range(5)]
            tasks = [update_conversation(title) for title in titles]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All updates should complete successfully
        assert len(results) == 5
        assert all(isinstance(r, str) for r in results if not isinstance(r, Exception))
        # The database should be called 5 times
        assert mock_db.update_conversation.call_count == 5

    @pytest.mark.asyncio
    async def test_concurrent_switches(self, conversation_manager, mock_db):
        """Test multiple concurrent conversation switches."""
        conv_ids = [f"conv-{i}" for i in range(3)]

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            async def switch_conversation(conv_id: str):
                """Simulate switching to a conversation."""
                await conversation_manager.switch_conversation(
                    unified_msg_origin="test:group:123",
                    conversation_id=conv_id,
                )
                return conv_id

            # Create concurrent switch tasks
            tasks = [switch_conversation(conv_id) for conv_id in conv_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All switches should complete
        assert len(results) == 3
        # The final state should be one of the conversation IDs
        assert conversation_manager.session_conversations["test:group:123"] in conv_ids

    @pytest.mark.asyncio
    async def test_concurrent_create_conversations(self, conversation_manager, mock_db):
        """Test multiple concurrent conversation creations for different sessions."""
        mock_conv = MagicMock()
        mock_conv.conversation_id = "new-conv-id"
        mock_db.create_conversation.return_value = mock_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            async def create_conversation(session_id: str):
                """Simulate creating a new conversation."""
                return await conversation_manager.new_conversation(
                    unified_msg_origin=f"test:group:{session_id}"
                )

            # Create multiple concurrent conversation creation tasks
            session_ids = [str(i) for i in range(10)]
            tasks = [create_conversation(sid) for sid in session_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All creations should complete successfully
        assert len(results) == 10
        assert all(isinstance(r, str) for r in results if not isinstance(r, Exception))
        # Database should be called 10 times
        assert mock_db.create_conversation.call_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_delete_conversations(self, conversation_manager, mock_db):
        """Test multiple concurrent conversation deletions."""
        # Pre-populate sessions
        for i in range(5):
            conversation_manager.session_conversations[f"test:group:{i}"] = f"conv-{i}"

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_remove = AsyncMock()

            async def delete_conversation(session_id: str):
                """Simulate deleting a conversation."""
                await conversation_manager.delete_conversations_by_user_id(
                    unified_msg_origin=f"test:group:{session_id}"
                )
                return session_id

            # Create concurrent deletion tasks
            session_ids = [str(i) for i in range(5)]
            tasks = [delete_conversation(sid) for sid in session_ids]
            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All deletions should complete
        assert len(results) == 5
        # Database should be called 5 times
        assert mock_db.delete_conversations_by_user_id.call_count == 5

    @pytest.mark.asyncio
    async def test_concurrent_read_conversations(self, conversation_manager, mock_db):
        """Test multiple concurrent read operations."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "test-conv-id"
        mock_conv_v2.platform_id = "test_platform"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = []
        mock_conv_v2.title = "Test Title"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0

        mock_db.get_conversation_by_id.return_value = mock_conv_v2

        async def read_conversation(conv_id: str):
            """Simulate reading a conversation."""
            return await conversation_manager.get_conversation(
                unified_msg_origin="test:group:123", conversation_id=conv_id
            )

        # Create concurrent read tasks
        conv_ids = [f"conv-{i}" for i in range(10)]
        tasks = [read_conversation(cid) for cid in conv_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All reads should complete
        assert len(results) == 10
        # Database should be called 10 times
        assert mock_db.get_conversation_by_id.call_count == 10

    @pytest.mark.asyncio
    async def test_mixed_concurrent_operations(self, conversation_manager, mock_db):
        """Test mixed concurrent operations (create, read, update, delete)."""
        # Setup mock for create
        mock_conv = MagicMock()
        mock_conv.conversation_id = "mixed-conv-id"
        mock_conv.content = []
        mock_db.create_conversation.return_value = mock_conv

        # Setup mock for get_conversation
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "mixed-conv-id"
        mock_conv_v2.platform_id = "test"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = []
        mock_conv_v2.title = "Test"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0
        mock_db.get_conversation_by_id.return_value = mock_conv_v2

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()
            mock_sp.session_get = AsyncMock(return_value="mixed-conv-id")

            async def create_op():
                """Create operation."""
                return await conversation_manager.new_conversation(
                    unified_msg_origin="test:group:123"
                )

            async def read_op():
                """Read operation."""
                return await conversation_manager.get_curr_conversation_id(
                    unified_msg_origin="test:group:123"
                )

            async def update_op():
                """Update operation."""
                await conversation_manager.update_conversation(
                    unified_msg_origin="test:group:123",
                    conversation_id="mixed-conv-id",
                    title="Updated Title",
                )
                return "updated"

            async def switch_op():
                """Switch operation."""
                await conversation_manager.switch_conversation(
                    unified_msg_origin="test:group:123",
                    conversation_id="other-conv-id",
                )
                return "switched"

            # Create mixed concurrent tasks
            tasks = []
            tasks.append(asyncio.create_task(create_op()))
            tasks.append(asyncio.create_task(read_op()))
            tasks.append(asyncio.create_task(update_op()))
            tasks.append(asyncio.create_task(switch_op()))
            tasks.append(asyncio.create_task(read_op()))
            tasks.append(asyncio.create_task(update_op()))

            results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should complete without exceptions
        assert len(results) == 6
        # Check no exceptions in results
        exceptions = [r for r in results if isinstance(r, Exception)]
        assert len(exceptions) == 0

    @pytest.mark.asyncio
    async def test_concurrent_get_conversations_list(
        self, conversation_manager, mock_db
    ):
        """Test concurrent access to get_conversations method."""
        mock_conv_v2 = MagicMock(spec=ConversationV2)
        mock_conv_v2.conversation_id = "conv-id"
        mock_conv_v2.platform_id = "test"
        mock_conv_v2.user_id = "test:group:123"
        mock_conv_v2.content = []
        mock_conv_v2.title = "Test"
        mock_conv_v2.persona_id = None
        mock_conv_v2.created_at = MagicMock()
        mock_conv_v2.created_at.timestamp.return_value = 1234567890
        mock_conv_v2.updated_at = MagicMock()
        mock_conv_v2.updated_at.timestamp.return_value = 1234567890
        mock_conv_v2.token_usage = 0

        mock_db.get_conversations.return_value = [mock_conv_v2]

        async def get_conversations_list(user_id: str):
            """Simulate getting conversation list."""
            return await conversation_manager.get_conversations(
                unified_msg_origin=user_id
            )

        # Create concurrent get_conversations tasks
        user_ids = [f"test:group:{i}" for i in range(10)]
        tasks = [get_conversations_list(uid) for uid in user_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should complete
        assert len(results) == 10
        # Database should be called 10 times
        assert mock_db.get_conversations.call_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_add_message_pair(self, conversation_manager, mock_db):
        """Test concurrent add_message_pair operations."""
        mock_conv = MagicMock()
        mock_conv.content = [{"role": "user", "content": "Hello"}]
        mock_db.get_conversation_by_id.return_value = mock_conv

        async def add_message(index: int):
            """Simulate adding a message pair."""
            await conversation_manager.add_message_pair(
                cid="conv-id",
                user_message={"role": "user", "content": f"User {index}"},
                assistant_message={
                    "role": "assistant",
                    "content": f"Assistant {index}",
                },
            )
            return index

        # Create concurrent add_message_pair tasks
        tasks = [add_message(i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should complete
        assert len(results) == 10
        # Database should be called 10 times for get + 10 times for update
        assert mock_db.get_conversation_by_id.call_count == 10
        assert mock_db.update_conversation.call_count == 10
