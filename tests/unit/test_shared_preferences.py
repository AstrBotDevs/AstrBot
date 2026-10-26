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


@pytest.mark.asyncio
@pytest.mark.parametrize("cached", [False, True], ids=["historical", "cached"])
async def test_sync_remove_hides_values_before_persistence(preferences, cached):
    store, database = preferences
    if cached:
        await store.put_async("plugin", "example", "token", "old-token")
    else:
        await database.insert_preference_or_update(
            "plugin", "example", "token", {"val": "old-token"}
        )

    store.remove("token", scope="plugin", scope_id="example")

    # No event-loop yield: the queued deletion cannot have reached SQLite yet.
    assert (
        store.get("token", "missing", scope="plugin", scope_id="example") == "missing"
    )
    assert store.range_get("plugin", "example") == []
    await store.flush()
    assert await database.get_preference("plugin", "example", "token") is None


@pytest.mark.asyncio
async def test_sync_clear_hides_only_the_target_scope_before_persistence(preferences):
    store, database = preferences
    await database.insert_preference_or_update(
        "plugin", "example", "historical", {"val": "old"}
    )
    await store.put_async("plugin", "example", "cached", "old")
    await database.insert_preference_or_update(
        "plugin", "other", "historical", {"val": "keep-other-id"}
    )
    await database.insert_preference_or_update(
        "other", "example", "historical", {"val": "keep-other-scope"}
    )

    store.clear("plugin", "example")

    for key in ("historical", "cached"):
        assert (
            store.get(key, "missing", scope="plugin", scope_id="example") == "missing"
        )
    assert store.range_get("plugin", "example") == []
    assert [item.scope_id for item in store.range_get("plugin")] == ["other"]
    assert (
        store.get("historical", scope="other", scope_id="example") == "keep-other-scope"
    )
    await store.flush()
    assert await store.range_get_async("plugin", "example") == []


@pytest.mark.asyncio
async def test_sync_clear_then_put_keeps_only_new_values_visible(preferences):
    store, database = preferences
    await database.insert_preference_or_update(
        "plugin", "example", "historical", {"val": "old"}
    )
    await store.put_async("plugin", "example", "replaced", "old")

    store.clear("plugin", "example")
    store.put("replaced", "new", scope="plugin", scope_id="example")
    store.put("added", "new", scope="plugin", scope_id="example")

    assert (
        store.get("historical", "missing", scope="plugin", scope_id="example")
        == "missing"
    )
    assert {
        item.key: item.value["val"] for item in store.range_get("plugin", "example")
    } == {
        "replaced": "new",
        "added": "new",
    }
    assert [item.key for item in store.range_get("plugin", key="replaced")] == [
        "replaced"
    ]
    await store.flush()
    assert {item.key for item in await store.range_get_async("plugin", "example")} == {
        "replaced",
        "added",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["remove", "clear"])
async def test_earlier_deletion_does_not_unmask_a_later_pending_deletion(
    preferences, monkeypatch, action
):
    store, database = preferences
    await database.insert_preference_or_update(
        "plugin", "example", "token", {"val": "original"}
    )
    entered = asyncio.Event()
    release = asyncio.Event()
    method_name = "remove_preference" if action == "remove" else "clear_preferences"
    original_delete = getattr(database, method_name)
    calls = 0

    async def pause_second_deletion(*args):
        nonlocal calls
        calls += 1
        if calls == 2:
            entered.set()
            await release.wait()
        await original_delete(*args)

    monkeypatch.setattr(database, method_name, pause_second_deletion)
    if action == "remove":
        store.remove("token", scope="plugin", scope_id="example")
    else:
        store.clear("plugin", "example")
    store.put("token", "intermediate", scope="plugin", scope_id="example")
    if action == "remove":
        store.remove("token", scope="plugin", scope_id="example")
    else:
        store.clear("plugin", "example")

    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        # The first deletion and intervening put are committed; the second is pending.
        persisted = await database.get_preference("plugin", "example", "token")
        assert persisted.value == {"val": "intermediate"}
        assert (
            store.get("token", "missing", scope="plugin", scope_id="example")
            == "missing"
        )
        assert store.range_get("plugin", "example") == []
        assert (
            await store.get_async("plugin", "example", "token", "missing") == "missing"
        )
    finally:
        release.set()
        await store.flush()
    assert await database.get_preference("plugin", "example", "token") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["remove", "clear"])
async def test_put_none_after_deletion_remains_distinct_from_missing(
    preferences, action
):
    store, database = preferences
    await database.insert_preference_or_update(
        "plugin", "example", "token", {"val": "old"}
    )
    if action == "remove":
        store.remove("token", scope="plugin", scope_id="example")
    else:
        store.clear("plugin", "example")
    store.put("token", None, scope="plugin", scope_id="example")

    assert await store.get_async("plugin", "example", "token", "missing") is None
    assert {
        item.key: item.value["val"] for item in store.range_get("plugin", "example")
    } == {"token": None}
    await store.flush()
    persisted = await database.get_preference("plugin", "example", "token")
    assert persisted.value == {"val": None}


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["remove", "clear"])
async def test_completed_deletion_preserves_on_demand_database_reads(
    preferences, action
):
    store, database = preferences
    await database.insert_preference_or_update(
        "plugin", "example", "token", {"val": "old"}
    )
    if action == "remove":
        store.remove("token", scope="plugin", scope_id="example")
    else:
        store.clear("plugin", "example")
    await store.flush()
    await database.insert_preference_or_update(
        "plugin", "example", "token", {"val": "fresh-from-database"}
    )

    assert (
        store.get("token", scope="plugin", scope_id="example") == "fresh-from-database"
    )
    assert await store.get_async("plugin", "example", "token") == "fresh-from-database"
    assert {item.key for item in store.range_get("plugin", "example")} == {"token"}


@pytest.mark.asyncio
async def test_range_overlay_preserves_persisted_record_metadata(preferences):
    store, database = preferences
    await store.put_async("plugin", "example", "token", "persisted")
    persisted = await database.get_preference("plugin", "example", "token")

    result = await store.range_get_async("plugin", "example")

    assert len(result) == 1
    assert result[0].id == persisted.id
    assert result[0].created_at == persisted.created_at
    assert result[0].updated_at == persisted.updated_at
    assert result[0].value == persisted.value


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["remove", "clear"])
async def test_deletion_before_initialization_is_replayed(
    preferences, tmp_path, action
):
    _, database = preferences
    await database.insert_preference_or_update(
        "plugin", "example", "token", {"val": "old-token"}
    )
    store = SharedPreferences(database, tmp_path / "deferred.json")
    try:
        if action == "remove":
            store.remove("token", scope="plugin", scope_id="example")
        else:
            store.clear("plugin", "example")
        assert (
            store.get("token", "missing", scope="plugin", scope_id="example")
            == "missing"
        )
        await store.initialize()
        assert await database.get_preference("plugin", "example", "token") is None
        await database.insert_preference_or_update(
            "plugin", "example", "token", {"val": "fresh-from-database"}
        )
        assert (
            await store.get_async("plugin", "example", "token") == "fresh-from-database"
        )
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_concurrent_conversation_lookup_cannot_restore_a_deleted_selection(
    preferences, monkeypatch
):
    from astrbot.core import conversation_mgr

    store, database = preferences
    monkeypatch.setattr(conversation_mgr, "sp", store)
    manager = conversation_mgr.ConversationManager(database)
    umo = "test:GroupMessage:room"
    cid = await manager.new_conversation(umo)
    entered = asyncio.Event()
    release = asyncio.Event()
    original_remove = database.remove_preference

    async def pause_selection_deletion(*args):
        entered.set()
        await release.wait()
        await original_remove(*args)

    monkeypatch.setattr(database, "remove_preference", pause_selection_deletion)
    deletion = asyncio.create_task(manager.delete_conversation(umo))
    try:
        await asyncio.wait_for(entered.wait(), timeout=3)
        assert await database.get_conversation_by_id(cid) is None
        assert await manager.get_curr_conversation_id(umo) is None
    finally:
        release.set()
        await deletion

    assert await manager.get_curr_conversation_id(umo) is None
    assert await database.get_preference("umo", umo, "sel_conv_id") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["remove", "clear"])
@pytest.mark.parametrize("asynchronous", [False, True], ids=["sync", "async"])
async def test_failed_deletion_keeps_old_values_hidden_until_a_successful_retry(
    preferences, monkeypatch, action, asynchronous
):
    store, database = preferences
    await store.put_async("plugin", "example", "token", "old-token")
    method_name = "remove_preference" if action == "remove" else "clear_preferences"
    original_delete = getattr(database, method_name)

    async def fail_deletion(*args):
        raise OSError("database unavailable")

    monkeypatch.setattr(database, method_name, fail_deletion)
    if asynchronous:
        with pytest.raises(OSError, match="database unavailable"):
            if action == "remove":
                await store.remove_async("plugin", "example", "token")
            else:
                await store.clear_async("plugin", "example")
    elif action == "remove":
        store.remove("token", scope="plugin", scope_id="example")
    else:
        store.clear("plugin", "example")
    await store.flush()

    persisted = await database.get_preference("plugin", "example", "token")
    assert persisted.value == {"val": "old-token"}
    assert (
        store.get("token", "missing", scope="plugin", scope_id="example") == "missing"
    )
    assert await store.get_async("plugin", "example", "token", "missing") == "missing"
    assert store.range_get("plugin", "example") == []
    assert await store.range_get_async("plugin", "example") == []

    await store.put_async("plugin", "example", "token", "replacement")
    assert await store.get_async("plugin", "example", "token") == "replacement"
    assert {
        item.key: item.value["val"] for item in store.range_get("plugin", "example")
    } == {"token": "replacement"}
    assert {
        item.key: item.value["val"]
        for item in await store.range_get_async("plugin", "example")
    } == {"token": "replacement"}

    monkeypatch.setattr(database, method_name, original_delete)
    if action == "remove":
        await store.remove_async("plugin", "example", "token")
    else:
        await store.clear_async("plugin", "example")
    assert await database.get_preference("plugin", "example", "token") is None
    await database.insert_preference_or_update(
        "plugin", "example", "token", {"val": "fresh-from-database"}
    )
    assert await store.get_async("plugin", "example", "token") == "fresh-from-database"
