import pytest

from astrbot.core.message.components import File, Image, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager


@pytest.mark.asyncio
async def test_group_history_sanitizes_media_and_retains_only_group_scope(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    image = Image.fromURL("https://secret.example.invalid/private.png")
    file = File("private.txt", "/home/alice/private.txt")

    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-1",
        message_chain=MessageChain([Plain("hello"), image, file]),
        role="user",
        is_group=True,
        sender_id="u1",
        sender_name="Alice",
        max_messages=1,
    )
    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-2",
        message_chain=MessageChain([Plain("other")]),
        role="user",
        is_group=True,
        sender_id="u2",
        sender_name="Bob",
    )

    rows = await manager.get_group(
        "onebot",
        "onebot:GroupMessage:group-1",
        limit=20,
    )
    assert len(rows) == 1
    assert rows[0].is_group is True
    assert rows[0].role == "user"
    assert rows[0].content["message"] == [
        {"type": "plain", "text": "hello"},
        {"type": "image", "text": "[Image]"},
        {"type": "file", "text": "[File]"},
    ]
    assert "secret.example" not in str(rows[0].content)
    assert "/home/alice" not in str(rows[0].content)


@pytest.mark.asyncio
async def test_group_history_retention_is_atomic_and_excludes_non_group_rows(temp_db):
    manager = PlatformMessageHistoryManager(temp_db)
    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-1",
        message_chain=MessageChain([Plain("first")]),
        role="user",
        is_group=True,
        max_messages=2,
    )
    await manager.insert_message_chain(
        platform_id="onebot",
        user_id="onebot:GroupMessage:group-1",
        message_chain=MessageChain([Plain("second")]),
        role="assistant",
        is_group=True,
        max_messages=2,
    )
    await manager.insert(
        "onebot",
        "onebot:GroupMessage:group-1",
        {"message": [{"type": "plain", "text": "legacy"}]},
        role="user",
        is_group=False,
    )

    group_rows = await manager.get_group("onebot", "onebot:GroupMessage:group-1")
    all_rows = await manager.get("onebot", "onebot:GroupMessage:group-1")
    assert [row.content["message"][0]["text"] for row in group_rows] == [
        "first",
        "second",
    ]
    assert {row.content["message"][0]["text"] for row in all_rows} == {
        "legacy",
        "first",
        "second",
    }
