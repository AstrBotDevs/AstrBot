"""Tests for bounded reads of persisted conversation history."""

import json

import pytest
from sqlalchemy import event, select, text

from astrbot.core import conversation_history_limits
from astrbot.core.conversation_history_limits import HistoryTooLargeError
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.db.po import ConversationV2
from astrbot.core.db.sqlite import SQLiteDatabase


async def _create_conversation(db: SQLiteDatabase, cid: str, content: list) -> None:
    """Create one conversation fixture row."""
    async with db.get_db() as session, session.begin():
        session.add(
            ConversationV2(
                conversation_id=cid,
                user_id="user",
                platform_id="platform",
                content=content,
            )
        )
        await session.flush()


@pytest.mark.asyncio
async def test_single_conversation_limit_measures_stored_utf8_bytes_before_loading(
    temp_db: SQLiteDatabase,
    monkeypatch: pytest.MonkeyPatch,
):
    db = temp_db
    await db.initialize()
    db.inited = True
    await _create_conversation(db, "unicode", [{"role": "user", "content": "x"}])

    raw_history = json.dumps(
        [{"role": "user", "content": "汉😀"}],
        ensure_ascii=False,
    )
    async with db.get_db() as session, session.begin():
        await session.execute(
            text(
                "UPDATE conversations SET content = :content WHERE conversation_id = :cid"
            ),
            {"content": raw_history, "cid": "unicode"},
        )
        stored_size = (
            await session.execute(
                select(
                    conversation_history_limits.history_size_bytes(
                        ConversationV2.content
                    )
                ).where(ConversationV2.conversation_id == "unicode")
            )
        ).scalar_one()
    assert stored_size == len(raw_history.encode("utf-8"))

    monkeypatch.setattr(
        conversation_history_limits,
        "MAX_ONLINE_HISTORY_BYTES",
        stored_size - 1,
    )
    statements = []

    def capture_statement(
        _connection, _cursor, statement, _parameters, _context, _many
    ):
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        with pytest.raises(HistoryTooLargeError) as error:
            await db.get_conversation_by_id("unicode")
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", capture_statement)

    assert error.value.cid == "unicode"
    assert error.value.byte_size == stored_size
    assert error.value.limit_bytes == stored_size - 1
    assert "remains stored" in str(error.value)
    assert any(
        "length(CAST(conversations.content AS BLOB))" in sql for sql in statements
    )
    assert not any("SELECT conversations.content" in sql for sql in statements)

    monkeypatch.setattr(
        conversation_history_limits,
        "MAX_ONLINE_HISTORY_BYTES",
        stored_size,
    )
    loaded = await db.get_conversation_by_id("unicode")
    assert loaded is not None
    assert loaded.content == [{"role": "user", "content": "汉😀"}]


@pytest.mark.asyncio
async def test_conversation_lists_allow_metadata_but_raise_for_oversized_history(
    temp_db: SQLiteDatabase,
    monkeypatch: pytest.MonkeyPatch,
):
    db = temp_db
    await db.initialize()
    db.inited = True
    await _create_conversation(
        db,
        "large",
        [{"role": "user", "content": "x" * 512}],
    )
    monkeypatch.setattr(
        conversation_history_limits,
        "MAX_ONLINE_HISTORY_BYTES",
        256,
    )

    reads = (
        lambda: db.get_conversation_by_id("large"),
        lambda: db.get_conversations(),
        lambda: db.get_all_conversations(),
        lambda: db.get_filtered_conversations(page_size=10),
        lambda: ConversationManager(db).get_conversation(
            "user",
            "large",
            create_if_not_exists=True,
        ),
    )
    for read in reads:
        with pytest.raises(HistoryTooLargeError):
            await read()

    metadata = await db.get_conversation_by_id("large", include_history=False)
    assert metadata is not None
    assert metadata.content is None
    all_metadata = await db.get_conversations(include_history=False)
    page_metadata = await db.get_all_conversations(include_history=False)
    filtered_metadata, total = await db.get_filtered_conversations(
        page_size=10,
        include_history=False,
    )
    assert [item.conversation_id for item in all_metadata] == ["large"]
    assert [item.conversation_id for item in page_metadata] == ["large"]
    assert [item.conversation_id for item in filtered_metadata] == ["large"]
    assert total == 1
    assert all(item.content is None for item in (*all_metadata, *page_metadata))


@pytest.mark.asyncio
async def test_metadata_updates_and_delete_do_not_require_reading_large_history(
    temp_db: SQLiteDatabase,
    monkeypatch: pytest.MonkeyPatch,
):
    db = temp_db
    await db.initialize()
    db.inited = True
    await _create_conversation(
        db,
        "large",
        [{"role": "user", "content": "x" * 512}],
    )
    monkeypatch.setattr(
        conversation_history_limits,
        "MAX_ONLINE_HISTORY_BYTES",
        256,
    )

    updated = await db.update_conversation("large", title="Renamed")
    assert updated is not None
    assert updated.title == "Renamed"
    assert updated.content is None

    with pytest.raises(HistoryTooLargeError):
        await db.update_conversation(
            "large",
            content=[{"role": "user", "content": "replacement"}],
        )

    await db.delete_conversation("large")
    assert await db.get_conversation_by_id("large", include_history=False) is None


@pytest.mark.asyncio
async def test_expected_identity_is_checked_inside_conversation_update(
    temp_db: SQLiteDatabase,
):
    db = temp_db
    await db.initialize()
    db.inited = True
    await _create_conversation(db, "conversation", [{"role": "user", "content": "ok"}])

    with pytest.raises(PermissionError, match="identity changed"):
        await db.update_conversation(
            "conversation",
            title="Should not apply",
            expected_identity=("other-user", "platform"),
        )

    conversation = await db.get_conversation_by_id(
        "conversation",
        include_history=False,
    )
    assert conversation is not None
    assert conversation.title is None

    await ConversationManager(db).update_conversation(
        "user",
        conversation_id="conversation",
        title="Accepted",
        expected_identity=("user", "platform"),
    )
    conversation = await db.get_conversation_by_id(
        "conversation",
        include_history=False,
    )
    assert conversation is not None
    assert conversation.title == "Accepted"
