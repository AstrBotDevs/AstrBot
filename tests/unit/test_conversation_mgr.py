"""Unit tests for astrbot.core.conversation_mgr.ConversationManager."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import Conversation, ConversationV2

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_conv_v2(
    conversation_id="conv-1",
    platform_id="test",
    user_id="test_user",
    title="Test Title",
    persona_id=None,
    content=None,
    token_usage=None,
):
    """Factory for ConversationV2 with sensible defaults."""
    from datetime import datetime, timezone

    return ConversationV2(
        conversation_id=conversation_id,
        platform_id=platform_id,
        user_id=user_id,
        title=title,
        persona_id=persona_id,
        content=content or [],
        token_usage=token_usage,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_db():
    """Create a mock BaseDatabase."""
    db = MagicMock()
    db.create_conversation = AsyncMock()
    db.get_conversation_by_id = AsyncMock()
    db.get_conversations = AsyncMock()
    db.get_filtered_conversations = AsyncMock()
    db.delete_conversation = AsyncMock()
    db.delete_conversations_by_user_id = AsyncMock()
    db.update_conversation = AsyncMock()
    return db


@pytest.fixture
def mgr(mock_db):
    """Create a ConversationManager with mocked database."""
    return ConversationManager(mock_db)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestConversationManagerInit:
    """Tests for ConversationManager.__init__()."""

    def test_init_sets_attributes(self, mock_db):
        """Verify __init__ sets all initial attributes."""
        mgr = ConversationManager(mock_db)
        assert mgr.db is mock_db
        assert mgr.session_conversations == {}
        assert mgr.save_interval == 60
        assert mgr._on_session_deleted_callbacks == []

    def test_register_on_session_deleted(self, mgr):
        """Verify register_on_session_deleted adds callback."""
        async def callback(_umo: str):
            pass

        mgr.register_on_session_deleted(callback)
        assert callback in mgr._on_session_deleted_callbacks


class TestConversationManagerConvertV2ToV1:
    """Tests for _convert_conv_from_v2_to_v1()."""

    def test_converts_v2_to_v1(self, mgr):
        """Verify basic conversion of ConversationV2 to Conversation."""
        conv_v2 = _make_conv_v2(
            conversation_id="c1",
            platform_id="qq",
            user_id="user:123",
            title="Chat",
            persona_id="p1",
            content=[{"role": "user", "content": "hi"}],
            token_usage=100,
        )
        conv = mgr._convert_conv_from_v2_to_v1(conv_v2)
        assert isinstance(conv, Conversation)
        assert conv.cid == "c1"
        assert conv.platform_id == "qq"
        assert conv.user_id == "user:123"
        assert conv.title == "Chat"
        assert conv.persona_id == "p1"
        assert conv.token_usage == 100
        assert json.loads(conv.history) == [{"role": "user", "content": "hi"}]

    def test_converts_empty_content(self, mgr):
        """Verify conversion handles None content."""
        conv_v2 = _make_conv_v2(content=None)
        conv = mgr._convert_conv_from_v2_to_v1(conv_v2)
        assert json.loads(conv.history) == []

    def test_converts_null_timestamps(self, mgr):
        """Verify conversion handles None timestamps."""
        conv_v2 = _make_conv_v2()
        conv_v2.created_at = None
        conv_v2.updated_at = None
        conv = mgr._convert_conv_from_v2_to_v1(conv_v2)
        assert conv.created_at == 0
        assert conv.updated_at == 0


class TestConversationManagerNewConversation:
    """Tests for new_conversation()."""

    @pytest.mark.asyncio
    async def test_new_conversation_creates_and_caches(self, mgr, mock_db):
        """Verify new_conversation creates via DB and caches the ID."""
        created_conv = _make_conv_v2(conversation_id="new-conv")
        mock_db.create_conversation.return_value = created_conv

        with patch("astrbot.core.conversation_mgr.sp.session_put", AsyncMock()) as sp_put:
            cid = await mgr.new_conversation(
                "qq:group:123",
                platform_id="qq",
                content=[{"role": "user", "content": "hi"}],
                title="New Chat",
                persona_id="p1",
            )

        assert cid == "new-conv"
        assert mgr.session_conversations["qq:group:123"] == "new-conv"
        mock_db.create_conversation.assert_awaited_once_with(
            user_id="qq:group:123",
            platform_id="qq",
            content=[{"role": "user", "content": "hi"}],
            title="New Chat",
            persona_id="p1",
        )
        sp_put.assert_awaited_once_with("qq:group:123", "sel_conv_id", "new-conv")

    @pytest.mark.asyncio
    async def test_new_conversation_infers_platform_id(self, mgr, mock_db):
        """Verify platform_id is inferred from unified_msg_origin when not provided."""
        created_conv = _make_conv_v2(conversation_id="cid")
        mock_db.create_conversation.return_value = created_conv

        with patch("astrbot.core.conversation_mgr.sp.session_put", AsyncMock()):
            cid = await mgr.new_conversation("discord:dm:456")

        assert cid == "cid"
        mock_db.create_conversation.assert_awaited_once_with(
            user_id="discord:dm:456",
            platform_id="discord",
            content=None,
            title=None,
            persona_id=None,
        )

    @pytest.mark.asyncio
    async def test_new_conversation_fallback_platform(self, mgr, mock_db):
        """Verify platform_id falls back to 'unknown' when it cannot be inferred."""
        created_conv = _make_conv_v2(conversation_id="cid")
        mock_db.create_conversation.return_value = created_conv

        with patch("astrbot.core.conversation_mgr.sp.session_put", AsyncMock()):
            cid = await mgr.new_conversation("short")

        assert cid == "cid"
        mock_db.create_conversation.assert_awaited_once_with(
            user_id="short",
            platform_id="unknown",
            content=None,
            title=None,
            persona_id=None,
        )


class TestConversationManagerSwitchConversation:
    """Tests for switch_conversation()."""

    @pytest.mark.asyncio
    async def test_switch_conversation(self, mgr):
        """Verify switch updates cache and persists to session prefs."""
        mgr.session_conversations["origin:1"] = "old-id"

        with patch("astrbot.core.conversation_mgr.sp.session_put", AsyncMock()) as sp_put:
            await mgr.switch_conversation("origin:1", "new-id")

        assert mgr.session_conversations["origin:1"] == "new-id"
        sp_put.assert_awaited_once_with("origin:1", "sel_conv_id", "new-id")


class TestConversationManagerDeleteConversation:
    """Tests for delete_conversation()."""

    @pytest.mark.asyncio
    async def test_delete_current_conversation(self, mgr, mock_db):
        """Verify deleting the current conversation clears cache."""
        mgr.session_conversations["origin:1"] = "conv-id"
        mock_db.get_conversation_by_id = AsyncMock(return_value=None)
        mock_db.delete_conversation = AsyncMock()

        with (
            patch(
                "astrbot.core.conversation_mgr.sp.session_remove",
                AsyncMock(),
            ) as sp_remove,
            patch.object(
                mgr,
                "get_curr_conversation_id",
                AsyncMock(return_value="conv-id"),
            ),
        ):
            await mgr.delete_conversation("origin:1")

        mock_db.delete_conversation.assert_awaited_once_with(cid="conv-id")
        assert "origin:1" not in mgr.session_conversations
        sp_remove.assert_awaited_once_with("origin:1", "sel_conv_id")

    @pytest.mark.asyncio
    async def test_delete_specific_conversation(self, mgr, mock_db):
        """Verify deleting a non-current conversation by ID."""
        mgr.session_conversations["origin:1"] = "current-id"
        mock_db.delete_conversation = AsyncMock()

        with (
            patch(
                "astrbot.core.conversation_mgr.sp.session_remove",
                AsyncMock(),
            ) as sp_remove,
            patch.object(
                mgr,
                "get_curr_conversation_id",
                AsyncMock(return_value="current-id"),
            ),
        ):
            await mgr.delete_conversation("origin:1", conversation_id="other-id")

        mock_db.delete_conversation.assert_awaited_once_with(cid="other-id")
        # Current ID should NOT be removed since it differs
        assert mgr.session_conversations.get("origin:1") == "current-id"
        sp_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_no_conversation_id_fallback(self, mgr, mock_db):
        """Verify when no conv ID is given and none cached, do nothing."""
        mgr.session_conversations = {}
        mock_db.delete_conversation = AsyncMock()

        with patch(
            "astrbot.core.conversation_mgr.sp.session_remove",
            AsyncMock(),
        ):
            await mgr.delete_conversation("origin:1")

        mock_db.delete_conversation.assert_not_called()


class TestConversationManagerDeleteConversationsByUserId:
    """Tests for delete_conversations_by_user_id()."""

    @pytest.mark.asyncio
    async def test_delete_all_and_trigger_callbacks(self, mgr, mock_db):
        """Verify deleting all conversations cleans cache and triggers callbacks."""
        mgr.session_conversations["origin:1"] = "c1"
        mock_db.delete_conversations_by_user_id = AsyncMock()

        callback = AsyncMock()
        mgr.register_on_session_deleted(callback)

        with patch(
            "astrbot.core.conversation_mgr.sp.session_remove",
            AsyncMock(),
        ) as sp_remove:
            await mgr.delete_conversations_by_user_id("origin:1")

        mock_db.delete_conversations_by_user_id.assert_awaited_once_with(
            user_id="origin:1",
        )
        assert "origin:1" not in mgr.session_conversations
        sp_remove.assert_awaited_once_with("origin:1", "sel_conv_id")
        callback.assert_awaited_once_with("origin:1")


class TestConversationManagerGetCurrConversationId:
    """Tests for get_curr_conversation_id()."""

    @pytest.mark.asyncio
    async def test_returns_cached_value(self, mgr):
        """Verify returns cached conversation ID without hitting session prefs."""
        mgr.session_conversations["origin:1"] = "cached-id"

        with patch("astrbot.core.conversation_mgr.sp.session_get", AsyncMock()) as sp_get:
            cid = await mgr.get_curr_conversation_id("origin:1")

        assert cid == "cached-id"
        sp_get.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetches_from_session_prefs_and_caches(self, mgr):
        """Verify fetches from session prefs when not cached, then caches it."""
        mgr.session_conversations = {}

        with patch(
            "astrbot.core.conversation_mgr.sp.session_get",
            AsyncMock(return_value="pref-id"),
        ) as sp_get:
            cid = await mgr.get_curr_conversation_id("origin:1")

        assert cid == "pref-id"
        assert mgr.session_conversations["origin:1"] == "pref-id"

    @pytest.mark.asyncio
    async def test_returns_none_when_not_found(self, mgr):
        """Verify returns None when no conversation is known."""
        mgr.session_conversations = {}

        with patch(
            "astrbot.core.conversation_mgr.sp.session_get",
            AsyncMock(return_value=None),
        ):
            cid = await mgr.get_curr_conversation_id("origin:1")

        assert cid is None


class TestConversationManagerGetConversation:
    """Tests for get_conversation()."""

    @pytest.mark.asyncio
    async def test_get_existing_conversation(self, mgr, mock_db):
        """Verify retrieves and converts existing conversation."""
        conv_v2 = _make_conv_v2(conversation_id="c1")
        mock_db.get_conversation_by_id.return_value = conv_v2

        conv = await mgr.get_conversation("origin:1", "c1")

        assert conv is not None
        assert conv.cid == "c1"
        mock_db.get_conversation_by_id.assert_awaited_once_with(cid="c1")

    @pytest.mark.asyncio
    async def test_get_non_existing_not_created(self, mgr, mock_db):
        """Verify returns None when not found and create_if_not_exists is False."""
        mock_db.get_conversation_by_id.return_value = None

        conv = await mgr.get_conversation("origin:1", "nonexistent")

        assert conv is None

    @pytest.mark.asyncio
    async def test_get_non_existing_creates_new(self, mgr, mock_db):
        """Verify creates new conversation when not found and create_if_not_exists is True."""
        mock_db.get_conversation_by_id.side_effect = [
            None,
            _make_conv_v2(conversation_id="new-c1"),
        ]

        with patch.object(
            mgr,
            "new_conversation",
            AsyncMock(return_value="new-c1"),
        ) as mock_new:
            conv = await mgr.get_conversation(
                "origin:1",
                "nonexistent",
                create_if_not_exists=True,
            )

        assert conv is not None
        assert conv.cid == "new-c1"
        mock_new.assert_awaited_once_with("origin:1")


class TestConversationManagerGetConversations:
    """Tests for get_conversations()."""

    @pytest.mark.asyncio
    async def test_get_conversations(self, mgr, mock_db):
        """Verify retrieving multiple conversations."""
        convs_v2 = [
            _make_conv_v2(conversation_id="c1"),
            _make_conv_v2(conversation_id="c2"),
        ]
        mock_db.get_conversations.return_value = convs_v2

        convs = await mgr.get_conversations(unified_msg_origin="origin:1")

        assert len(convs) == 2
        assert convs[0].cid == "c1"
        assert convs[1].cid == "c2"
        mock_db.get_conversations.assert_awaited_once_with(
            user_id="origin:1",
            platform_id=None,
        )


class TestConversationManagerGetFilteredConversations:
    """Tests for get_filtered_conversations()."""

    @pytest.mark.asyncio
    async def test_get_filtered_conversations(self, mgr, mock_db):
        """Verify filtered conversation retrieval."""
        convs_v2 = [_make_conv_v2(conversation_id="c1")]
        mock_db.get_filtered_conversations.return_value = (convs_v2, 1)

        convs, cnt = await mgr.get_filtered_conversations(
            page=1,
            page_size=20,
            platform_ids=["qq"],
            search_query="test",
        )

        assert len(convs) == 1
        assert convs[0].cid == "c1"
        assert cnt == 1
        mock_db.get_filtered_conversations.assert_awaited_once_with(
            page=1,
            page_size=20,
            platform_ids=["qq"],
            search_query="test",
        )


class TestConversationManagerUpdateConversation:
    """Tests for update_conversation()."""

    @pytest.mark.asyncio
    async def test_update_without_id_uses_current(self, mgr, mock_db):
        """Verify update uses current conversation ID when not provided."""
        with patch.object(
            mgr,
            "get_curr_conversation_id",
            AsyncMock(return_value="current-id"),
        ):
            await mgr.update_conversation(
                "origin:1",
                history=[{"role": "user", "content": "hi"}],
                title="Updated",
                persona_id="p2",
                token_usage=50,
            )

        mock_db.update_conversation.assert_awaited_once_with(
            cid="current-id",
            title="Updated",
            persona_id="p2",
            clear_persona=False,
            content=[{"role": "user", "content": "hi"}],
            token_usage=50,
        )

    @pytest.mark.asyncio
    async def test_update_with_id(self, mgr, mock_db):
        """Verify update with explicit conversation ID."""
        await mgr.update_conversation(
            "origin:1",
            conversation_id="explicit-id",
            title="New Title",
        )

        mock_db.update_conversation.assert_awaited_once_with(
            cid="explicit-id",
            title="New Title",
            persona_id=None,
            clear_persona=False,
            content=None,
            token_usage=None,
        )

    @pytest.mark.asyncio
    async def test_update_without_id_no_current_does_nothing(self, mgr, mock_db):
        """Verify update does nothing when no ID is available."""
        with patch.object(
            mgr,
            "get_curr_conversation_id",
            AsyncMock(return_value=None),
        ):
            await mgr.update_conversation("origin:1", title="New Title")

        mock_db.update_conversation.assert_not_called()


class TestConversationManagerUpdateConversationTitle:
    """Tests for update_conversation_title()."""

    @pytest.mark.asyncio
    async def test_update_title_delegates(self, mgr):
        """Verify update_conversation_title delegates to update_conversation."""
        with patch.object(mgr, "update_conversation", AsyncMock()) as mock_update:
            await mgr.update_conversation_title("origin:1", "New Title", "conv-id")

        mock_update.assert_awaited_once_with(
            unified_msg_origin="origin:1",
            conversation_id="conv-id",
            title="New Title",
        )


class TestConversationManagerUpdateConversationPersonaId:
    """Tests for update_conversation_persona_id()."""

    @pytest.mark.asyncio
    async def test_update_persona_delegates(self, mgr):
        """Verify update_conversation_persona_id delegates to update_conversation."""
        with patch.object(mgr, "update_conversation", AsyncMock()) as mock_update:
            await mgr.update_conversation_persona_id(
                "origin:1",
                "persona-123",
                "conv-id",
            )

        mock_update.assert_awaited_once_with(
            unified_msg_origin="origin:1",
            conversation_id="conv-id",
            persona_id="persona-123",
        )


class TestConversationManagerUnsetConversationPersona:
    """Tests for unset_conversation_persona()."""

    @pytest.mark.asyncio
    async def test_unset_persona_delegates_with_clear(self, mgr):
        """Verify unset_conversation_persona delegates with clear_persona=True."""
        with patch.object(mgr, "update_conversation", AsyncMock()) as mock_update:
            await mgr.unset_conversation_persona("origin:1", "conv-id")

        mock_update.assert_awaited_once_with(
            unified_msg_origin="origin:1",
            conversation_id="conv-id",
            clear_persona=True,
        )


class TestConversationManagerAddMessagePair:
    """Tests for add_message_pair()."""

    @pytest.mark.asyncio
    async def test_add_message_pair_dicts(self, mgr, mock_db):
        """Verify adding message pair using plain dicts."""
        conv_v2 = _make_conv_v2(content=[])
        mock_db.get_conversation_by_id.return_value = conv_v2

        await mgr.add_message_pair(
            "c1",
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        )

        mock_db.update_conversation.assert_awaited_once_with(
            cid="c1",
            content=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
            ],
        )

    @pytest.mark.asyncio
    async def test_add_message_pair_appends_to_existing(self, mgr, mock_db):
        """Verify adding message pair appends to existing history."""
        conv_v2 = _make_conv_v2(content=[{"role": "user", "content": "prev"}])
        mock_db.get_conversation_by_id.return_value = conv_v2

        await mgr.add_message_pair(
            "c1",
            {"role": "user", "content": "q2"},
            {"role": "assistant", "content": "a2"},
        )

        mock_db.update_conversation.assert_awaited_once_with(
            cid="c1",
            content=[
                {"role": "user", "content": "prev"},
                {"role": "user", "content": "q2"},
                {"role": "assistant", "content": "a2"},
            ],
        )

    @pytest.mark.asyncio
    async def test_add_message_pair_conv_not_found(self, mgr, mock_db):
        """Verify raises when conversation is not found."""
        mock_db.get_conversation_by_id.return_value = None

        with pytest.raises(Exception, match="Conversation with id nonexistent not found"):
            await mgr.add_message_pair(
                "nonexistent",
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            )

    @pytest.mark.asyncio
    async def test_add_message_pair_segment_objects(self, mgr, mock_db):
        """Verify adding message pair using UserMessageSegment / AssistantMessageSegment."""
        from astrbot.core.agent.message import (
            AssistantMessageSegment,
            UserMessageSegment,
        )

        conv_v2 = _make_conv_v2(content=[])
        mock_db.get_conversation_by_id.return_value = conv_v2

        user_msg = UserMessageSegment(content="hello")
        assistant_msg = AssistantMessageSegment(content="world")

        with (
            patch.object(user_msg, "model_dump", return_value={"role": "user", "content": "hello"}),
            patch.object(
                assistant_msg,
                "model_dump",
                return_value={"role": "assistant", "content": "world"},
            ),
        ):
            await mgr.add_message_pair("c1", user_msg, assistant_msg)

        mock_db.update_conversation.assert_awaited_once_with(
            cid="c1",
            content=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            ],
        )


class TestConversationManagerGetHumanReadableContext:
    """Tests for get_human_readable_context()."""

    @pytest.mark.asyncio
    async def test_get_context(self, mgr):
        """Verify basic context formatting."""
        mgr._convert_conv_from_v2_to_v1 = MagicMock(
            return_value=Conversation(
                platform_id="qq",
                user_id="user:1",
                cid="c1",
                history=json.dumps([
                    {"role": "user", "content": "hello"},
                    {"role": "assistant", "content": "world"},
                    {"role": "user", "content": "how are you"},
                    {"role": "assistant", "content": "fine"},
                ]),
                title="Chat",
                created_at=1000,
                updated_at=1001,
            ),
        )

        contexts, total_pages = await mgr.get_human_readable_context(
            "origin:1",
            "c1",
            page=1,
            page_size=10,
        )

        # Order: most recent pair first
        assert contexts == [
            "User: how are you",
            "Assistant: fine",
            "User: hello",
            "Assistant: world",
        ]
        assert total_pages == 1

    @pytest.mark.asyncio
    async def test_get_context_no_conversation(self, mgr):
        """Verify returns empty when conversation not found."""
        with patch.object(
            mgr,
            "get_conversation",
            AsyncMock(return_value=None),
        ):
            contexts, total_pages = await mgr.get_human_readable_context(
                "origin:1",
                "nonexistent",
            )

        assert contexts == []
        assert total_pages == 0

    @pytest.mark.asyncio
    async def test_get_context_pagination(self, mgr):
        """Verify context pagination."""
        records = []
        for i in range(5):
            records.append({"role": "user", "content": f"q{i}"})
            records.append({"role": "assistant", "content": f"a{i}"})

        mgr._convert_conv_from_v2_to_v1 = MagicMock(
            return_value=Conversation(
                platform_id="qq",
                user_id="user:1",
                cid="c1",
                history=json.dumps(records),
                title="Chat",
                created_at=1000,
                updated_at=1001,
            ),
        )

        contexts, total_pages = await mgr.get_human_readable_context(
            "origin:1",
            "c1",
            page=1,
            page_size=2,
        )

        # 5 pairs = 10 records, reversed, page_size=2
        assert len(contexts) == 2
        assert total_pages == 5

    @pytest.mark.asyncio
    async def test_get_context_with_tool_calls(self, mgr):
        """Verify context handles tool_calls in assistant messages."""
        mgr._convert_conv_from_v2_to_v1 = MagicMock(
            return_value=Conversation(
                platform_id="qq",
                user_id="user:1",
                cid="c1",
                history=json.dumps([
                    {"role": "user", "content": "search weather"},
                    {
                        "role": "assistant",
                        "tool_calls": [{"function": {"name": "get_weather"}}],
                    },
                ]),
                title="Chat",
                created_at=1000,
                updated_at=1001,
            ),
        )

        contexts, _ = await mgr.get_human_readable_context("origin:1", "c1")

        assert "Assistant: [函数调用]" in contexts[0]


class TestConversationManagerTriggerSessionDeleted:
    """Tests for _trigger_session_deleted()."""

    @pytest.mark.asyncio
    async def test_triggers_callbacks(self, mgr):
        """Verify all callbacks are triggered."""
        cb1 = AsyncMock()
        cb2 = AsyncMock()
        mgr.register_on_session_deleted(cb1)
        mgr.register_on_session_deleted(cb2)

        await mgr._trigger_session_deleted("origin:1")

        cb1.assert_awaited_once_with("origin:1")
        cb2.assert_awaited_once_with("origin:1")

    @pytest.mark.asyncio
    async def test_callback_error_does_not_block_others(self, mgr):
        """Verify one failing callback does not prevent others from running."""
        cb1 = AsyncMock(side_effect=RuntimeError("fail"))
        cb2 = AsyncMock()
        mgr.register_on_session_deleted(cb1)
        mgr.register_on_session_deleted(cb2)

        # Should not raise
        await mgr._trigger_session_deleted("origin:1")

        cb2.assert_awaited_once_with("origin:1")
