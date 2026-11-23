"""Unit tests for astrbot.core.conversation_mgr.ConversationManager."""

from __future__ import annotations

import json
from datetime import UTC
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core import conversation_mgr as conversation_module
from astrbot.core import session_overrides
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
    from datetime import datetime

    return ConversationV2(
        conversation_id=conversation_id,
        platform_id=platform_id,
        user_id=user_id,
        title=title,
        persona_id=persona_id,
        content=content or [],
        token_usage=token_usage,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
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
def manager_preferences(shared_preferences, monkeypatch):
    """Keep preference writes local even when testing a database boundary."""
    monkeypatch.setattr(conversation_module, "sp", shared_preferences)
    monkeypatch.setattr(session_overrides, "sp", shared_preferences)
    return shared_preferences


@pytest.fixture
def mgr(mock_db, manager_preferences):
    """Create a manager with explicit database and preference boundaries."""
    return ConversationManager(mock_db)


@pytest.fixture
def persisted_manager(database, manager_preferences):
    """Use the real event store for message and projection behavior."""
    return ConversationManager(database)


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
    """Tests for to_legacy_conversation()."""

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
        conv = mgr.to_legacy_conversation(conv_v2)
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
        conv = mgr.to_legacy_conversation(conv_v2)
        assert json.loads(conv.history) == []

    def test_converts_null_timestamps(self, mgr):
        """Verify conversion handles None timestamps."""
        conv_v2 = _make_conv_v2()
        conv_v2.created_at = None
        conv_v2.updated_at = None
        conv = mgr.to_legacy_conversation(conv_v2)
        assert conv.created_at == 0
        assert conv.updated_at == 0


class TestConversationManagerNewConversation:
    """Tests for new_conversation()."""

    @pytest.mark.asyncio
    async def test_new_conversation_creates_and_caches(self, mgr, mock_db):
        """Verify new_conversation creates via DB and caches the ID."""
        created_conv = _make_conv_v2(conversation_id="new-conv")
        mock_db.create_conversation.return_value = created_conv

        with patch(
            "astrbot.core.conversation_mgr.sp.session_put", AsyncMock()
        ) as sp_put:
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

        with patch(
            "astrbot.core.conversation_mgr.sp.session_put", AsyncMock()
        ) as sp_put:
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

        with patch(
            "astrbot.core.conversation_mgr.sp.session_get", AsyncMock()
        ) as sp_get:
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
        sp_get.assert_awaited_once_with("origin:1", "sel_conv_id", None)

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
            include_history=True,
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
    """Append complete pairs through ConversationV3 and reject stale snapshots."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("with_existing", [False, True])
    @pytest.mark.parametrize("segments", [False, True])
    async def test_add_message_pair_preserves_existing_history(
        self, persisted_manager, database, with_existing, segments
    ):
        from astrbot.core.agent.message import (
            AssistantMessageSegment,
            UserMessageSegment,
        )

        initial = [{"role": "user", "content": "previous"}] if with_existing else []
        conv = await database.create_conversation("owner", "test", content=initial)
        user = {"role": "user", "content": "hello"}
        assistant = {"role": "assistant", "content": "world"}
        await persisted_manager.add_message_pair(
            conv.conversation_id,
            UserMessageSegment(content="hello") if segments else user,
            AssistantMessageSegment(content="world") if segments else assistant,
        )

        snapshot = await database.conversation_store.read(conv.conversation_id)
        assert [
            {"role": message["role"], "content": message["content"]}
            for message in snapshot.messages
        ] == [*initial, user, assistant]
        appended = [
            event
            for event in await database.conversation_store.events(conv.conversation_id)
            if event.type == "message.appended"
        ]
        assert [event.payload["message"]["content"] for event in appended[-2:]] == [
            "hello",
            "world",
        ]

    @pytest.mark.asyncio
    async def test_add_message_pair_missing_conversation_raises(
        self, persisted_manager
    ):
        with pytest.raises(ValueError, match="Conversation with id missing not found"):
            await persisted_manager.add_message_pair(
                "missing",
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
            )

    @pytest.mark.asyncio
    async def test_concurrent_background_append_cannot_be_overwritten_by_a_stale_pair(
        self, persisted_manager, database, monkeypatch
    ):
        from astrbot.core.db.conversation import ConversationConflictError

        store = database.conversation_store
        conv = await store.create(umo="owner", platform_id="test")
        append = store.append
        background = {"role": "user", "content": "background result"}
        pair = [
            {"role": "user", "content": "foreground input"},
            {"role": "assistant", "content": "foreground reply"},
        ]

        async def append_background_before_pair(cid, drafts, **kwargs):
            await append(
                cid,
                [{"type": "message.appended", "payload": {"message": background}}],
                expected_leaf=kwargs["expected_leaf"],
            )
            return await append(cid, drafts, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(store, "append", append_background_before_pair)
            with pytest.raises(ConversationConflictError):
                await persisted_manager.add_message_pair(conv.conversation_id, *pair)

        assert (await store.read(conv.conversation_id)).messages == [background]
        await persisted_manager.add_message_pair(conv.conversation_id, *pair)
        assert (await store.read(conv.conversation_id)).messages == [background, *pair]


class TestConversationManagerGetHumanReadableContext:
    """Render persisted histories and paginate the newest complete pairs first."""

    @pytest.mark.asyncio
    async def test_get_context(self, persisted_manager, database):
        conv = await database.create_conversation(
            "owner",
            "test",
            content=[
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "world"},
                {"role": "user", "content": "how are you"},
                {"role": "assistant", "content": "fine"},
            ],
        )
        contexts, pages = await persisted_manager.get_human_readable_context(
            "owner", conv.conversation_id
        )
        assert contexts == [
            "User: how are you",
            "Assistant: fine",
            "User: hello",
            "Assistant: world",
        ]
        assert pages == 1

    @pytest.mark.asyncio
    async def test_get_context_no_conversation(self, persisted_manager):
        assert await persisted_manager.get_human_readable_context(
            "owner", "missing"
        ) == ([], 0)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("page", [1, 3, 5, 6])
    async def test_get_context_pagination(self, persisted_manager, database, page):
        records = []
        for index in range(5):
            records.extend(
                [
                    {"role": "user", "content": f"q{index}"},
                    {"role": "assistant", "content": f"a{index}"},
                ]
            )
        conv = await database.create_conversation("owner", "test", content=records)
        contexts, pages = await persisted_manager.get_human_readable_context(
            "owner", conv.conversation_id, page=page, page_size=2
        )
        assert pages == 5
        assert contexts == (
            [f"User: q{5 - page}", f"Assistant: a{5 - page}"] if page <= 5 else []
        )

    @pytest.mark.asyncio
    async def test_get_context_with_tool_calls(self, persisted_manager, database):
        tool = {
            "id": "call-1",
            "type": "function",
            "function": {"name": "get_weather", "arguments": "{}"},
        }
        conv = await database.create_conversation(
            "owner",
            "test",
            content=[
                {"role": "user", "content": "search weather"},
                {"role": "assistant", "tool_calls": [tool]},
            ],
        )
        contexts, pages = await persisted_manager.get_human_readable_context(
            "owner", conv.conversation_id
        )
        assert contexts == [
            "User: search weather",
            f"Assistant: [函数调用] {json.dumps([tool], ensure_ascii=False)}",
        ]
        assert pages == 1


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
