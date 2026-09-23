"""Backup round trips preserve linear recovery boundaries and recycled baselines."""

from copy import deepcopy

import pytest
import pytest_asyncio

from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "backup.db"))
    await db.initialize()
    yield db
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_backup_round_trip_keeps_recycled_baseline_distinct_from_empty(database):
    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "initial"}]
    )
    first = await store.append(
        conv.conversation_id,
        [],
        history=[{"role": "user", "content": "plugin version one"}],
        origin="plugin",
    )
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
        conv.conversation_id, [old_id, current.conversation.leaf_event_id, None]
    )
    assert status[old_id] == "pruned"
    assert status[current.conversation.leaf_event_id] == "available"
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


@pytest.mark.asyncio
async def test_legacy_tree_backup_preserves_both_versions_and_independent_side(
    database,
):
    data = {
        "conversations_v3": [
            {
                "id": 1,
                "conversation_id": "main",
                "platform_id": "p",
                "umo": "owner",
                "head_seq": 4,
                "leaf_event_id": "edited",
                "replay_from_event_id": None,
            },
            {
                "id": 2,
                "conversation_id": "side",
                "platform_id": "p",
                "umo": "owner",
                "head_seq": 1,
                "leaf_event_id": "original",
                "replay_from_event_id": None,
            },
        ],
        "conversation_events": [
            {
                "conversation_ref": 1,
                "seq": 1,
                "event_id": "created-main",
                "parent_event_id": None,
                "type": "conversation.created",
                "version": 1,
                "payload": {"umo": "owner", "platform_id": "p"},
            },
            {
                "conversation_ref": 1,
                "seq": 2,
                "event_id": "question",
                "parent_event_id": None,
                "type": "message.appended",
                "version": 1,
                "payload": {"message": {"role": "user", "content": "question"}},
            },
            {
                "conversation_ref": 1,
                "seq": 3,
                "event_id": "original",
                "parent_event_id": "question",
                "type": "message.appended",
                "version": 1,
                "payload": {
                    "message": {"role": "assistant", "content": "original answer"}
                },
            },
            {
                "conversation_ref": 1,
                "seq": 4,
                "event_id": "edited",
                "parent_event_id": "question",
                "type": "message.appended",
                "version": 1,
                "payload": {
                    "message": {"role": "assistant", "content": "edited answer"}
                },
            },
            {
                "conversation_ref": 2,
                "seq": 1,
                "event_id": "created-side",
                "parent_event_id": None,
                "type": "conversation.created",
                "version": 1,
                "payload": {
                    "umo": "owner",
                    "platform_id": "p",
                    "forked_from_event_id": "original",
                },
            },
        ],
    }
    unchanged = deepcopy(data)
    await AstrBotImporter(database)._import_main_database(data)
    assert data == unchanged
    store = database.conversation_store
    assert [m["content"] for m in (await store.read("main")).messages] == [
        "question",
        "edited answer",
    ]
    assert [m["content"] for m in (await store.read("side")).messages] == [
        "question",
        "original answer",
    ]
    old = await store.create(umo="owner", platform_id="p", source_event_id="original")
    assert [m["content"] for m in (await store.read(old.conversation_id)).messages] == [
        "question",
        "original answer",
    ]
    await store.delete(cid="main")
    assert [m["content"] for m in (await store.read("side")).messages] == [
        "question",
        "original answer",
    ]
