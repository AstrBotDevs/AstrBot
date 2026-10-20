import asyncio
import time

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
        await store.close()
        await database.engine.dispose()


@pytest.mark.asyncio
async def test_sync_put_updates_cache_and_persists_without_blocking(preferences):
    store, database = preferences

    started = time.monotonic()
    store.put("theme", "dark", scope="global", scope_id="global")

    assert time.monotonic() - started < 0.1
    assert store.get("theme", scope="global", scope_id="global") == "dark"

    await store.flush()
    persisted = await database.get_preference("global", "global", "theme")
    assert persisted is not None
    assert persisted.value == {"val": "dark"}


@pytest.mark.asyncio
async def test_async_put_waits_for_persistence(preferences):
    store, database = preferences

    await store.put_async("global", "global", "theme", "dark")

    persisted = await database.get_preference("global", "global", "theme")
    assert persisted is not None
    assert persisted.value == {"val": "dark"}


@pytest.mark.asyncio
async def test_sync_get_does_not_wait_for_an_exhausted_connection_pool(preferences):
    store, database = preferences
    pool = database.engine.pool
    capacity = pool.size() + pool._max_overflow
    connections = [await database.engine.connect() for _ in range(capacity)]
    released = asyncio.Event()

    async def release_connection():
        await asyncio.sleep(0.01)
        await connections.pop().close()
        released.set()

    release_task = asyncio.create_task(release_connection())
    try:
        assert (
            store.get(
                "missing",
                "default",
                scope="global",
                scope_id="global",
            )
            == "default"
        )
        await asyncio.wait_for(released.wait(), timeout=0.5)
    finally:
        await release_task
        for connection in connections:
            await connection.close()


@pytest.mark.asyncio
async def test_sync_writes_from_worker_threads_keep_fifo_order(preferences):
    store, database = preferences

    await asyncio.to_thread(
        store.put,
        "ordered",
        "first",
        "global",
        "global",
    )
    await asyncio.to_thread(
        store.put,
        "ordered",
        "second",
        "global",
        "global",
    )
    await store.flush()

    assert store.get("ordered", scope="global", scope_id="global") == "second"
    persisted = await database.get_preference("global", "global", "ordered")
    assert persisted is not None
    assert persisted.value == {"val": "second"}


@pytest.mark.asyncio
async def test_concurrent_sync_writes_keep_submission_order(
    preferences,
    monkeypatch,
):
    store, database = preferences
    original_schedule_write = store._schedule_write

    def delay_first_write(operation):
        if operation[4] == "first":
            time.sleep(0.05)
        original_schedule_write(operation)

    monkeypatch.setattr(store, "_schedule_write", delay_first_write)

    first = asyncio.create_task(
        asyncio.to_thread(
            store.put,
            "ordered",
            "first",
            "global",
            "global",
        )
    )
    await asyncio.sleep(0.01)
    second = asyncio.create_task(
        asyncio.to_thread(
            store.put,
            "ordered",
            "second",
            "global",
            "global",
        )
    )
    await asyncio.gather(first, second)
    await store.flush()

    persisted = await database.get_preference("global", "global", "ordered")
    assert persisted is not None
    assert persisted.value == {"val": "second"}


@pytest.mark.asyncio
async def test_initialize_does_not_load_all_preferences(tmp_path, monkeypatch):
    """Startup must not materialize the whole preferences table in memory."""
    database = SQLiteDatabase(str(tmp_path / "preload.db"))
    await database.initialize()

    def fail_on_unfiltered_load(scope=None, scope_id=None, key=None):
        if scope is None and scope_id is None and key is None:
            raise AssertionError("initialize() must not load all preferences")
        return original_get_preferences(scope, scope_id, key)

    original_get_preferences = database.get_preferences
    monkeypatch.setattr(database, "get_preferences", fail_on_unfiltered_load)

    store = SharedPreferences(database, tmp_path / "preferences.json")
    try:
        await store.initialize()
        assert store._cache == {}
    finally:
        await store.close()
        await database.engine.dispose()


@pytest.mark.asyncio
async def test_sync_reads_fall_back_to_database_without_preload(tmp_path):
    """Deprecated sync get() must read historical values written before startup."""
    database = SQLiteDatabase(str(tmp_path / "fallback.db"))
    await database.initialize()
    await database.insert_preference_or_update(
        "umo",
        "session",
        "provider",
        {"val": "provider-1"},
    )
    store = SharedPreferences(database, tmp_path / "preferences.json")
    try:
        await store.initialize()
        assert store._cache == {}
        assert store.get("provider", scope="umo", scope_id="session") == "provider-1"
        # Sync fallback reads must not backfill the in-memory overlay.
        assert store._cache == {}
    finally:
        await store.close()
        await database.engine.dispose()


@pytest.mark.asyncio
async def test_sync_range_reads_historical_and_process_local_values(tmp_path):
    """Deprecated range_get() must combine persisted and pending values."""
    database = SQLiteDatabase(str(tmp_path / "range-fallback.db"))
    await database.initialize()
    await database.insert_preference_or_update(
        "plugin",
        "example",
        "historical",
        {"val": "from-database"},
    )
    store = SharedPreferences(database, tmp_path / "preferences.json")
    try:
        await store.initialize()
        store.put(
            "pending",
            "from-overlay",
            scope="plugin",
            scope_id="example",
        )

        preferences = store.range_get("plugin", "example")
        values = {item.key: item.value["val"] for item in preferences}

        assert values == {
            "historical": "from-database",
            "pending": "from-overlay",
        }
        assert "historical" not in {cache_key for _, _, cache_key in store._cache}
    finally:
        await store.close()
        await database.engine.dispose()


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
    assert await store.get_async("plugin", "heavy_plugin", "missing", "d") == "d"
    # Reads must not grow the in-memory overlay.
    assert store._cache == {}


@pytest.mark.asyncio
async def test_sync_get_reads_persisted_value_with_exhausted_pool(preferences):
    """Sync reads must not depend on the async connection pool."""
    store, database = preferences
    await database.insert_preference_or_update(
        "global",
        "global",
        "inactivated_llm_tools",
        {"val": ["tool-a"]},
    )

    pool = database.engine.pool
    capacity = pool.size() + pool._max_overflow
    connections = [await database.engine.connect() for _ in range(capacity)]
    try:
        assert store.get(
            "inactivated_llm_tools", scope="global", scope_id="global"
        ) == ["tool-a"]
    finally:
        for connection in connections:
            await connection.close()
