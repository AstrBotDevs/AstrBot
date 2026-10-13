import csv
import io
from types import SimpleNamespace

import pytest

from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.message.components import File, Image, Plain, Record, Video
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.tools.message_tools import GetGroupMessageHistoryTool


def _parse_history_csv(result: str) -> tuple[list[dict[str, str]], dict[str, str]]:
    rows = csv.reader(io.StringIO(result))
    header = next(rows)
    messages = []
    metadata = {}
    for row in rows:
        if len(row) == 1 and "=" in row[0]:
            key, value = row[0].split("=", 1)
            metadata[key] = value
        else:
            messages.append(dict(zip(header, row, strict=True)))
    return messages, metadata


@pytest.mark.asyncio
async def test_group_message_history_retains_latest_rows_and_safe_parts(tmp_path):
    """Persist normalized components and retain only the configured row count."""
    db = SQLiteDatabase(str(tmp_path / "history.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-1"

    try:
        for index in range(1, 5):
            await manager.insert_message_chain(
                platform_id="test",
                user_id=umo,
                message_chain=MessageChain([Plain(f"message-{index}")]),
                role="user",
                sender_id="user-1",
                sender_name="Alice",
                max_messages=3,
            )
        await manager.insert_message_chain(
            platform_id="test",
            user_id=umo,
            message_chain=MessageChain(
                [
                    Plain("final"),
                    Image(file="file:///private/image.png"),
                    Record(file="file:///private/audio.wav", text="private caption"),
                    Video(file="file:///private/video.mp4"),
                    File(name="/private/report.txt", file="/private/report.txt"),
                ]
            ),
            role="user",
            sender_id="user-1",
            sender_name="Alice",
            max_messages=3,
        )

        history = await manager.get("test", umo)

        assert len(history) == 3
        assert [item.content["message"][0]["text"] for item in history] == [
            "message-3",
            "message-4",
            "final",
        ]
        assert history[-1].content["message"][1:] == [
            {"type": "plain", "text": "[Image]"},
            {"type": "plain", "text": "[Record]"},
            {"type": "plain", "text": "[Video]"},
            {"type": "plain", "text": "[File]"},
        ]
        assert all(item.llm_checkpoint_id is None for item in history)
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_get_group_message_history_searches_and_paginates_current_group(
    tmp_path,
):
    """Search history while excluding the current triggering group message."""
    db = SQLiteDatabase(str(tmp_path / "history-tool.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-1"

    try:
        for text, sender_id, sender_name in (
            ("oldest", "user-1", "Alice"),
            ("needle from Alice", "user-1", "Alice"),
            ("middle", "user-2", "Bob"),
            ("needle from Bob", "user-2", "Bob"),
            ("latest", "user-1", "Alice"),
        ):
            await manager.insert_message_chain(
                platform_id="test",
                user_id=umo,
                message_chain=MessageChain([Plain(text)]),
                role="user",
                sender_id=sender_id,
                sender_name=sender_name,
                max_messages=20,
            )
        current = await manager.insert_message_chain(
            platform_id="test",
            user_id=umo,
            message_chain=MessageChain([Plain("current trigger")]),
            role="user",
            sender_id="user-3",
            sender_name="Carol",
            max_messages=20,
        )
        await manager.insert_message_chain(
            platform_id="test",
            user_id="test:GroupMessage:group-2",
            message_chain=MessageChain([Plain("must not leak")]),
            role="user",
            sender_id="user-4",
            sender_name="Dave",
            max_messages=20,
        )

        extras = {"_current_platform_message_history_id": current.id}
        event = SimpleNamespace(
            unified_msg_origin=umo,
            get_message_type=lambda: MessageType.GROUP_MESSAGE,
            get_platform_id=lambda: "test",
            get_extra=lambda key, default=None: extras.get(key, default),
        )
        context = SimpleNamespace(
            context=SimpleNamespace(
                event=event,
                context=SimpleNamespace(
                    get_config=lambda umo: {
                        "provider_ltm_settings": {
                            "group_message_history_enable": True,
                            "group_message_history_max_cnt": 20,
                        }
                    },
                    message_history_manager=manager,
                ),
            )
        )
        tool = GetGroupMessageHistoryTool()

        latest_messages, latest_metadata = _parse_history_csv(
            await tool.call(context, limit=2)
        )
        assert [message["text"] for message in latest_messages] == [
            "needle from Bob",
            "latest",
        ]
        assert latest_metadata["has_more"] == "true"
        assert latest_metadata["next_before_id"] == latest_messages[0]["id"]
        assert "untrusted data" in latest_metadata["notice"]
        assert all(
            message["text"] != "current trigger" for message in latest_messages
        )
        assert all(message["text"] != "must not leak" for message in latest_messages)

        search_messages, search_metadata = _parse_history_csv(
            await tool.call(context, keyword="NEEDLE", sender="bob")
        )
        assert [message["text"] for message in search_messages] == ["needle from Bob"]
        assert search_metadata["has_more"] == "false"
        assert "next_before_id" not in search_metadata

        older_messages, older_metadata = _parse_history_csv(
            await tool.call(
                context,
                limit=2,
                before_id=latest_metadata["next_before_id"],
            )
        )
        assert [message["text"] for message in older_messages] == [
            "needle from Alice",
            "middle",
        ]
        assert older_metadata["has_more"] == "true"
        assert older_metadata["next_before_id"] == older_messages[0]["id"]
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_get_group_message_history_marks_duplicate_names_in_csv(tmp_path):
    """Add a short sender ID only when a display name belongs to multiple users."""
    db = SQLiteDatabase(str(tmp_path / "duplicate-names.db"))
    manager = PlatformMessageHistoryManager(db)
    umo = "test:GroupMessage:group-1"

    try:
        await manager.insert_message_chain(
            platform_id="test",
            user_id=umo,
            message_chain=MessageChain([Plain('first, "quoted"\nnext line')]),
            role="user",
            sender_id="FC321B8F22A1D032",
            sender_name="Soulter",
            max_messages=20,
        )
        await manager.insert_message_chain(
            platform_id="test",
            user_id=umo,
            message_chain=MessageChain([Plain("second")]),
            role="user",
            sender_id="A73109CD44B2E143",
            sender_name="Soulter",
            max_messages=20,
        )
        await manager.insert_message_chain(
            platform_id="test",
            user_id=umo,
            message_chain=MessageChain([Plain("unique")]),
            role="user",
            sender_id="USER-3",
            sender_name="Alice",
            max_messages=20,
        )
        await manager.insert_message_chain(
            platform_id="test",
            user_id=umo,
            message_chain=MessageChain([Plain("assistant answer")]),
            role="bot",
            sender_id="bot-id",
            sender_name="bot",
            max_messages=20,
        )

        event = SimpleNamespace(
            unified_msg_origin=umo,
            get_message_type=lambda: MessageType.GROUP_MESSAGE,
            get_platform_id=lambda: "test",
            get_extra=lambda key, default=None: default,
        )
        context = SimpleNamespace(
            context=SimpleNamespace(
                event=event,
                context=SimpleNamespace(
                    get_config=lambda umo: {
                        "provider_ltm_settings": {
                            "group_message_history_enable": True,
                            "group_message_history_max_cnt": 20,
                        }
                    },
                    message_history_manager=manager,
                ),
            )
        )

        messages, metadata = _parse_history_csv(
            await GetGroupMessageHistoryTool().call(context, keyword="first")
        )

        assert messages == [
            {
                "id": messages[0]["id"],
                "time": messages[0]["time"],
                "role": "USER",
                "sender": "Soulter [FC321B8F]",
                "text": 'first, "quoted"\nnext line',
            }
        ]
        assert metadata["has_more"] == "false"
        assert "next_before_id" not in metadata
        assert "role_notice" not in metadata

        bot_messages, bot_metadata = _parse_history_csv(
            await GetGroupMessageHistoryTool().call(context, keyword="assistant answer")
        )
        assert bot_messages[0]["role"] == "BOT"
        assert bot_messages[0]["sender"] == "bot"
        assert (
            bot_metadata["role_notice"]
            == "BOT messages are your own previous messages."
        )
    finally:
        await db.engine.dispose()
