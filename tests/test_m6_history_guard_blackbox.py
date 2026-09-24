"""Black-box checks for the configured online history size guard."""

from pathlib import Path

import pytest
from sqlalchemy import event, text

from astrbot.core.conversation_history_limits import (
    MAX_ONLINE_HISTORY_BYTES,
    HistoryTooLargeError,
)
from astrbot.core.db.po import ConversationV2
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_real_sqlite_rejects_over_16_mib_malformed_body_before_materializing(
    tmp_path: Path,
):
    db = SQLiteDatabase(str(tmp_path / "oversized-history.db"))
    await db.initialize()
    db.inited = True
    async with db.get_db() as session, session.begin():
        session.add(
            ConversationV2(
                conversation_id="oversized",
                platform_id="platform",
                user_id="user",
                content=[],
            )
        )
    async with db.get_db() as session, session.begin():
        await session.execute(
            text(
                "UPDATE conversations SET content = :body WHERE conversation_id = :cid"
            ),
            {
                # Deliberately malformed JSON proves the byte guard runs before
                # SQLModel's JSON result decoder sees the stored body.
                "body": "x" * (MAX_ONLINE_HISTORY_BYTES + 1),
                "cid": "oversized",
            },
        )

    statements = []

    def capture_statement(
        _connection, _cursor, statement, _parameters, _context, _many
    ):
        statements.append(statement)

    event.listen(db.engine.sync_engine, "before_cursor_execute", capture_statement)
    try:
        with pytest.raises(HistoryTooLargeError) as error:
            await db.get_conversation_by_id("oversized")
    finally:
        event.remove(db.engine.sync_engine, "before_cursor_execute", capture_statement)
        await db.engine.dispose()

    assert error.value.byte_size == MAX_ONLINE_HISTORY_BYTES + 1
    assert error.value.limit_bytes == MAX_ONLINE_HISTORY_BYTES
    assert any(
        "length(CAST(conversations.content AS BLOB))" in statement
        for statement in statements
    )
    assert not any(
        statement.lstrip().upper().startswith("SELECT CONVERSATIONS.CONTENT")
        for statement in statements
    )
