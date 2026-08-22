from datetime import UTC, datetime, timedelta

import pytest

from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_update_conversation_returns_none_for_empty_update_and_applies_partial_fields(
    temp_db: SQLiteDatabase,
):
    conversation = await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="Original",
        content=[{"text": "before"}],
        persona_id="persona-before",
        cid="conv-update",
    )

    assert await temp_db.update_conversation(conversation.conversation_id) is None

    updated = await temp_db.update_conversation(
        conversation.conversation_id,
        title="Updated",
        content=[{"text": "after"}],
        token_usage=12,
    )

    assert updated is not None
    assert updated.conversation_id == conversation.conversation_id
    assert updated.title == "Updated"
    assert updated.persona_id == "persona-before"
    assert updated.content == [{"text": "after"}]
    assert updated.token_usage == 12


@pytest.mark.asyncio
async def test_get_conversations_filters_and_get_all_conversations_paginates_by_latest(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="Old telegram",
        cid="conv-old",
        created_at=now - timedelta(minutes=3),
        updated_at=now - timedelta(minutes=3),
    )
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="New telegram",
        cid="conv-new",
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )
    await temp_db.create_conversation(
        user_id="discord:FriendMessage:user-2",
        platform_id="discord",
        title="Discord",
        cid="conv-discord",
        created_at=now - timedelta(minutes=2),
        updated_at=now - timedelta(minutes=2),
    )

    filtered = await temp_db.get_conversations(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
    )
    paged = await temp_db.get_all_conversations(page=1, page_size=2)

    assert [conversation.conversation_id for conversation in filtered] == [
        "conv-new",
        "conv-old",
    ]
    assert [conversation.conversation_id for conversation in paged] == [
        "conv-new",
        "conv-discord",
    ]


@pytest.mark.asyncio
async def test_delete_conversation_and_delete_conversations_by_user_id_scope_correctly(
    temp_db: SQLiteDatabase,
):
    target = await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        cid="conv-target",
    )
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        cid="conv-user-delete",
    )
    survivor = await temp_db.create_conversation(
        user_id="discord:FriendMessage:user-2",
        platform_id="discord",
        cid="conv-survivor",
    )

    await temp_db.delete_conversation(target.conversation_id)
    await temp_db.delete_conversations_by_user_id("telegram:FriendMessage:user-1")

    assert await temp_db.get_conversation_by_id(target.conversation_id) is None
    assert await temp_db.get_conversation_by_id("conv-user-delete") is None
    remaining = await temp_db.get_conversation_by_id(survivor.conversation_id)
    assert remaining is not None
    assert remaining.conversation_id == survivor.conversation_id


@pytest.mark.asyncio
async def test_get_filtered_conversations_combines_filters_and_paginates(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    await temp_db.create_conversation(
        user_id="telegram:FriendMessage:user-1",
        platform_id="telegram",
        title="Alpha match",
        content=[{"text": "one"}],
        cid="conv-1",
        created_at=now - timedelta(minutes=3),
        updated_at=now - timedelta(minutes=3),
    )
    await temp_db.create_conversation(
        user_id="telegram:GroupMessage:user-2",
        platform_id="telegram",
        title="Alpha group",
        content=[{"text": "two"}],
        cid="conv-2",
        created_at=now - timedelta(minutes=2),
        updated_at=now - timedelta(minutes=2),
    )
    await temp_db.create_conversation(
        user_id="discord:FriendMessage:user-3",
        platform_id="discord",
        title="Alpha discord",
        content=[{"text": "three"}],
        cid="conv-3",
        created_at=now - timedelta(minutes=1),
        updated_at=now - timedelta(minutes=1),
    )

    conversations, total = await temp_db.get_filtered_conversations(
        page=1,
        page_size=1,
        platform_ids=["telegram", "discord"],
        search_query="Alpha",
        message_types=["FriendMessage"],
        platforms=["telegram"],
    )

    assert total == 1
    assert [conversation.conversation_id for conversation in conversations] == [
        "conv-1"
    ]


@pytest.mark.asyncio
async def test_get_filtered_conversations_supports_unicode_and_literal_wildcards(
    temp_db: SQLiteDatabase,
):
    await temp_db.create_conversation(
        user_id="wechat:FriendMessage:user-1",
        platform_id="wechat",
        title="中文 100% 命中",
        content=[{"text": "内容"}],
        cid="conv-unicode",
    )
    await temp_db.create_conversation(
        user_id="wechat:FriendMessage:user-2",
        platform_id="wechat",
        title="中文 100X 命中",
        content=[{"text": "内容"}],
        cid="conv-other",
    )

    conversations, total = await temp_db.get_filtered_conversations(
        page=1,
        page_size=10,
        search_query="中文 100%",
    )

    assert total == 1
    assert [conversation.conversation_id for conversation in conversations] == [
        "conv-unicode"
    ]


@pytest.mark.asyncio
async def test_get_session_conversations_joins_preferences_conversations_and_personas(
    temp_db: SQLiteDatabase,
):
    persona = await temp_db.insert_persona(
        persona_id="persona-a",
        system_prompt="prompt",
    )
    await temp_db.create_conversation(
        user_id="umo-1",
        platform_id="webchat",
        title="Session Alpha",
        persona_id=persona.persona_id,
        cid="conv-a",
    )
    await temp_db.create_conversation(
        user_id="umo-2",
        platform_id="telegram",
        title="Other Title",
        cid="conv-b",
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "webchat:FriendMessage:webchat!alice!session-a",
        "sel_conv_id",
        {"val": "conv-a"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "telegram:FriendMessage:telegram!alice!session-b",
        "sel_conv_id",
        {"val": "conv-b"},
    )

    rows, total = await temp_db.get_session_conversations(
        page=1,
        page_size=10,
        search_query="Alpha",
        platform="webchat",
    )

    assert total == 1
    assert rows == [
        {
            "session_id": "webchat:FriendMessage:webchat!alice!session-a",
            "conversation_id": "conv-a",
            "persona_id": "persona-a",
            "title": "Session Alpha",
            "persona_name": "persona-a",
        }
    ]


@pytest.mark.asyncio
async def test_get_session_conversations_handles_missing_related_rows_and_pagination(
    temp_db: SQLiteDatabase,
):
    await temp_db.create_conversation(
        user_id="umo-1",
        platform_id="webchat",
        title="Alpha",
        cid="conv-a",
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "a:webchat:session",
        "sel_conv_id",
        {"val": "missing-conv"},
    )
    await temp_db.insert_preference_or_update(
        "umo",
        "b:webchat:session",
        "sel_conv_id",
        {"val": "conv-a"},
    )

    page_one, total = await temp_db.get_session_conversations(
        page=1,
        page_size=1,
    )
    page_two, _ = await temp_db.get_session_conversations(
        page=2,
        page_size=1,
    )
    missing = await temp_db.get_session_conversations(
        page=1,
        page_size=10,
        search_query="does-not-exist",
        platform="discord",
    )

    assert total == 2
    assert page_one == [
        {
            "session_id": "a:webchat:session",
            "conversation_id": "missing-conv",
            "persona_id": None,
            "title": None,
            "persona_name": None,
        }
    ]
    assert page_two == [
        {
            "session_id": "b:webchat:session",
            "conversation_id": "conv-a",
            "persona_id": None,
            "title": "Alpha",
            "persona_name": None,
        }
    ]
    assert missing == ([], 0)
