from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import col, update

from astrbot.core.db.po import WebChatThread
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_webchat_thread_queries_and_bulk_delete_paths(temp_db: SQLiteDatabase):
    first = await temp_db.create_webchat_thread(
        creator="alice",
        parent_session_id="session-1",
        parent_message_id=10,
        base_checkpoint_id="ck-1",
        selected_text="quote one",
    )
    second = await temp_db.create_webchat_thread(
        creator="bob",
        parent_session_id="session-1",
        parent_message_id=11,
        base_checkpoint_id="ck-2",
        selected_text="quote two",
    )
    third = await temp_db.create_webchat_thread(
        creator="alice",
        parent_session_id="session-2",
        parent_message_id=10,
        base_checkpoint_id="ck-3",
        selected_text="quote three",
    )

    by_session = await temp_db.get_webchat_threads_by_parent_session(
        "session-1",
        creator="alice",
    )
    assert [thread.thread_id for thread in by_session] == [first.thread_id]

    same_text = await temp_db.get_webchat_thread_by_parent_message_and_text(
        "session-1",
        10,
        "quote one",
        creator="alice",
    )
    assert same_text is not None
    assert same_text.thread_id == first.thread_id
    assert (
        await temp_db.get_webchat_thread_by_parent_message_and_text(
            "session-1",
            10,
            "quote one",
            creator="bob",
        )
        is None
    )

    deleted_by_message = await temp_db.delete_webchat_threads_by_parent_message_ids(
        "session-1",
        [11, 99],
    )
    assert deleted_by_message == [second.thread_id]
    assert await temp_db.get_webchat_thread_by_id(second.thread_id) is None
    assert (
        await temp_db.delete_webchat_threads_by_parent_message_ids("session-1", [])
        == []
    )

    deleted_by_session = await temp_db.delete_webchat_threads_by_parent_session(
        "session-1"
    )
    assert deleted_by_session == [first.thread_id]
    assert await temp_db.get_webchat_thread_by_id(first.thread_id) is None
    assert await temp_db.get_webchat_thread_by_id(third.thread_id) is not None


@pytest.mark.asyncio
async def test_get_webchat_threads_by_parent_session_without_creator_orders_by_created_at(
    temp_db: SQLiteDatabase,
):
    now = datetime.now(UTC)
    first = await temp_db.create_webchat_thread(
        creator="alice",
        parent_session_id="session-1",
        parent_message_id=10,
        base_checkpoint_id="ck-1",
        selected_text="first",
    )
    second = await temp_db.create_webchat_thread(
        creator="bob",
        parent_session_id="session-1",
        parent_message_id=11,
        base_checkpoint_id="ck-2",
        selected_text="second",
    )

    async with temp_db.get_db() as session:
        async with session.begin():
            await session.execute(
                update(WebChatThread)
                .where(col(WebChatThread.thread_id) == second.thread_id)
                .values(created_at=now - timedelta(minutes=2))
            )
            await session.execute(
                update(WebChatThread)
                .where(col(WebChatThread.thread_id) == first.thread_id)
                .values(created_at=now - timedelta(minutes=1))
            )

    threads = await temp_db.get_webchat_threads_by_parent_session("session-1")

    assert [thread.thread_id for thread in threads] == [
        second.thread_id,
        first.thread_id,
    ]
