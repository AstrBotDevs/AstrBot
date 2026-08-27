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
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="friend",
            platform_id="qq",
            user_id="qq:FriendMessage:2",
            title="中文标题",
            content=[{"role": "assistant", "content": "中文正文 😀"}],
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="other",
            platform_id="telegram",
            user_id="telegram:FriendMessage:3",
            content=[{"role": "assistant", "content": "ordinary"}],
            created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="webchat",
            platform_id="webchat",
            user_id="webchat:FriendMessage:4",
            content=[{"role": "assistant", "content": "excluded"}],
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        ),
        ConversationV2(
            conversation_id="astrbot",
            platform_id="qq",
            user_id="astrbot:FriendMessage:5",
            content=[{"role": "assistant", "content": "excluded"}],
            created_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            updated_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
        ),
    ]
    async with db.get_db() as session:
        async with session.begin():
            session.add_all(conversations)

    summary, total = await db.get_filtered_conversations(
        page=1,
        page_size=10,
        include_history=False,
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
        include_history=False,
    )
    content_matches, _ = await db.get_filtered_conversations(
        search_query="中文正文",
        include_history=False,
    )
    assert [item.conversation_id for item in title_matches] == ["friend"]
    assert [item.conversation_id for item in content_matches] == ["friend"]

    keyword_matches, _ = await db.get_filtered_conversations(
        keyword_query="中文正文",
        include_history=False,
    )
    keyword_does_not_match_umo, _ = await db.get_filtered_conversations(
        keyword_query="FriendMessage:2",
        include_history=False,
    )
    assert [item.conversation_id for item in keyword_matches] == ["friend"]
    assert keyword_does_not_match_umo == []

    full, full_total = await db.get_filtered_conversations(page_size=10)
    assert full_total == 5
    assert all("content" not in sqlalchemy_inspect(item).unloaded for item in full)

    umo_matches, _ = await db.get_filtered_conversations(
        umo_query="FriendMessage:2",
        include_history=False,
    )
    assert [item.conversation_id for item in umo_matches] == ["friend"]

    updated_ascending, _ = await db.get_filtered_conversations(
        page_size=10,
        sort_by="updated_at",
        sort_order="asc",
        include_history=False,
    )
    assert [item.conversation_id for item in updated_ascending] == [
        "astrbot",
        "webchat",
        "other",
        "group",
        "friend",
    ]

    assert await db.get_conversation_platform_ids() == [
        "qq",
        "telegram",
        "webchat",
    ]


@pytest.mark.asyncio
async def test_filtered_conversations_can_paginate_complete_session_groups(
    tmp_path: Path,
):
    db = SQLiteDatabase(str(tmp_path / "grouped-conversations.db"))
    await db.initialize()

    def conversation(cid: str, user_id: str, day: int) -> ConversationV2:
        """Build a dated conversation fixture.

        Args:
            cid: Conversation ID.
            user_id: Unified message origin.
            day: Day used for the created and updated timestamps.

        Returns:
            Conversation fixture.
        """
        timestamp = datetime(2026, 1, day, tzinfo=timezone.utc)
        return ConversationV2(
            conversation_id=cid,
            platform_id="qq",
            user_id=user_id,
            content=[{"role": "user", "content": cid}],
            created_at=timestamp,
            updated_at=timestamp,
        )

    async with db.get_db() as session:
        async with session.begin():
            session.add_all(
                [
                    conversation("a-old", "qq:FriendMessage:a", 1),
                    conversation("a-new", "qq:FriendMessage:a", 2),
                    conversation("b-old", "qq:FriendMessage:b", 3),
                    conversation("b-new", "qq:FriendMessage:b", 4),
                    conversation("c-only", "qq:FriendMessage:c", 5),
                ]
            )

    first_page, total_sessions = await db.get_filtered_conversations(
        page=1,
        page_size=2,
        sort_by="updated_at",
        sort_order="desc",
        group_by_session=True,
        include_history=False,
    )
    second_page, second_total = await db.get_filtered_conversations(
        page=2,
        page_size=2,
        sort_by="updated_at",
        sort_order="desc",
        group_by_session=True,
        include_history=False,
    )

    assert total_sessions == second_total == 3
    assert [item.conversation_id for item in first_page] == [
        "c-only",
        "b-new",
        "b-old",
    ]
    assert [item.conversation_id for item in second_page] == ["a-new", "a-old"]
    assert all("content" in sqlalchemy_inspect(item).unloaded for item in first_page)


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

    expected_indexes = {
        "ix_conversations_created_at_inner_id",
        "ix_conversations_platform_created_at_inner_id",
    }
    assert expected_indexes.issubset(index_names)
    assert expected_indexes.issubset(
        {index.name for index in ConversationV2.__table__.indexes}
    )
    assert "ix_conversations_platform_user_id" not in index_names
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
            include_history=False,
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
