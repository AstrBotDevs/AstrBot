"""Tests for runtime-owned shared preferences."""

import asyncio
from unittest.mock import MagicMock

import pytest
import pytest_asyncio

from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.utils.shared_preferences import SharedPreferences


@pytest_asyncio.fixture
async def preferences(tmp_path):
    database = SQLiteDatabase(str(tmp_path / "preferences.db"))
    await database.initialize()
    store = SharedPreferences(database, tmp_path / "preferences.json")
    await store.initialize()
    try:
        yield store, database
    finally:
        await store.terminate()
        await database.engine.dispose()


@pytest.mark.asyncio
async def test_put_updates_cache_and_persists(preferences):
    store, database = preferences

    await store.global_put("theme", "dark")

    assert await store.global_get("theme") == "dark"
    persisted = await database.get_preference("global", "global", "theme")
    assert persisted is not None
    assert persisted.value == {"val": "dark"}


@pytest.mark.asyncio
async def test_remove_and_clear_update_cache_and_persist(preferences):
    store, database = preferences
    await store.put_async("umo", "session", "first", 1)
    await store.put_async("umo", "session", "second", 2)

    await store.remove_async("umo", "session", "first")
    assert await store.get_async("umo", "session", "first") is None

    await store.clear_async("umo", "session")
    assert await store.range_get_async("umo", "session") == []
    assert await database.get_preferences("umo", "session") == []


@pytest.mark.asyncio
async def test_initialize_preloads_values_and_returns_copies(tmp_path):
    database = SQLiteDatabase(str(tmp_path / "preload.db"))
    await database.initialize()
    await database.insert_preference_or_update(
        "umo", "session", "provider", {"val": {"id": "provider-1"}}
    )
    store = SharedPreferences(database, tmp_path / "preferences.json")
    try:
        await store.initialize()
        provider = await store.session_get("session", "provider")
        assert provider == {"id": "provider-1"}
        provider["id"] = "mutated"
        assert await store.session_get("session", "provider") == {"id": "provider-1"}
    finally:
        await store.terminate()
        await database.engine.dispose()


@pytest.mark.asyncio
async def test_flush_preserves_write_order(preferences):
    store, database = preferences

    first = asyncio.create_task(store.global_put("ordered", "first"))
    second = asyncio.create_task(store.global_put("ordered", "second"))
    await asyncio.gather(first, second)
    await store.flush()

    persisted = await database.get_preference("global", "global", "ordered")
    assert persisted is not None
    assert persisted.value == {"val": "second"}


@pytest.mark.asyncio
async def test_terminate_stops_scheduler_thread_once(tmp_path):
    preferences = SharedPreferences(
        db_helper=MagicMock(),
        json_storage_path=str(tmp_path / "preferences.json"),
    )
    scheduler_thread = preferences._scheduler._thread  # noqa: SLF001

    try:
        assert scheduler_thread is not None
        assert scheduler_thread.is_alive()

        await preferences.terminate()
        await preferences.terminate()

        assert scheduler_thread.is_alive() is False
        assert preferences._scheduler.running is False  # noqa: SLF001
    finally:
        await preferences.terminate()
