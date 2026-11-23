"""Conversation selection and deletion against real temporary persistence."""

import json

import pytest

from astrbot.core import conversation_mgr


@pytest.fixture
def manager(monkeypatch, database, shared_preferences):
    monkeypatch.setattr(conversation_mgr, "sp", shared_preferences)
    return conversation_mgr.ConversationManager(database)


@pytest.mark.asyncio
async def test_new_conversation_preserves_history_and_selection_after_restart(
    manager, database
):
    umo = "test:FriendMessage:alice"
    history = [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "answer"},
    ]
    cid = await manager.new_conversation(umo, content=history, title="Saved topic")
    restarted = conversation_mgr.ConversationManager(database)

    assert await restarted.get_curr_conversation_id(umo) == cid
    conversation = await restarted.get_conversation(umo, cid)
    assert conversation is not None
    assert conversation.title == "Saved topic"
    assert conversation.platform_id == "test"
    assert json.loads(conversation.history) == history
    assert await restarted.get_curr_conversation_id("test:FriendMessage:bob") is None


@pytest.mark.asyncio
async def test_switch_and_delete_noncurrent_conversation_keep_current_selection(
    manager, database
):
    umo = "test:FriendMessage:alice"
    first = await manager.new_conversation(umo, title="first")
    second = await manager.new_conversation(umo, title="second")
    await manager.switch_conversation(umo, first)
    restarted = conversation_mgr.ConversationManager(database)
    assert await restarted.get_curr_conversation_id(umo) == first

    await restarted.delete_conversation(umo, second)
    assert await restarted.get_conversation(umo, second) is None
    assert await restarted.get_curr_conversation_id(umo) == first
    await restarted.delete_conversation(umo)
    assert await restarted.get_conversation(umo, first) is None
    assert await restarted.get_curr_conversation_id(umo) is None


@pytest.mark.asyncio
async def test_delete_all_clears_selection_and_runs_remaining_callbacks_on_failure(
    manager, database
):
    umo = "test:GroupMessage:room"
    first = await manager.new_conversation(umo)
    second = await manager.new_conversation(umo)
    observed: list[tuple[str, str]] = []

    async def failing_callback(session: str) -> None:
        observed.append(("first", session))
        raise ValueError("callback failed")

    async def remaining_callback(session: str) -> None:
        observed.append(("second", session))

    manager.register_on_session_deleted(failing_callback)
    manager.register_on_session_deleted(remaining_callback)
    await manager.delete_conversations_by_user_id(umo)

    assert observed == [("first", umo), ("second", umo)]
    assert await manager.get_conversations(umo) == []
    restarted = conversation_mgr.ConversationManager(database)
    assert await restarted.get_curr_conversation_id(umo) is None
    assert await restarted.get_conversation(umo, first) is None
    assert await restarted.get_conversation(umo, second) is None


@pytest.mark.asyncio
async def test_event_writer_rejects_a_different_session_owner(manager):
    owner = "test:FriendMessage:alice"
    cid = await manager.new_conversation(owner)
    with pytest.raises(ValueError, match="not accessible"):
        await manager.create_event_writer(
            cid, unified_msg_origin="test:FriendMessage:bob"
        )
    assert await manager.get_conversation(owner, cid) is not None
