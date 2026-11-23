"""Backup imports preserve canonical association values across legacy aliases."""

import json
import sqlite3
import zipfile
from collections.abc import AsyncIterator
from copy import deepcopy
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.exc import StatementError
from sqlmodel import select, text

from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.config.default import VERSION
from astrbot.core.db.po import PlatformMessageHistory, WebChatThread
from astrbot.core.db.sqlite import SQLiteDatabase


def association_backup(
    aliases: dict[str, object], record_id: int = 1
) -> dict[str, list[dict[str, object]]]:
    """Build one message and one thread using the requested backup keys."""
    data = {
        "platform_message_history": [
            {
                "id": record_id,
                "platform_id": "test-platform",
                "user_id": "owner",
                "content": {"text": "saved message"},
            }
        ],
        "webchat_threads": [
            {
                "id": record_id,
                "thread_id": f"thread-{record_id}",
                "creator": "owner",
                "parent_session_id": "parent-session",
                "parent_message_id": record_id,
                "selected_text": "saved selection",
            }
        ],
    }
    for table, canonical, legacy in (
        ("platform_message_history", "turn_id", "llm_checkpoint_id"),
        ("webchat_threads", "base_event_id", "base_checkpoint_id"),
    ):
        names = {"canonical": canonical, "legacy": legacy}
        data[table][0].update({names[key]: value for key, value in aliases.items()})
    return data


@pytest_asyncio.fixture(params=["fresh", "legacy-required"])
async def alias_target(tmp_path: Path, request) -> AsyncIterator[SQLiteDatabase]:
    """Include a restored database whose old thread column remains required."""
    path = tmp_path / "target.db"
    if request.param == "legacy-required":
        with sqlite3.connect(path) as connection:
            connection.executescript(
                "CREATE TABLE platform_message_history ("
                "id INTEGER PRIMARY KEY, platform_id TEXT NOT NULL, "
                "user_id TEXT NOT NULL, sender_id TEXT, sender_name TEXT, "
                "content JSON NOT NULL, llm_checkpoint_id TEXT, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);"
                "CREATE TABLE webchat_threads ("
                "id INTEGER PRIMARY KEY, thread_id TEXT NOT NULL UNIQUE, "
                "creator TEXT NOT NULL, parent_session_id TEXT NOT NULL, "
                "parent_message_id INTEGER NOT NULL, "
                "base_checkpoint_id TEXT NOT NULL, selected_text TEXT NOT NULL, "
                "created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL);"
            )
    database = SQLiteDatabase(str(path))
    try:
        await database.initialize()
        yield database
    finally:
        await database.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("aliases", "expected"),
    [
        pytest.param({"legacy": "old-value"}, "old-value", id="legacy"),
        pytest.param({"legacy": ""}, "", id="legacy-empty"),
        pytest.param({"canonical": "new-value"}, "new-value", id="current"),
        pytest.param({"canonical": ""}, "", id="current-empty"),
        pytest.param(
            {"canonical": "new-value", "legacy": "old-value"},
            "new-value",
            id="mixed-conflict",
        ),
        pytest.param({"canonical": "", "legacy": "old-value"}, "", id="mixed-empty"),
        pytest.param(
            {"canonical": None, "legacy": "old-value"},
            "old-value",
            id="mixed-canonical-null",
        ),
        pytest.param({"canonical": None, "legacy": ""}, "", id="mixed-null-to-empty"),
        pytest.param(
            {"canonical": "new-value", "legacy": None},
            "new-value",
            id="mixed-legacy-null",
        ),
        pytest.param(
            {"canonical": "", "legacy": None}, "", id="mixed-empty-legacy-null"
        ),
    ],
)
async def test_import_alias_precedence_reaches_storage_and_export(
    alias_target: SQLiteDatabase, aliases: dict[str, object], expected: str
) -> None:
    data = association_backup(aliases)
    original = deepcopy(data)
    imported = await AstrBotImporter(alias_target)._import_main_database(data)
    assert imported == dict.fromkeys(data, 1)
    assert data == original
    async with alias_target.get_db() as session:
        history = (await session.execute(select(PlatformMessageHistory))).scalar_one()
        thread = (await session.execute(select(WebChatThread))).scalar_one()
        assert history.turn_id == thread.base_event_id == expected
        stored_alias = await session.scalar(
            text("SELECT base_checkpoint_id FROM webchat_threads WHERE id = 1")
        )
        assert stored_alias == expected
    exported = await AstrBotExporter(alias_target)._export_main_database()
    assert exported["platform_message_history"][0]["turn_id"] == expected
    assert exported["webchat_threads"][0]["base_event_id"] == expected
    assert "llm_checkpoint_id" not in exported["platform_message_history"][0]
    assert "base_checkpoint_id" not in exported["webchat_threads"][0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "aliases",
    [{}, {"canonical": None}, {"legacy": None}, {"canonical": None, "legacy": None}],
    ids=["missing", "current-null", "legacy-null", "both-null"],
)
async def test_import_history_keeps_optional_null_association(
    database: SQLiteDatabase, aliases: dict[str, object]
) -> None:
    data = {
        "platform_message_history": association_backup(aliases)[
            "platform_message_history"
        ]
    }
    imported = await AstrBotImporter(database)._import_main_database(data)
    assert imported == {"platform_message_history": 1}
    async with database.get_db() as session:
        restored = (await session.execute(select(PlatformMessageHistory))).scalar_one()
        assert restored.turn_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("table", "aliases"),
    [
        pytest.param("webchat_threads", {}, id="missing-required"),
        pytest.param("webchat_threads", {"canonical": None}, id="current-null"),
        pytest.param("webchat_threads", {"legacy": None}, id="legacy-null"),
        pytest.param(
            "webchat_threads", {"canonical": None, "legacy": None}, id="both-null"
        ),
        pytest.param(
            "webchat_threads",
            {"canonical": {}, "legacy": "old-value"},
            id="invalid-current-thread",
        ),
        pytest.param(
            "platform_message_history",
            {"canonical": {}, "legacy": "old-value"},
            id="invalid-current-history",
        ),
    ],
)
async def test_invalid_alias_import_rolls_back_without_using_legacy_to_hide_error(
    database: SQLiteDatabase, table: str, aliases: dict[str, object]
) -> None:
    importer = AstrBotImporter(database)
    await importer._import_main_database(
        association_backup({"canonical": "existing"}, 99)
    )
    data = association_backup({"canonical": "valid"})
    data[table].append(association_backup(aliases, 2)[table][0])
    original = deepcopy(data)
    with pytest.raises(StatementError):
        await importer._import_main_database(data)
    assert data == original
    async with database.get_db() as session:
        for model in (PlatformMessageHistory, WebChatThread):
            restored = (await session.execute(select(model))).scalars().all()
            assert [record.id for record in restored] == [99]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("aliases", "expected"),
    [
        pytest.param({"legacy": "old-value"}, "old-value", id="legacy"),
        pytest.param({"canonical": "new-value"}, "new-value", id="current"),
        pytest.param({"canonical": "", "legacy": "old-value"}, "", id="mixed-empty"),
    ],
)
async def test_archive_replace_preserves_alias_counts_cleanup_and_round_trip(
    alias_target: SQLiteDatabase,
    tmp_path: Path,
    aliases: dict[str, object],
    expected: str,
) -> None:
    importer = AstrBotImporter(alias_target)
    await importer._import_main_database(association_backup({"canonical": "stale"}, 99))
    path = tmp_path / "backup.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"astrbot_version": VERSION}))
        archive.writestr(
            "databases/main_db.json", json.dumps(association_backup(aliases))
        )
    result = await importer.import_all(str(path))
    assert result.success, result.errors
    assert result.imported_tables == {
        "platform_message_history": 1,
        "webchat_threads": 1,
    }
    exported = await AstrBotExporter(alias_target)._export_main_database()
    for table, canonical in (
        ("platform_message_history", "turn_id"),
        ("webchat_threads", "base_event_id"),
    ):
        assert [row["id"] for row in exported[table]] == [1]
        assert exported[table][0][canonical] == expected
    await importer._clear_main_db()
    await importer._import_main_database(exported)
    assert await AstrBotExporter(alias_target)._export_main_database() == exported
