"""Database initialization and session boundaries use real temporary SQLite."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlmodel import select

from astrbot.core.db import BaseDatabase
from astrbot.core.db.po import Preference
from astrbot.core.db.sqlite import SQLiteDatabase


def test_incomplete_database_backend_cannot_be_instantiated():
    with pytest.raises(TypeError, match="abstract"):
        BaseDatabase()


@pytest.mark.asyncio
async def test_first_session_initializes_schema_once_and_reuses_it(
    temp_db, monkeypatch
):
    initialize = AsyncMock(side_effect=temp_db.initialize)
    monkeypatch.setattr(temp_db, "initialize", initialize)
    assert temp_db.inited is False
    async with temp_db.get_db() as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    async with temp_db.get_db() as session:
        names = set(
            (
                await session.execute(
                    text("SELECT name FROM sqlite_master WHERE type = 'table'")
                )
            ).scalars()
        )
    assert {"conversations_v3", "conversation_events"}.issubset(names)
    assert temp_db.inited is True
    initialize.assert_awaited_once()


@pytest.mark.asyncio
async def test_every_connection_enforces_foreign_keys_and_waits_for_busy_writers(
    temp_db,
):
    async with temp_db.get_db() as session:
        assert (await session.execute(text("PRAGMA foreign_keys"))).scalar_one() == 1
        assert (
            await session.execute(text("PRAGMA busy_timeout"))
        ).scalar_one() == 30000


@pytest.mark.asyncio
async def test_failed_initialization_is_not_cached_and_can_be_retried(
    temp_db, monkeypatch
):
    original = temp_db.initialize
    initialize = AsyncMock(side_effect=RuntimeError("migration interrupted"))
    monkeypatch.setattr(temp_db, "initialize", initialize)
    with pytest.raises(RuntimeError, match="migration interrupted"):
        async with temp_db.get_db():
            pytest.fail("An uninitialized session must not be exposed")
    assert temp_db.inited is False
    monkeypatch.setattr(temp_db, "initialize", original)
    async with temp_db.get_db() as session:
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    assert temp_db.inited is True


@pytest.mark.asyncio
@pytest.mark.parametrize("raise_error", [False, True])
async def test_uncommitted_writes_are_rolled_back_when_the_session_exits(
    temp_db, raise_error
):
    async with temp_db.get_db() as session:
        await session.execute(text("CREATE TABLE transaction_probe (value TEXT)"))
        await session.commit()

    async def write_without_commit():
        async with temp_db.get_db() as session:
            await session.execute(
                text("INSERT INTO transaction_probe(value) VALUES (:value)"),
                {"value": "uncommitted"},
            )
            if raise_error:
                raise RuntimeError("abort transaction")

    if raise_error:
        with pytest.raises(RuntimeError, match="abort transaction"):
            await write_without_commit()
    else:
        await write_without_commit()

    async with temp_db.get_db() as session:
        assert (
            await session.execute(text("SELECT count(*) FROM transaction_probe"))
        ).scalar_one() == 0


@pytest.mark.asyncio
async def test_committed_models_remain_readable_after_the_session_closes(temp_db):
    preference = Preference(
        scope="global",
        scope_id="global",
        key="initialization-probe",
        value={"val": "saved"},
    )
    async with temp_db.get_db() as session:
        session.add(preference)
        await session.commit()
    assert preference.value == {"val": "saved"}
    async with temp_db.get_db() as session:
        stored = (
            await session.execute(
                select(Preference).where(Preference.key == "initialization-probe")
            )
        ).scalar_one()
    assert stored.value == {"val": "saved"}


@pytest.mark.asyncio
async def test_consistent_read_enters_an_explicit_transaction(temp_db):
    async with temp_db.get_db(consistent_read=True) as session:
        assert session.in_transaction()
        assert (await session.execute(text("SELECT 1"))).scalar_one() == 1
    async with temp_db.get_db() as session:
        assert not session.in_transaction()
        assert (await session.execute(text("SELECT 2"))).scalar_one() == 2


@pytest.mark.asyncio
async def test_concurrent_first_reads_wait_for_complete_schema(temp_db):
    async def read_tables():
        async with temp_db.get_db() as session:
            return (
                await session.execute(text("SELECT count(*) FROM conversations_v3"))
            ).scalar_one()

    assert await asyncio.gather(*(read_tables() for _ in range(4))) == [0, 0, 0, 0]


@pytest.mark.asyncio
async def test_independent_database_paths_do_not_share_committed_records(
    temp_db, tmp_path
):
    other = SQLiteDatabase(str(tmp_path / "other.db"))
    try:
        await temp_db.create_conversation(
            user_id="bot:FriendMessage:alice",
            platform_id="bot",
            cid="first-only",
            content=[],
        )
        assert [row.conversation_id for row in await temp_db.get_conversations()] == [
            "first-only"
        ]
        assert await other.get_conversations() == []
    finally:
        await other.engine.dispose()
