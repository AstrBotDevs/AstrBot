"""Tests for ConversationManager."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

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
        assert conversation_manager.session_conversations["test_platform:group:123456"] == "test-conv-id"
        mock_db.create_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_new_conversation_with_platform_id(self, conversation_manager, mock_db):
        """Test creating a new conversation with explicit platform_id."""
        mock_conv = MagicMock()
        mock_conv.conversation_id = "test-conv-id"
        mock_db.create_conversation.return_value = mock_conv

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            conv_id = await conversation_manager.new_conversation(
                unified_msg_origin="test:group:123",
                platform_id="custom_platform"
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
                persona_id="test-persona"
            )

        assert conv_id == "test-conv-id"
        mock_db.create_conversation.assert_called_once_with(
            user_id="test:group:123",
            platform_id="test",
            content=content,
            title="Test Title",
            persona_id="test-persona",
        )


class TestSwitchConversation:
    """Tests for switch_conversation method."""

    @pytest.mark.asyncio
    async def test_switch_conversation(self, conversation_manager):
        """Test switching conversation."""
        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_put = AsyncMock()

            await conversation_manager.switch_conversation(
                unified_msg_origin="test:group:123",
                conversation_id="new-conv-id"
            )

        assert conversation_manager.session_conversations["test:group:123"] == "new-conv-id"
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
                unified_msg_origin="test:group:123",
                conversation_id="conv-to-delete"
            )

        mock_db.delete_conversation.assert_called_once_with(cid="conv-to-delete")

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
    async def test_delete_conversations_triggers_callback(self, conversation_manager, mock_db):
        """Test that deleting conversations triggers registered callbacks."""
        callback = AsyncMock()
        conversation_manager.register_on_session_deleted(callback)

        with patch("astrbot.core.conversation_mgr.sp") as mock_sp:
            mock_sp.session_remove = AsyncMock()

            await conversation_manager.delete_conversations_by_user_id(
                unified_msg_origin="test:group:123"
            )

        callback.assert_called_once_with("test:group:123")


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
        assert conversation_manager.session_conversations["test:group:123"] == "stored-conv-id"

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
            unified_msg_origin="test:group:123",
            conversation_id="test-conv-id"
        )

        assert result is not None
        mock_db.get_conversation_by_id.assert_called_once_with(cid="test-conv-id")

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(self, conversation_manager, mock_db):
        """Test getting conversation when not found."""
        mock_db.get_conversation_by_id.return_value = None

        result = await conversation_manager.get_conversation(
            unified_msg_origin="test:group:123",
            conversation_id="non-existent"
        )

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
            persona_id="new-persona"
        )

        mock_db.update_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_conversation_without_id(self, conversation_manager, mock_db):
        """Test updating conversation using current ID."""
        conversation_manager.get_curr_conversation_id = AsyncMock(
            return_value="current-conv-id"
        )

        await conversation_manager.update_conversation(
            unified_msg_origin="test:group:123",
            history=[{"role": "user", "content": "Hello"}]
        )

        mock_db.update_conversation.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_conversation_no_current_id(self, conversation_manager, mock_db):
        """Test updating conversation when no current ID exists."""
        conversation_manager.get_curr_conversation_id = AsyncMock(return_value=None)

        await conversation_manager.update_conversation(
            unified_msg_origin="test:group:123",
            title="New Title"
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
            cid="conv-id",
            user_message=user_msg,
            assistant_message=assistant_msg
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
                assistant_message={"role": "assistant", "content": "Hi"}
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
