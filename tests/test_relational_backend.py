"""Behavior shared by SQLite and the optional PostgreSQL backend."""

import asyncio
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from astrbot.core.backup.exporter import AstrBotExporter
from astrbot.core.backup.importer import AstrBotImporter
from astrbot.core.db.conversation import ConversationConflictError


@pytest.mark.asyncio
async def test_search_preferences_stats_and_restored_sequence(temp_db):
    await temp_db.initialize()
    conv = await temp_db.create_conversation(
        "p:FriendMessage:user", "p", [{"role": "user", "content": "searchable 文本"}]
    )
    rows, count = await temp_db.get_filtered_conversations(search_query="文本")
    assert count == 1 and rows[0].conversation_id == conv.conversation_id
    await temp_db.update_conversation(
        conv.conversation_id, content=[{"role": "user", "content": "replacement"}]
    )
    assert (await temp_db.get_filtered_conversations(search_query="文本"))[1] == 0
    assert (await temp_db.get_filtered_conversations(search_query="replacement"))[
        1
    ] == 1
    await temp_db.insert_preference_or_update(
        "plugin", "owner", "key", {"val": [1, "中文"]}
    )
    assert temp_db.get_preference_sync("plugin", "owner", "key") == {"val": [1, "中文"]}
    assert len(temp_db.get_preferences_sync("plugin", "owner")) == 1
    now = datetime.now()
    await temp_db.insert_platform_stats("p", "test", 2, now - timedelta(hours=1))
    await temp_db.insert_platform_stats("p", "test", 3, now)
    await temp_db.insert_platform_stats("p", "test", 4, now)
    stats = await temp_db.get_platform_stats()
    assert len(stats) == 1 and stats[0].count == 7
    backup = await AstrBotExporter(temp_db)._export_main_database()
    # Restore explicit IDs far ahead of the server's current sequence.
    owner = backup["conversations_v3"][0]["id"]
    backup["conversations_v3"][0]["id"] = 10000
    for event in backup["conversation_events"]:
        if event["conversation_ref"] == owner:
            event["conversation_ref"] = 10000
    importer = AstrBotImporter(temp_db)
    await importer._clear_main_db()
    await importer._import_main_database(backup)
    created = await temp_db.conversation_store.create(umo="next", platform_id="p")
    assert created.id > 10000
    assert (await temp_db.get_conversation_by_id(conv.conversation_id)).content == [
        {"role": "user", "content": "replacement"}
    ]


@pytest.mark.asyncio
async def test_postgres_locks_only_the_target_conversation(temp_db):
    if temp_db.engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock isolation")
    await temp_db.initialize()
    store = temp_db.conversation_store
    first = await store.create(umo="first", platform_id="p")
    second = await store.create(umo="second", platform_id="p")
    draft = {
        "type": "message.appended",
        "payload": {"message": {"role": "user", "content": "new"}},
    }
    async with temp_db.get_db() as holder:
        await holder.execute(
            text("SELECT id FROM conversations_v3 WHERE id=:id FOR UPDATE"),
            {"id": first.id},
        )
        # A write to another conversation must finish while the first lock is held.
        await asyncio.wait_for(store.append(second.conversation_id, [draft]), timeout=5)
        await holder.execute(
            text("UPDATE conversations_v3 SET head_seq=head_seq+1 WHERE id=:id"),
            {"id": first.id},
        )
        waiting = asyncio.create_task(
            store.append(first.conversation_id, [draft], expected_head=first.head_seq)
        )
        await holder.commit()
        with pytest.raises(ConversationConflictError):
            await asyncio.wait_for(waiting, timeout=5)
    assert (await store.read(first.conversation_id)).messages == []
    assert (await store.read(second.conversation_id)).messages == [
        draft["payload"]["message"]
    ]


@pytest.mark.asyncio
async def test_context_read_survives_concurrent_baseline_reclamation(
    temp_db, monkeypatch
):
    """Metadata and payloads must come from one view, even if a writer prunes."""
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

    from astrbot.core.db.po import ConversationV3

    await temp_db.initialize()
    store = temp_db.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    original = [{"role": "user", "content": "before"}]
    replacement = [{"role": "user", "content": "after"}]
    await store.append(conv.conversation_id, [], history=original, origin="plugin")
    execute = AsyncSession.execute
    replaced = False

    async def interleave(session, statement, *args, **kwargs):
        nonlocal replaced
        result = await execute(session, statement, *args, **kwargs)
        if (
            not replaced
            and isinstance(statement, Select)
            and any(
                column.get("entity") is ConversationV3
                for column in statement.column_descriptions
            )
        ):
            replaced = True
            await store.append(
                conv.conversation_id, [], history=replacement, origin="plugin"
            )
        return result

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "execute", interleave)
        observed = await store.read(conv.conversation_id)
    assert replaced and observed.messages == original
    assert (await store.read(conv.conversation_id)).messages == replacement


@pytest.mark.asyncio
async def test_webchat_startup_migration_is_portable(temp_db):
    from astrbot.core.db.migration.migra_webchat_session import migrate_webchat_session

    await temp_db.initialize()
    for _ in range(2):
        await temp_db.insert_platform_message_history(
            "webchat",
            "session",
            {"type": "user", "message": []},
            sender_id="owner",
            sender_name="Alice",
        )
    await migrate_webchat_session(temp_db)
    await migrate_webchat_session(temp_db)
    session = await temp_db.get_platform_session_by_id("session")
    assert session.creator == "Alice"
