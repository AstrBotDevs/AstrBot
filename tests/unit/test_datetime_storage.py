"""Regression coverage for the existing SQLite datetime representation."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import Column, DateTime, MetaData, create_engine, literal, select
from sqlmodel import SQLModel

import astrbot.core.db.sqlite as sqlite_module
from astrbot.core.db.po import (
    ConversationV2,
    PlatformMessageHistory,
    PlatformStat,
)
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.db.vec_db.faiss_impl.document_storage import BaseDocModel, Document
from astrbot.core.knowledge_base.models import BaseKBModel, KnowledgeBase


@pytest.mark.parametrize(
    "metadata",
    [SQLModel.metadata, BaseKBModel.metadata, BaseDocModel.metadata],
    ids=["main", "knowledge-base", "documents"],
)
@pytest.mark.parametrize(
    "value",
    [
        None,
        datetime(2024, 1, 2, 3, 4, 5, 123456),
        datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc),
        datetime(2024, 1, 2, 3, 4, 5, 123456, tzinfo=timezone(timedelta(hours=8))),
    ],
    ids=["null", "naive", "utc", "non-utc"],
)
def test_datetime_columns_preserve_wall_time(
    metadata: MetaData, value: datetime | None
):
    """Exercise each datetime column's SQLite bind and result processing.

    Args:
        metadata: One of AstrBot's three database model registries.
        value: An input accepted by the existing datetime storage contract.
    """
    columns = [
        column
        for table in metadata.tables.values()
        for column in table.columns
        if isinstance(column.type, DateTime)
        or isinstance(getattr(column.type, "impl", None), DateTime)
    ]
    assert columns
    expected = value.replace(tzinfo=None) if value is not None else None
    engine = create_engine("sqlite://")
    try:
        with engine.connect() as connection:
            for column in columns:
                # SQLite historically stores the wall time without an offset.
                result = connection.scalar(select(literal(value, type_=column.type)))
                assert result == expected, str(column)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "column",
    [
        PlatformStat.__table__.c.timestamp,
        ConversationV2.__table__.c.created_at,
        KnowledgeBase.__table__.c.created_at,
        Document.__table__.c.created_at,
    ],
    ids=["statistics", "inherited-timestamp", "knowledge-base", "documents"],
)
def test_existing_datetime_rows_keep_naive_reads_and_filters(
    tmp_path: Path, column: Column
):
    """Read legacy DATETIME values without changing their timezone or filtering.

    Args:
        tmp_path: Temporary directory for the pre-existing database file.
        column: A production model column used to read the legacy values.
    """
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    timestamp = datetime(2024, 1, 2, 3, 4, 5, 123456)
    try:
        with engine.begin() as connection:
            # Create the old schema independently of the current model metadata.
            connection.exec_driver_sql(
                f'CREATE TABLE "{column.table.name}" ("{column.name}" DATETIME)'
            )
            connection.exec_driver_sql(
                f'INSERT INTO "{column.table.name}" ("{column.name}") VALUES (?)',
                (timestamp.isoformat(sep=" "),),
            )
        with engine.connect() as connection:
            result = connection.execute(
                select(column).where(column >= timestamp)
            ).scalar_one()
            assert result == timestamp
            assert result.isoformat() == "2024-01-02T03:04:05.123456"
    finally:
        engine.dispose()


@pytest.mark.asyncio
async def test_delete_platform_message_offset_compares_in_utc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """The history cutoff must match the UTC wall time stored in created_at.

    Args:
        tmp_path: Temporary directory for the database file.
        monkeypatch: Fixture used to simulate a host in a non-UTC timezone.
    """
    now_utc = datetime.now(timezone.utc)
    inside_window = (now_utc - timedelta(hours=20)).replace(tzinfo=None)
    outside_window = (now_utc - timedelta(hours=30)).replace(tzinfo=None)

    db = SQLiteDatabase(str(tmp_path / "history.db"))
    await db.initialize()
    try:
        async with db.get_db() as session:
            async with session.begin():
                for created_at in (inside_window, outside_window):
                    session.add(
                        PlatformMessageHistory(
                            platform_id="p1",
                            user_id="u1",
                            content={},
                            created_at=created_at,
                        )
                    )

        class LocalTime(datetime):
            """Simulate a host whose local timezone is UTC+8."""

            @classmethod
            def now(cls, tz=None):
                if tz is None:
                    return now_utc.replace(tzinfo=None) + timedelta(hours=8)
                return now_utc.astimezone(tz)

        monkeypatch.setattr(sqlite_module, "datetime", LocalTime)
        await db.delete_platform_message_offset("p1", "u1", offset_sec=86400)

        rows = await db.get_platform_message_history("p1", "u1")
        assert [row.created_at for row in rows] == [outside_window]
    finally:
        await db.engine.dispose()
