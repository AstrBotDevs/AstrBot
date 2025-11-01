"""Tests for ConversationManager.add_message_pair method."""

import json

import pytest
import pytest_asyncio

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def conversation_manager(tmp_path):
    """Provides a ConversationManager instance with a temporary database."""
    temp_db_path = tmp_path / "test_conv.db"
    db = SQLiteDatabase(str(temp_db_path))
    await db.initialize()
    conv_mgr = ConversationManager(db)
    yield conv_mgr
    # Database will be cleaned up when the temporary directory is removed


@pytest.mark.asyncio
async def test_add_message_pair_basic(conversation_manager):
    """Test adding a basic user-assistant message pair."""
    # Setup: Create a new conversation
    unified_msg_origin = "test_platform:FriendMessage:test_user_123"
    conv_id = await conversation_manager.new_conversation(unified_msg_origin)

    # Action: Add a message pair
    user_message = "提醒我检查邮件"
    assistant_message = "好的，我已经设置了提醒"

    await conversation_manager.add_message_pair(
        unified_msg_origin=unified_msg_origin,
        user_message=user_message,
        assistant_message=assistant_message,
        conversation_id=conv_id,
    )

    # Verify: Check that the messages were added to history
    conversation = await conversation_manager.get_conversation(
        unified_msg_origin,
        conv_id,
    )
    assert conversation is not None

    history = json.loads(conversation.history)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == user_message
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == assistant_message


@pytest.mark.asyncio
async def test_add_message_pair_to_existing_history(conversation_manager):
    """Test adding a message pair to a conversation with existing history."""
    # Setup: Create a conversation with existing history
    unified_msg_origin = "test_platform:FriendMessage:test_user_456"
    existing_history = [
        {"role": "user", "content": "你好"},
        {"role": "assistant", "content": "你好！有什么可以帮助你的吗？"},
    ]
    conv_id = await conversation_manager.new_conversation(
        unified_msg_origin,
        content=existing_history,
    )

    # Action: Add a new message pair
    user_message = "现在几点了？"
    assistant_message = "现在是下午3点"

    await conversation_manager.add_message_pair(
        unified_msg_origin=unified_msg_origin,
        user_message=user_message,
        assistant_message=assistant_message,
        conversation_id=conv_id,
    )

    # Verify: Check that the new messages were appended
    conversation = await conversation_manager.get_conversation(
        unified_msg_origin,
        conv_id,
    )
    history = json.loads(conversation.history)
    assert len(history) == 4  # 2 existing + 2 new
    assert history[2]["role"] == "user"
    assert history[2]["content"] == user_message
    assert history[3]["role"] == "assistant"
    assert history[3]["content"] == assistant_message


@pytest.mark.asyncio
async def test_add_message_pair_without_conversation_id(conversation_manager):
    """Test adding a message pair using the current conversation."""
    # Setup: Create a new conversation and set it as current
    unified_msg_origin = "test_platform:FriendMessage:test_user_789"
    conv_id = await conversation_manager.new_conversation(unified_msg_origin)

    # Action: Add a message pair without specifying conversation_id
    user_message = "测试消息"
    assistant_message = "收到测试消息"

    await conversation_manager.add_message_pair(
        unified_msg_origin=unified_msg_origin,
        user_message=user_message,
        assistant_message=assistant_message,
        # conversation_id is not specified, should use current
    )

    # Verify: Check that the messages were added
    conversation = await conversation_manager.get_conversation(
        unified_msg_origin,
        conv_id,
    )
    history = json.loads(conversation.history)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_add_message_pair_no_conversation(conversation_manager):
    """Test that adding a message pair without a conversation logs a warning."""
    # Setup: Use a unified_msg_origin that doesn't have any conversation
    unified_msg_origin = "test_platform:FriendMessage:no_conv_user"

    # Action: Try to add a message pair (should log warning and return early)
    await conversation_manager.add_message_pair(
        unified_msg_origin=unified_msg_origin,
        user_message="测试",
        assistant_message="测试回复",
    )

    # Verify: The method should return early without error
    # (The warning is logged but we can't easily test that here)
    # Just verify no exception was raised


@pytest.mark.asyncio
async def test_add_message_pair_nonexistent_conversation(conversation_manager):
    """Test adding a message pair to a non-existent conversation ID."""
    # Setup
    unified_msg_origin = "test_platform:FriendMessage:test_user_999"
    fake_conv_id = "00000000-0000-0000-0000-000000000000"

    # Action: Try to add a message pair with a fake conversation ID
    await conversation_manager.add_message_pair(
        unified_msg_origin=unified_msg_origin,
        user_message="测试",
        assistant_message="测试回复",
        conversation_id=fake_conv_id,
    )

    # Verify: The method should log a warning and return early
    # No exception should be raised
