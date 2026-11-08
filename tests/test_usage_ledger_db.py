import sqlite3
from contextlib import closing

import pytest
from sqlmodel import select

from astrbot.core.db.po import ProviderStat
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_old_stats_migrate_without_changing_old_rows(tmp_path):
    path = tmp_path / "old.db"
    with closing(sqlite3.connect(path)) as conn, conn:
        conn.execute(
            "CREATE TABLE provider_stats ("
            "id INTEGER PRIMARY KEY, created_at DATETIME, updated_at DATETIME, "
            "agent_type VARCHAR NOT NULL, status VARCHAR NOT NULL, umo VARCHAR NOT NULL, "
            "conversation_id VARCHAR, provider_id VARCHAR NOT NULL, provider_model VARCHAR, "
            "token_input_other INTEGER NOT NULL, token_input_cached INTEGER NOT NULL, "
            "token_output INTEGER NOT NULL, start_time FLOAT NOT NULL, end_time FLOAT NOT NULL, "
            "time_to_first_token FLOAT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO provider_stats VALUES "
            "(1,'2026-01-01','2026-01-01','provider','completed',"
            "'provider:old:sdk',NULL,'old','model',7,2,3,1,2,0)"
        )
    db = SQLiteDatabase(str(path))
    try:
        await db.initialize()
        await db.initialize()
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(
                "INSERT INTO provider_stats "
                "(created_at, updated_at, agent_type, status, umo, provider_id, "
                "token_input_other, token_input_cached, token_output, start_time, "
                "end_time, time_to_first_token) VALUES "
                "('2026-01-02','2026-01-02','provider','completed',"
                "'provider:old:plugin','old',2,0,1,3,4,0)"
            )
        async with db.get_db() as session:
            rows = (
                (await session.execute(select(ProviderStat).order_by(ProviderStat.id)))
                .scalars()
                .all()
            )
            old = rows[0]
            assert len(rows) == 2
            assert old.token_input_other == 7
            assert old.token_input_cached == 2
            assert old.token_output == 3
            assert old.stat_version == 0
            assert old.request_id is None
            assert rows[1].stat_version == 0
    finally:
        await db.engine.dispose()


@pytest.mark.asyncio
async def test_request_id_is_idempotent_and_nullable_for_legacy(temp_db):
    await temp_db.initialize()
    kwargs = {
        "umo": "qq:GroupMessage:7",
        "provider_id": "source/model",
        "stats": {
            "request_id": "request-1",
            "session_umo": "qq:GroupMessage:7",
            "source_id": "source",
            "usage_status": "reported",
            "stat_version": 1,
            "token_usage": {"input_other": 5, "input_cached": 1, "output": 2},
        },
    }
    first = await temp_db.insert_provider_stat(**kwargs)
    second = await temp_db.insert_provider_stat(**kwargs)
    assert first.id == second.id
    async with temp_db.get_db() as session:
        records = (await session.execute(select(ProviderStat))).scalars().all()
        assert len(records) == 1
        assert records[0].source_id == "source"
        assert records[0].stat_version == 1


@pytest.mark.asyncio
async def test_fresh_database_accepts_old_insert_columns(temp_db):
    await temp_db.initialize()
    with closing(sqlite3.connect(temp_db.db_path)) as conn, conn:
        conn.execute(
            "INSERT INTO provider_stats "
            "(created_at, updated_at, agent_type, status, umo, provider_id, "
            "token_input_other, token_input_cached, token_output, start_time, "
            "end_time, time_to_first_token) VALUES "
            "('2026-01-01','2026-01-01','provider','completed',"
            "'provider:legacy:sdk','legacy',3,1,2,1,2,0)"
        )
    async with temp_db.get_db() as session:
        row = (await session.execute(select(ProviderStat))).scalar_one()
        assert row.stat_version == 0
        assert row.token_input_other == 3
