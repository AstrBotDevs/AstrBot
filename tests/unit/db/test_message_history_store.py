from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import col, update

from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_platform_message_history_update_and_offset_delete(
    temp_db: SQLiteDatabase,
):
    now = datetime.now()
    older = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "user", "message": [{"type": "plain", "text": "old"}]},
        llm_checkpoint_id="ck-old",
    )
    newer = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "bot", "message": [{"type": "plain", "text": "new"}]},
        llm_checkpoint_id="ck-new",
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == older.id)
                .values(created_at=now - timedelta(days=3))
            )
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == newer.id)
                .values(created_at=now)
            )

    await temp_db.update_platform_message_history(
        newer.id,
        content={"type": "bot", "message": [{"type": "plain", "text": "updated"}]},
        llm_checkpoint_id="ck-updated",
    )
    updated_before_delete = await temp_db.get_platform_message_history_by_id(newer.id)
    assert updated_before_delete is not None
    assert updated_before_delete.content == {
        "type": "bot",
        "message": [{"type": "plain", "text": "updated"}],
    }
    assert updated_before_delete.llm_checkpoint_id == "ck-updated"

    await temp_db.delete_platform_message_offset(
        "webchat",
        "session-1",
        offset_sec=3600,
    )

    remaining = await temp_db.get_platform_message_history("webchat", "session-1")
    assert [row.id for row in remaining] == [older.id]

    updated_row = await temp_db.get_platform_message_history_by_id(newer.id)
    assert updated_row is None
    preserved_row = await temp_db.get_platform_message_history_by_id(older.id)
    assert preserved_row is not None
    assert preserved_row.llm_checkpoint_id == "ck-old"


@pytest.mark.asyncio
async def test_get_platform_message_history_is_paginated_and_scoped_by_platform_and_user(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    first = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "user", "message": [{"type": "plain", "text": "first"}]},
    )
    second = await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-1",
        content={"type": "bot", "message": [{"type": "plain", "text": "second"}]},
    )
    await temp_db.insert_platform_message_history(
        platform_id="telegram",
        user_id="session-1",
        content={
            "type": "user",
            "message": [{"type": "plain", "text": "other platform"}],
        },
    )
    await temp_db.insert_platform_message_history(
        platform_id="webchat",
        user_id="session-2",
        content={"type": "user", "message": [{"type": "plain", "text": "other user"}]},
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == first.id)
                .values(created_at=now - timedelta(minutes=2))
            )
            await session.execute(
                update(PlatformMessageHistory)
                .where(col(PlatformMessageHistory.id) == second.id)
                .values(created_at=now - timedelta(minutes=1))
            )

    page_one = await temp_db.get_platform_message_history(
        "webchat",
        "session-1",
        page=1,
        page_size=1,
    )
    page_two = await temp_db.get_platform_message_history(
        "webchat",
        "session-1",
        page=2,
        page_size=1,
    )

    assert [row.id for row in page_one] == [second.id]
    assert [row.id for row in page_two] == [first.id]
