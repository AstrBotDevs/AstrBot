"""Backup round trips preserve linear recovery boundaries and recycled baselines."""

from copy import deepcopy

import pytest

from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter


@pytest.mark.asyncio
async def test_backup_round_trip_keeps_recycled_baseline_distinct_from_empty(database):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "initial"}]
    )
    first = (
        await store.append(
            conv.conversation_id,
            [],
            history=[{"role": "user", "content": "plugin version one"}],
            origin="plugin",
        )
    ).events
    old_id = next(e.event_id for e in first if e.type == "context.rebased")
    await store.append(conv.conversation_id, [], history=[], origin="plugin")
    exported = await AstrBotExporter(database)._export_main_database()
    old = next(e for e in exported["conversation_events"] if e["event_id"] == old_id)
    assert old["payload"] is None
    importer = AstrBotImporter(database)
    await importer._clear_main_db()
    await importer._import_main_database(exported)
    current = await store.read(conv.conversation_id)
    assert current.messages == []
    status = await store.get_context_availability(
        conv.conversation_id, [old_id, current.revision.leaf_event_id, None]
    )
    assert status[old_id] == "pruned"
    assert status[current.revision.leaf_event_id] == "available"
    assert status[None] == "available"


@pytest.mark.asyncio
@pytest.mark.parametrize("baseline", ["missing-baseline", None])
async def test_backup_rejects_missing_historical_baseline(database, baseline):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "old"}]
    )
    await store.append(
        conv.conversation_id,
        [
            {
                "type": "message.appended",
                "payload": {"message": {"role": "assistant", "content": "reply"}},
            }
        ],
    )
    await store.append(conv.conversation_id, [], history=[], origin="user")
    exported = await AstrBotExporter(database)._export_main_database()
    broken = deepcopy(exported)
    message = next(
        e for e in broken["conversation_events"] if e["type"] == "message.appended"
    )
    message["replay_from_event_id"] = baseline
    importer = AstrBotImporter(database)
    await importer._clear_main_db()
    with pytest.raises(ValueError, match="Invalid conversation recovery baseline"):
        await importer._import_main_database(broken)
    assert await store.read(conv.conversation_id) is None
    await importer._import_main_database(exported)
    assert (await store.read(conv.conversation_id)).messages == []
