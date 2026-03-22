from __future__ import annotations

from datetime import datetime, timezone

import pytest

from astrbot_sdk._internal.testing_support import MockContext
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.message.components import Plain
from astrbot_sdk.message.session import MessageSession


def _session_store_key(session: MessageSession) -> str:
    return f"{session.platform_id}:{session.message_type}:{session.session_id}"


@pytest.mark.asyncio
async def test_mock_context_message_history_round_trip_and_aliases() -> None:
    ctx = MockContext(plugin_id="sdk-demo")
    private_session = MessageSession(
        platform_id="demo-platform",
        message_type="private",
        session_id="user-1",
    )
    group_session = MessageSession(
        platform_id="demo-platform",
        message_type="group",
        session_id="user-1",
    )

    assert ctx.message_history_manager is ctx.message_history

    first = await ctx.message_history.append(
        private_session,
        parts=[Plain("first", convert=False)],
        sender={"sender_id": "sender-1", "sender_name": "Tester"},
        metadata={"source": "test"},
        idempotency_key="idem-1",
    )
    repeated = await ctx.message_history.append(
        private_session,
        parts=[Plain("first", convert=False)],
        sender={"sender_id": "sender-1", "sender_name": "Tester"},
        metadata={"source": "test"},
        idempotency_key="idem-1",
    )
    second = await ctx.message_history.append(
        private_session,
        parts=[Plain("second", convert=False)],
        sender={"sender_id": "sender-2", "sender_name": "Tester 2"},
    )
    third = await ctx.message_history.append(
        private_session,
        parts=[Plain("third", convert=False)],
        sender={"sender_id": "sender-3", "sender_name": "Tester 3"},
    )
    group_record = await ctx.message_history.append(
        group_session,
        parts=[Plain("group only", convert=False)],
        sender={"sender_id": "group-sender", "sender_name": "Group Tester"},
    )

    assert repeated.id == first.id
    assert group_record.session.message_type == "group"

    first_page = await ctx.message_history.list(private_session, limit=2)
    assert [record.id for record in first_page.records] == [third.id, second.id]
    assert first_page.next_cursor == str(second.id)
    assert first_page.total == 3
    assert first_page.records[0].parts[0].text == "third"

    second_page = await ctx.message_history.list(
        private_session,
        cursor=first_page.next_cursor,
        limit=2,
    )
    assert [record.id for record in second_page.records] == [first.id]
    assert second_page.next_cursor is None

    fetched = await ctx.message_history.get(private_session, second.id)
    assert fetched is not None
    assert fetched.sender.sender_id == "sender-2"
    assert fetched.metadata == {}
    assert fetched.parts[0].text == "second"

    group_page = await ctx.message_history.list(group_session, limit=10)
    assert [record.id for record in group_page.records] == [group_record.id]

    store = ctx.router._message_history_store[_session_store_key(private_session)]
    timestamps = {
        first.id: "2026-03-20T00:00:00+00:00",
        second.id: "2026-03-21T00:00:00+00:00",
        third.id: "2026-03-22T00:00:00+00:00",
    }
    for record in store:
        stamped = timestamps.get(int(record["id"]))
        if stamped is None:
            continue
        record["created_at"] = stamped
        record["updated_at"] = stamped

    deleted_before = await ctx.message_history.delete_before(
        private_session,
        before=datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc),
    )
    assert deleted_before == 1
    remaining_after_before = await ctx.message_history.list(private_session, limit=10)
    assert [record.id for record in remaining_after_before.records] == [
        third.id,
        second.id,
    ]

    deleted_after = await ctx.message_history.delete_after(
        private_session,
        after=datetime(2026, 3, 21, 12, 0, tzinfo=timezone.utc),
    )
    assert deleted_after == 1
    remaining_after_after = await ctx.message_history.list(private_session, limit=10)
    assert [record.id for record in remaining_after_after.records] == [second.id]

    deleted_all = await ctx.message_history.delete_all(private_session)
    assert deleted_all == 1
    assert (await ctx.message_history.list(private_session, limit=10)).records == []
    assert [
        record.id
        for record in (await ctx.message_history.list(group_session, limit=10)).records
    ] == [group_record.id]


@pytest.mark.asyncio
async def test_message_history_delete_boundaries_normalize_naive_datetime_to_utc() -> (
    None
):
    ctx = MockContext(plugin_id="sdk-demo")
    session = MessageSession(
        platform_id="demo-platform",
        message_type="private",
        session_id="user-1",
    )

    first = await ctx.message_history.append(
        session,
        parts=[Plain("first", convert=False)],
        sender={"sender_id": "sender-1", "sender_name": "Tester"},
    )
    second = await ctx.message_history.append(
        session,
        parts=[Plain("second", convert=False)],
        sender={"sender_id": "sender-2", "sender_name": "Tester 2"},
    )
    third = await ctx.message_history.append(
        session,
        parts=[Plain("third", convert=False)],
        sender={"sender_id": "sender-3", "sender_name": "Tester 3"},
    )

    store = ctx.router._message_history_store[_session_store_key(session)]
    timestamps = {
        first.id: "2026-03-20T00:00:00+00:00",
        second.id: "2026-03-21T00:00:00+00:00",
        third.id: "2026-03-22T00:00:00+00:00",
    }
    for record in store:
        stamped = timestamps.get(int(record["id"]))
        if stamped is None:
            continue
        record["created_at"] = stamped
        record["updated_at"] = stamped

    deleted_before = await ctx.message_history.delete_before(
        session,
        before=datetime(2026, 3, 21, 0, 0),
    )
    assert deleted_before == 1

    deleted_after = await ctx.message_history.delete_after(
        session,
        after=datetime(2026, 3, 21, 12, 0),
    )
    assert deleted_after == 1

    remaining = await ctx.message_history.list(session, limit=10)
    assert [record.id for record in remaining.records] == [second.id]


@pytest.mark.asyncio
async def test_message_history_list_invalid_cursor_returns_invalid_input() -> None:
    ctx = MockContext(plugin_id="sdk-demo")
    session = MessageSession(
        platform_id="demo-platform",
        message_type="private",
        session_id="user-1",
    )
    await ctx.message_history.append(
        session,
        parts=[Plain("first", convert=False)],
        sender={"sender_id": "sender-1", "sender_name": "Tester"},
    )

    with pytest.raises(AstrBotError) as exc_info:
        await ctx.message_history.list(session, cursor="abc")

    assert exc_info.value.code == "invalid_input"
