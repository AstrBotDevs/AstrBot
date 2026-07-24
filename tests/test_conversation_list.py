import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import event, text
from sqlalchemy import inspect as sqlalchemy_inspect

from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import ConversationV2
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_filtered_conversations_summary_skips_content_and_applies_filters(
    tmp_path: Path,
):
    db = SQLiteDatabase(str(tmp_path / "conversations.db"))
    await db.initialize()

    conversations = [
        ConversationV2(
            conversation_id="group",
            platform_id="qq",
            user_id="qq:GroupMessage:1",
            content=[{"role": "user", "content": "x" * 10_000}],
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="friend",
            platform_id="qq",
            user_id="qq:FriendMessage:2",
            title="中文标题",
            content=[{"role": "assistant", "content": "中文正文 😀"}],
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="other",
            platform_id="telegram",
            user_id="telegram:FriendMessage:3",
            content=[{"role": "assistant", "content": "ordinary"}],
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="webchat",
            platform_id="webchat",
            user_id="webchat:FriendMessage:4",
            content=[{"role": "assistant", "content": "excluded"}],
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="astrbot",
            platform_id="qq",
            user_id="astrbot:FriendMessage:5",
            content=[{"role": "assistant", "content": "excluded"}],
            created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        ),
    ]
    async with db.get_db() as session:
        async with session.begin():
            session.add_all(conversations)

    summary, total = await db.get_filtered_conversations(
        page=1,
        page_size=10,
        include_content=False,
        message_types=["GroupMessage", "FriendMessage"],
        exclude_ids=["astrbot"],
        exclude_platforms=["webchat"],
    )

    assert total == 3
    assert [item.conversation_id for item in summary] == [
        "friend",
        "group",
        "other",
    ]
    assert all("content" in sqlalchemy_inspect(item).unloaded for item in summary)

    manager_summary, manager_total = await ConversationManager(
        db,
    ).get_filtered_conversations(
        page=1,
        page_size=10,
        include_history=False,
        message_types=["GroupMessage", "FriendMessage"],
        exclude_ids=["astrbot"],
        exclude_platforms=["webchat"],
    )
    assert manager_total == total
    assert all(item.history == "[]" for item in manager_summary)
    assert all(json.loads(item.history) == [] for item in manager_summary)

    title_matches, _ = await db.get_filtered_conversations(
        search_query="中文标题",
        include_content=False,
    )
    content_matches, _ = await db.get_filtered_conversations(
        search_query="中文正文",
        include_content=False,
    )
    assert [item.conversation_id for item in title_matches] == ["friend"]
    assert [item.conversation_id for item in content_matches] == ["friend"]

    full, full_total = await db.get_filtered_conversations(page_size=10)
    assert full_total == 5
    assert all("content" not in sqlalchemy_inspect(item).unloaded for item in full)


@pytest.mark.asyncio
async def test_conversation_indexes_are_idempotent_and_support_ordered_list(
    tmp_path: Path,
):
    db = SQLiteDatabase(str(tmp_path / "conversations.db"))
    await db.initialize()
    await db.initialize()

    async with db.get_db() as session:
        index_rows = (
            await session.execute(text("PRAGMA index_list(conversations)"))
        ).all()
        index_names = {row[1] for row in index_rows}
        plan = (
            await session.execute(
                text(
                    "EXPLAIN QUERY PLAN "
                    "SELECT conversation_id FROM conversations "
                    "ORDER BY created_at DESC, inner_conversation_id DESC LIMIT 20"
                )
            )
        ).all()

    assert {
        "ix_conversations_created_at_inner_id",
        "ix_conversations_platform_created_at_inner_id",
        "ix_conversations_platform_user_id",
    }.issubset(index_names)
    assert not any("TEMP B-TREE" in str(row) for row in plan)


@pytest.mark.asyncio
async def test_multi_platform_summary_uses_global_order_index(
    tmp_path: Path,
):
    db = SQLiteDatabase(str(tmp_path / "multi-platform.db"))
    await db.initialize()

    async with db.get_db() as session:
        async with session.begin():
            session.add_all(
                [
                    ConversationV2(
                        conversation_id=f"conversation-{index}",
                        platform_id="qq" if index % 2 else "telegram",
                        user_id=f"platform:FriendMessage:{index}",
                        content=[{"role": "user", "content": "x" * 1000}],
                        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                    )
                    for index in range(20)
                ],
            )

    statements = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        conversations, total = await db.get_filtered_conversations(
            page=1,
            page_size=5,
            platforms=["qq", "telegram"],
            include_content=False,
        )
    finally:
        event.remove(
            db.engine.sync_engine,
            "before_cursor_execute",
            capture_statement,
        )

    assert total == 20
    assert [conversation.conversation_id for conversation in conversations] == [
        "conversation-19",
        "conversation-18",
        "conversation-17",
        "conversation-16",
        "conversation-15",
    ]
    assert all("content" in sqlalchemy_inspect(item).unloaded for item in conversations)

    ordered_queries = [statement for statement in statements if "ORDER BY" in statement]
    assert len(ordered_queries) == 1
    assert (
        "FROM conversations INDEXED BY ix_conversations_created_at_inner_id"
        in ordered_queries[0]
    )
    assert "content" not in ordered_queries[0].split("FROM", 1)[0]
