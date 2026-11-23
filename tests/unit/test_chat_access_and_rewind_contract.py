"""Keep ownership, revision, and cancellation behavior stable across refactoring."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.db.conversation import ContextUnavailableError
from astrbot.core.db.po import PlatformMessageHistory, PlatformSession
from astrbot.dashboard.services.chat_service import ChatService, ChatServiceError

SESSION_ACTIONS = [
    ("stop_session", {"session_id": "session-1"}),
    ("delete_webchat_session", {"session_id": "session-1"}),
    ("get_session", {"session_id": "session-1"}),
    (
        "create_thread",
        {
            "data": {
                "session_id": "session-1",
                "parent_message_id": 10,
                "selected_text": "Selected answer",
            }
        },
    ),
    (
        "update_message",
        {
            "data": {
                "session_id": "session-1",
                "message_id": 10,
                "content": {
                    "type": "user",
                    "message": [{"type": "plain", "text": "Edited question"}],
                },
            }
        },
    ),
    (
        "prepare_regenerate_message_payload",
        {"data": {"session_id": "session-1", "message_id": 10}},
    ),
    (
        "update_session_display_name",
        {"session_id": "session-1", "display_name": "Renamed session"},
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("method,arguments", SESSION_ACTIONS)
@pytest.mark.parametrize("owner", [None, "bob"])
async def test_session_actions_check_access_before_downstream_work(
    method, arguments, owner
):
    service = object.__new__(ChatService)
    lookup = AsyncMock(return_value=SimpleNamespace(creator=owner) if owner else None)
    service.db = SimpleNamespace(get_platform_session_by_id=lookup)

    with pytest.raises(ChatServiceError) as error:
        await getattr(service, method)("alice", **deepcopy(arguments))

    assert str(error.value) == (
        "Permission denied" if owner else "Session session-1 not found"
    )
    lookup.assert_awaited_once_with("session-1")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method,arguments",
    [
        ("get_thread", {"thread_id": "thread-1"}),
        ("delete_thread", {"thread_id": "thread-1"}),
        ("prepare_thread_chat_payload", {"data": {"thread_id": "thread-1"}}),
    ],
)
@pytest.mark.parametrize("owner", [None, "bob"])
async def test_thread_actions_check_access_before_downstream_work(
    method, arguments, owner
):
    service = object.__new__(ChatService)
    lookup = AsyncMock(return_value=SimpleNamespace(creator=owner) if owner else None)
    service.db = SimpleNamespace(get_webchat_thread_by_id=lookup)

    with pytest.raises(ChatServiceError) as error:
        await getattr(service, method)("alice", **deepcopy(arguments))

    assert str(error.value) == (
        "Permission denied" if owner else "Thread thread-1 not found"
    )
    lookup.assert_awaited_once_with("thread-1")


@pytest.fixture(params=["update_message", "prepare_regenerate_message_payload"])
def history_action(request):
    """Prepare real record models with isolated persistence operations."""
    service = object.__new__(ChatService)
    editing = request.param == "update_message"
    session = PlatformSession(
        session_id="session-1", creator="alice", platform_id="webchat", is_group=0
    )
    record = PlatformMessageHistory(
        id=10,
        platform_id="webchat",
        user_id="session-1",
        content={"type": "user" if editing else "bot", "message": []},
    )
    replacement = PlatformMessageHistory(
        id=77,
        platform_id="webchat",
        user_id="session-1",
        turn_id="replacement-turn",
        content={
            "type": "user",
            "message": [{"type": "plain", "text": "Replacement question"}],
        },
    )
    store = SimpleNamespace(
        read=AsyncMock(
            return_value=SimpleNamespace(
                revision=SimpleNamespace(head_seq=19, leaf_event_id="current-leaf")
            )
        ),
        rewind_webchat=AsyncMock(return_value=replacement),
    )
    service.db = SimpleNamespace(
        get_platform_session_by_id=AsyncMock(return_value=session),
        get_platform_message_history_by_id=AsyncMock(return_value=record),
        conversation_store=store,
        update_platform_session=AsyncMock(),
    )
    service.conv_mgr = SimpleNamespace(
        get_curr_conversation_id=AsyncMock(return_value="conversation-1")
    )
    service.running_convs = {}
    payload = {
        "session_id": "session-1",
        "message_id": "10",
        "content": {
            "type": "user",
            "message": [{"type": "plain", "text": "Edited question"}],
        },
        "locale": "zh-CN",
        "selected_provider": "provider-1",
        "selected_model": "model-1",
        "flags": {"enable_reasoning": False},
    }
    return service, getattr(service, request.param), payload, editing


@pytest.mark.asyncio
async def test_history_rewrite_preserves_revision_and_public_result(history_action):
    service, action, payload, editing = history_action
    original_payload = deepcopy(payload)

    result = await action("alice", payload)

    service.conv_mgr.get_curr_conversation_id.assert_awaited_once_with(
        "webchat:FriendMessage:webchat!alice!session-1"
    )
    store = service.db.conversation_store
    store.read.assert_awaited_once_with("conversation-1")
    expected = {"expected_head": 19, "expected_leaf": "current-leaf"}
    if editing:
        expected["content"] = original_payload["content"]
        assert result["message"]["id"] == 77
        assert result["needs_regenerate"] is True
        assert result["truncated_after_message"] is True
        service.db.update_platform_session.assert_awaited_once_with(
            session_id="session-1"
        )
    else:
        assert result["session_id"] == "session-1"
        assert result["message"] == store.rewind_webchat.return_value.content["message"]
        assert result["_skip_user_history"] is True
        assert result["_turn_id"] == "replacement-turn"
        assert result["flags"]["enable_reasoning"] is False
        for key in ("locale", "selected_provider", "selected_model"):
            assert result[key] == original_payload[key]
        service.db.update_platform_session.assert_not_awaited()
    store.rewind_webchat.assert_awaited_once_with("conversation-1", 10, **expected)
    assert payload == original_payload


@pytest.mark.asyncio
@pytest.mark.parametrize("conversation_id", [None, "", "missing-snapshot"])
async def test_missing_conversation_cannot_rewrite_history(
    history_action, conversation_id
):
    service, action, payload, _editing = history_action
    service.conv_mgr.get_curr_conversation_id.return_value = conversation_id
    store = service.db.conversation_store
    store.read.return_value = None

    with pytest.raises(ChatServiceError) as error:
        await action("alice", payload)

    assert str(error.value) == "Conversation not found"
    if conversation_id:
        store.read.assert_awaited_once_with(conversation_id)
    else:
        store.read.assert_not_awaited()
    store.rewind_webchat.assert_not_awaited()
    service.db.update_platform_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_run_is_checked_before_loading_rewrite_context(history_action):
    service, action, payload, editing = history_action
    service.running_convs["session-1"] = True

    with pytest.raises(ChatServiceError) as error:
        await action("alice", payload)

    operation = "editing" if editing else "regenerating"
    assert str(error.value) == f"Stop the active run before {operation}"
    service.conv_mgr.get_curr_conversation_id.assert_not_awaited()
    service.db.conversation_store.read.assert_not_awaited()
    service.db.conversation_store.rewind_webchat.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "exception,expected_message",
    [
        (
            ContextUnavailableError("pruned context"),
            "Historical context has been cleared; this action is unavailable.",
        ),
        (ValueError("revision changed"), "revision changed"),
    ],
)
async def test_history_rewrite_keeps_error_translation(
    history_action, exception, expected_message
):
    service, action, payload, _editing = history_action
    service.db.conversation_store.rewind_webchat.side_effect = exception

    with pytest.raises(ChatServiceError) as error:
        await action("alice", payload)

    assert str(error.value) == expected_message
    assert error.value.__cause__ is exception
    service.db.update_platform_session.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["read", "rewind_webchat"])
async def test_history_rewrite_propagates_cancellation(history_action, phase):
    service, action, payload, _editing = history_action
    store = service.db.conversation_store
    getattr(store, phase).side_effect = asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await action("alice", payload)

    if phase == "read":
        store.rewind_webchat.assert_not_awaited()
    service.db.update_platform_session.assert_not_awaited()
