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
        await database.close()


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
async def test_initialize_does_not_load_all_preferences(tmp_path, monkeypatch):
    database = SQLiteDatabase(str(tmp_path / "preload.db"))
    await database.initialize()

    original_get_preferences = database.get_preferences

    async def fail_on_unfiltered_load(scope=None, scope_id=None, key=None):
        if scope is None and scope_id is None and key is None:
            raise AssertionError("initialize() must not load all preferences")
        return await original_get_preferences(scope, scope_id, key)

    monkeypatch.setattr(database, "get_preferences", fail_on_unfiltered_load)

    store = SharedPreferences(database, tmp_path / "preferences.json")
    try:
        await store.initialize()
        assert store._cache == {}
    finally:
        await store.terminate()
        await database.close()


@pytest.mark.asyncio
async def test_get_async_falls_back_to_database_without_caching(preferences):
    store, database = preferences
    await database.insert_preference_or_update(
        "plugin",
        "heavy_plugin",
        "blob",
        {"val": {"payload": [1, 2, 3]}},
    )

    assert store._cache == {}
    value = await store.get_async("plugin", "heavy_plugin", "blob")
    assert value == {"payload": [1, 2, 3]}
    value["payload"].append(4)
    assert await store.get_async("plugin", "heavy_plugin", "blob") == {
        "payload": [1, 2, 3]
    }
    assert await store.get_async("plugin", "heavy_plugin", "missing", "d") == "d"
    assert store._cache == {}


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
async def test_bounded_write_queue_backpressures_and_persists(tmp_path):
    database = SQLiteDatabase(str(tmp_path / "preferences.db"))
    await database.initialize()
    store = SharedPreferences(database, tmp_path / "preferences.json")
    await store.initialize()
    store._write_queue = asyncio.Queue(maxsize=1)

    resume = asyncio.Event()
    entered = asyncio.Event()
    original_insert = database.insert_preference_or_update

    async def stalled_insert(scope, scope_id, key, value):
        entered.set()
        await resume.wait()
        return await original_insert(scope, scope_id, key, value)

    database.insert_preference_or_update = stalled_insert
    try:
        first = asyncio.create_task(store.put_async("global", "global", "k1", "v1"))
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert not first.done()
        assert await store.get_async("global", "global", "k1") == "v1"

        second = asyncio.create_task(store.put_async("global", "global", "k2", "v2"))
        await asyncio.sleep(0.05)
        assert not second.done()

        resume.set()
        await asyncio.gather(first, second)

        assert await store.get_async("global", "global", "k1") == "v1"
        assert await store.get_async("global", "global", "k2") == "v2"
        persisted_first = await database.get_preference("global", "global", "k1")
        persisted_second = await database.get_preference("global", "global", "k2")
        assert persisted_first is not None
        assert persisted_first.value == {"val": "v1"}
        assert persisted_second is not None
        assert persisted_second.value == {"val": "v2"}
    finally:
        resume.set()
        await store.terminate()
        await database.close()


@pytest.mark.asyncio
async def test_initialize_creates_bounded_write_queue(tmp_path):
    database = SQLiteDatabase(str(tmp_path / "preferences.db"))
    await database.initialize()
    store = SharedPreferences(database, tmp_path / "preferences.json")
    try:
        await store.initialize()
        assert store._write_queue is not None
        assert store._write_queue.maxsize == 1024
    finally:
        await store.terminate()
        await database.close()


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
