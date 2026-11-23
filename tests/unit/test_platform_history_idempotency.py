"""History lookup keys survive schema upgrades and legacy query boundaries."""

import asyncio
import json
import sqlite3
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.exc import MultipleResultsFound, OperationalError
from sqlmodel import text

from astrbot.core.db.po import PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def history_db(tmp_path: Path) -> AsyncIterator[SQLiteDatabase]:
    database = SQLiteDatabase(str(tmp_path / "history.db"))
    try:
        yield database
    finally:
        await database.engine.dispose()


def history(
    key: str | None,
    *,
    platform: str = "test",
    user: str = "session",
) -> PlatformMessageHistory:
    return PlatformMessageHistory(
        platform_id=platform,
        user_id=user,
        content={"message": []},
        idempotency_key=key,
    )


@pytest.mark.asyncio
async def test_history_key_persists_and_lookup_is_scoped(
    history_db: SQLiteDatabase,
) -> None:
    records = [
        history("same-key"),
        history("same-key", platform="other"),
        history("same-key", user="other"),
        history("another-key"),
    ]
    async with history_db.get_db() as session:
        session.add_all(records)
        await session.commit()

    for inserted in records:
        found = await history_db.find_platform_message_history_by_idempotency_key(
            inserted.platform_id, inserted.user_id, inserted.idempotency_key
        )
        assert found is not None
        assert found.id == inserted.id
        assert found.model_dump()["idempotency_key"] == inserted.idempotency_key
    assert (
        await history_db.find_platform_message_history_by_idempotency_key(
            "absent", "session", "same-key"
        )
        is None
    )
    assert (
        await history_db.find_platform_message_history_by_idempotency_key(
            "test", "absent", "same-key"
        )
        is None
    )


@pytest.mark.asyncio
async def test_new_history_schema_supports_nullable_indexed_keys(
    history_db: SQLiteDatabase,
) -> None:
    async with history_db.get_db() as session:
        session.add_all([history(None), history(None)])
        await session.commit()
        columns = {
            row[1]: row
            for row in await session.execute(
                text("PRAGMA table_info(platform_message_history)")
            )
        }
        indexes = {
            row[1]: row
            for row in await session.execute(
                text("PRAGMA index_list(platform_message_history)")
            )
        }
        indexed_columns = await session.execute(
            text("PRAGMA index_info(ix_platform_message_history_idempotency_key)")
        )
        assert columns["idempotency_key"][3] == 0
        assert indexes["ix_platform_message_history_idempotency_key"][2] == 0
        assert [row[2] for row in indexed_columns] == ["idempotency_key"]
        assert (
            await session.execute(
                text(
                    "SELECT count(*) FROM platform_message_history "
                    "WHERE idempotency_key IS NULL"
                )
            )
        ).scalar_one() == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", ["original", "checkpoint", "partial", "current"])
async def test_history_migration_preserves_existing_rows_and_can_be_repeated(
    tmp_path: Path, schema: str
) -> None:
    path = tmp_path / "legacy.db"
    extra_columns = {
        "original": "",
        "checkpoint": ", llm_checkpoint_id VARCHAR",
        "partial": ", idempotency_key VARCHAR",
        "current": (
            ", turn_id VARCHAR, context_event_id VARCHAR, "
            "is_active BOOLEAN NOT NULL DEFAULT 1, idempotency_key VARCHAR"
        ),
    }[schema]
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE platform_message_history ("
            "id INTEGER PRIMARY KEY, platform_id TEXT NOT NULL, user_id TEXT NOT NULL, "
            "sender_id TEXT, sender_name TEXT, content JSON NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL"
            f"{extra_columns})"
        )
        connection.execute(
            "INSERT INTO platform_message_history "
            "(id, platform_id, user_id, content, created_at, updated_at) "
            "VALUES (1, 'test', 'legacy', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (json.dumps({"message": ["preserved"]}),),
        )
        if schema == "checkpoint":
            connection.execute(
                "UPDATE platform_message_history SET llm_checkpoint_id = 'old-turn'"
            )
        if schema in {"partial", "current"}:
            connection.execute(
                "UPDATE platform_message_history SET idempotency_key = 'old-key'"
            )
        if schema == "current":
            connection.execute(
                "UPDATE platform_message_history SET turn_id = 'old-turn', "
                "context_event_id = 'old-event', is_active = 0"
            )

    for _ in range(2):
        database = SQLiteDatabase(str(path))
        try:
            await asyncio.gather(database.initialize(), database.initialize())
            async with database.get_db() as session:
                record = await session.get(PlatformMessageHistory, 1)
                assert record is not None
                assert record.content == {"message": ["preserved"]}
                assert record.user_id == "legacy"
                assert record.idempotency_key == (
                    "old-key" if schema in {"partial", "current"} else None
                )
                assert record.turn_id == (
                    "old-turn" if schema in {"checkpoint", "current"} else None
                )
                assert record.context_event_id == (
                    "old-event" if schema == "current" else None
                )
                assert record.is_active is (schema != "current")
                indexes = await session.execute(
                    text("PRAGMA index_list(platform_message_history)")
                )
                assert [row[1] for row in indexes].count(
                    "ix_platform_message_history_idempotency_key"
                ) == 1
        finally:
            await database.engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_key_writes_in_separate_sessions_remain_independent(
    history_db: SQLiteDatabase,
) -> None:
    await history_db.initialize()

    async def persist(user: str) -> int:
        async with history_db.get_db() as session:
            record = history("same-key", user=user)
            session.add(record)
            await session.commit()
            assert record.id is not None
            return record.id

    users = ["alpha", "beta", "gamma"]
    ids = await asyncio.gather(*(persist(user) for user in users))
    assert len(set(ids)) == len(users)
    for user, record_id in zip(users, ids, strict=True):
        found = await history_db.find_platform_message_history_by_idempotency_key(
            "test", user, "same-key"
        )
        assert found is not None and found.id == record_id


@pytest.mark.asyncio
async def test_duplicate_keys_in_one_scope_are_reported_as_ambiguous(
    history_db: SQLiteDatabase,
) -> None:
    async with history_db.get_db() as session:
        session.add_all([history("duplicate"), history("duplicate")])
        await session.commit()
    with pytest.raises(MultipleResultsFound):
        await history_db.find_platform_message_history_by_idempotency_key(
            "test", "session", "duplicate"
        )


@pytest.mark.asyncio
async def test_rolled_back_history_key_is_not_visible(
    history_db: SQLiteDatabase,
) -> None:
    with pytest.raises(RuntimeError, match="abort write"):
        async with history_db.get_db() as session:
            session.add(history("uncommitted"))
            await session.flush()
            raise RuntimeError("abort write")
    assert (
        await history_db.find_platform_message_history_by_idempotency_key(
            "test", "session", "uncommitted"
        )
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["get_base_stats", "get_total_message_count", "get_grouped_base_stats"]
)
async def test_legacy_stats_can_return_real_results_inside_an_active_event_loop(
    history_db: SQLiteDatabase, method: str
) -> None:
    await history_db.insert_platform_stats("first", "test", count=3)
    await history_db.insert_platform_stats("second", "test", count=5)
    with pytest.warns(DeprecationWarning):
        result = getattr(history_db, method)()
    if method == "get_total_message_count":
        assert result == 8
    else:
        assert {item.name: item.count for item in result.platform} == {
            "first": 3,
            "second": 5,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method", ["get_base_stats", "get_total_message_count", "get_grouped_base_stats"]
)
async def test_legacy_stats_propagate_database_errors_to_the_caller(
    history_db: SQLiteDatabase, method: str
) -> None:
    async with history_db.get_db() as session:
        await session.execute(text("DROP TABLE platform_stats"))
        await session.commit()
    with (
        pytest.warns(DeprecationWarning),
        pytest.raises(OperationalError, match="no such table: platform_stats"),
    ):
        getattr(history_db, method)()
