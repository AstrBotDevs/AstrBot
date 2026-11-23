"""Partially migrated message associations retain data and accept current writes."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError
from sqlmodel import text

from astrbot.core.db.po import PlatformMessageHistory, WebChatThread
from astrbot.core.db.sqlite import SQLiteDatabase


def make_alias_database(path: Path, schema: str) -> None:
    """Build storage with constraints and objects absent from ORM metadata."""
    history_aliases = {
        "legacy": "llm_checkpoint_id TEXT",
        "current": "turn_id TEXT",
        "mixed": "llm_checkpoint_id TEXT, turn_id TEXT",
    }[schema]
    thread_aliases = {
        "legacy": "base_checkpoint_id TEXT NOT NULL REFERENCES event_anchors(id)",
        "current": "base_event_id TEXT NOT NULL REFERENCES event_anchors(id)",
        "mixed": (
            "base_checkpoint_id TEXT NOT NULL REFERENCES event_anchors(id), "
            "base_event_id TEXT"
        ),
    }[schema]
    with sqlite3.connect(path) as connection:
        connection.executescript(
            "CREATE TABLE event_anchors (id TEXT PRIMARY KEY);"
            "INSERT INTO event_anchors VALUES ('old-event'), ('new-event'), ('fresh-event');"
            "CREATE TABLE platform_message_history ("
            "id INTEGER PRIMARY KEY, platform_id TEXT NOT NULL, user_id TEXT NOT NULL, "
            "sender_id TEXT, sender_name TEXT, content JSON NOT NULL, "
            "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
            f"{history_aliases});"
            "CREATE TABLE webchat_threads ("
            "id INTEGER PRIMARY KEY, created_at DATETIME NOT NULL, "
            "updated_at DATETIME NOT NULL, thread_id TEXT NOT NULL UNIQUE, "
            "creator TEXT NOT NULL, parent_session_id TEXT NOT NULL, "
            "parent_message_id INTEGER NOT NULL, selected_text TEXT NOT NULL, "
            "legacy_note TEXT NOT NULL DEFAULT 'keep me', "
            f"{thread_aliases}, CHECK (length(selected_text) > 0));"
            "CREATE UNIQUE INDEX legacy_thread_selection "
            "ON webchat_threads(creator, selected_text);"
            "CREATE INDEX legacy_thread_expression "
            "ON webchat_threads(lower(selected_text)) WHERE creator <> '';"
            "CREATE TABLE thread_audit (thread_id INTEGER NOT NULL);"
            "CREATE TRIGGER legacy_thread_audit AFTER INSERT ON webchat_threads "
            "BEGIN INSERT INTO thread_audit VALUES (NEW.id); END;"
            "CREATE TABLE thread_children (thread_id INTEGER "
            "REFERENCES webchat_threads(id), payload TEXT);"
        )
        history_column = "turn_id" if schema == "current" else "llm_checkpoint_id"
        thread_column = "base_event_id" if schema == "current" else "base_checkpoint_id"
        for record_id in range(1, 4):
            connection.execute(
                "INSERT INTO platform_message_history "
                "(id, platform_id, user_id, content, created_at, updated_at, "
                f"{history_column}) VALUES (?, 'test', 'session', '{{}}', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'old-turn')",
                (record_id,),
            )
            connection.execute(
                "INSERT INTO webchat_threads "
                "(id, thread_id, creator, parent_session_id, parent_message_id, "
                f"selected_text, created_at, updated_at, {thread_column}) "
                "VALUES (?, ?, 'owner', 'parent', 1, ?, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'old-event')",
                (record_id, f"thread-{record_id}", f"selection-{record_id}"),
            )
        connection.execute("INSERT INTO thread_children VALUES (1, 'child survives')")
        if schema == "mixed":
            connection.execute(
                "UPDATE platform_message_history SET turn_id = 'new-turn' WHERE id = 2"
            )
            connection.execute(
                "UPDATE platform_message_history SET turn_id = '' WHERE id = 3"
            )
            connection.execute(
                "UPDATE webchat_threads SET base_event_id = 'new-event' WHERE id = 2"
            )
            connection.execute(
                "UPDATE webchat_threads SET base_event_id = '' WHERE id = 3"
            )


def legacy_schema_objects(path: Path) -> list[tuple[str, str, str]]:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT type, name, sql FROM sqlite_schema "
            "WHERE name LIKE 'legacy_thread_%' ORDER BY name"
        ).fetchall()


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", ["legacy", "current", "mixed"])
async def test_alias_upgrade_preserves_rows_objects_and_public_model(
    tmp_path: Path, schema: str
) -> None:
    path = tmp_path / "aliases.db"
    make_alias_database(path, schema)
    objects_before = legacy_schema_objects(path)
    database = SQLiteDatabase(str(path))
    try:
        for _ in range(2):
            await database.initialize()
        async with database.get_db() as session:
            for record_id in range(1, 4):
                history = await session.get(PlatformMessageHistory, record_id)
                thread = await session.get(WebChatThread, record_id)
                assert history is not None
                assert thread is not None
                assert history.turn_id == (
                    {1: "old-turn", 2: "new-turn", 3: ""}[record_id]
                    if schema == "mixed"
                    else "old-turn"
                )
                assert thread.base_event_id == (
                    {1: "old-event", 2: "new-event", 3: ""}[record_id]
                    if schema == "mixed"
                    else "old-event"
                )
                assert thread.selected_text == f"selection-{record_id}"
                assert "base_checkpoint_id" not in thread.model_dump()
            rows = (
                await session.execute(
                    text("SELECT legacy_note FROM webchat_threads ORDER BY id")
                )
            ).all()
            assert rows == [("keep me",)] * 3
            assert (
                await session.execute(text("SELECT payload FROM thread_children"))
            ).scalar_one() == "child survives"
            assert (
                await session.execute(text("PRAGMA integrity_check"))
            ).scalar_one() == "ok"
            assert not (await session.execute(text("PRAGMA foreign_key_check"))).all()
            if schema == "mixed":
                assert (
                    await session.execute(
                        text("SELECT llm_checkpoint_id FROM platform_message_history")
                    )
                ).scalars().all() == ["old-turn"] * 3
                assert (
                    await session.execute(
                        text("SELECT base_checkpoint_id FROM webchat_threads")
                    )
                ).scalars().all() == ["old-event"] * 3
        assert legacy_schema_objects(path) == objects_before
        assert (
            "base_checkpoint_id" not in WebChatThread.model_json_schema()["properties"]
        )
    finally:
        await database.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("schema", ["legacy", "current", "mixed", "fresh"])
@pytest.mark.parametrize("writer", ["database", "orm", "core"])
async def test_current_thread_writes_support_required_legacy_alias(
    tmp_path: Path, schema: str, writer: str
) -> None:
    path = tmp_path / "write.db"
    if schema != "fresh":
        make_alias_database(path, schema)
    database = SQLiteDatabase(str(path))
    values = {
        "creator": "new-owner",
        "parent_session_id": "new-parent",
        "parent_message_id": 4,
        "base_event_id": "fresh-event",
        "selected_text": "new selection",
    }
    try:
        if writer == "database":
            thread = await database.create_webchat_thread(**values)
            inserted_id = thread.id
        else:
            async with database.get_db() as session:
                if writer == "orm":
                    thread = WebChatThread(**values)
                    session.add(thread)
                    await session.flush()
                    inserted_id = thread.id
                else:
                    result = await session.execute(
                        WebChatThread.__table__.insert().values(**values)
                    )
                    inserted_id = result.inserted_primary_key[0]
                await session.commit()
        assert inserted_id is not None
        async with database.get_db() as session:
            saved = await session.get(WebChatThread, inserted_id)
            assert saved is not None
            assert saved.base_event_id == "fresh-event"
            assert saved.creator == "new-owner"
            assert "base_checkpoint_id" not in saved.model_dump()
            if schema != "fresh":
                assert (
                    await session.execute(
                        text("SELECT count(*) FROM thread_audit WHERE thread_id = :id"),
                        {"id": inserted_id},
                    )
                ).scalar_one() == 1
    finally:
        await database.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "invalid_value", "constraint"),
    [
        ("base_event_id", "unknown-event", "FOREIGN KEY"),
        ("selected_text", "", "CHECK"),
        ("selected_text", "selection-1", "UNIQUE"),
    ],
)
async def test_mixed_alias_upgrade_retains_original_constraints(
    tmp_path: Path, field: str, invalid_value: str, constraint: str
) -> None:
    path = tmp_path / "constraints.db"
    make_alias_database(path, "mixed")
    database = SQLiteDatabase(str(path))
    values = {
        "creator": "owner",
        "parent_session_id": "parent",
        "parent_message_id": 1,
        "base_event_id": "fresh-event",
        "selected_text": "valid selection",
    }
    values[field] = invalid_value
    try:
        with pytest.raises(IntegrityError, match=constraint):
            await database.create_webchat_thread(**values)
    finally:
        await database.engine.dispose()


class MigrationInterrupted(RuntimeError):
    """A deterministic process interruption after an actual DDL operation."""


@contextmanager
def interrupt_after_statement(
    database: SQLiteDatabase, statement_prefix: str
) -> Iterator[None]:
    def after_cursor_execute(
        connection: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        if statement.startswith(statement_prefix):
            raise MigrationInterrupted(statement_prefix)

    event.listen(
        database.engine.sync_engine, "after_cursor_execute", after_cursor_execute
    )
    try:
        yield
    finally:
        event.remove(
            database.engine.sync_engine, "after_cursor_execute", after_cursor_execute
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("schema", "statement", "table", "persisted_column"),
    [
        (
            "legacy",
            "ALTER TABLE platform_message_history RENAME COLUMN llm_checkpoint_id",
            "platform_message_history",
            "turn_id",
        ),
        (
            "legacy",
            "ALTER TABLE webchat_threads ADD COLUMN base_event_id",
            "webchat_threads",
            "base_event_id",
        ),
        (
            "current",
            "ALTER TABLE webchat_threads ADD COLUMN base_checkpoint_id",
            "webchat_threads",
            "base_checkpoint_id",
        ),
    ],
)
async def test_alias_migration_retries_after_persisted_partial_ddl(
    tmp_path: Path,
    schema: str,
    statement: str,
    table: str,
    persisted_column: str,
) -> None:
    path = tmp_path / "interrupted.db"
    make_alias_database(path, schema)
    database = SQLiteDatabase(str(path))
    try:
        with interrupt_after_statement(database, statement):
            with pytest.raises(MigrationInterrupted):
                await database.initialize()
        assert not database.inited
        with sqlite3.connect(path) as connection:
            columns = {
                row[1] for row in connection.execute(f"PRAGMA table_info({table})")
            }
            assert persisted_column in columns
        await database.initialize()
        async with database.get_db() as session:
            history = await session.get(PlatformMessageHistory, 1)
            thread = await session.get(WebChatThread, 1)
            assert history is not None and history.turn_id == "old-turn"
            assert thread is not None and thread.base_event_id == "old-event"
        inserted = await database.create_webchat_thread(
            "new-owner", "parent", 1, "fresh-event", "after recovery"
        )
        assert inserted.id is not None
        assert inserted.base_event_id == "fresh-event"
    finally:
        await database.engine.dispose()
