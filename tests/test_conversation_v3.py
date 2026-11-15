"""Behavioral checks for event storage, migration, and runner compatibility."""

import asyncio
import json
from base64 import urlsafe_b64decode
from uuid import UUID

import pytest
from sqlalchemy import text
from sqlmodel import select

from astrbot.core.agent.conversation_events import ConversationEventWriter
from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.db.po import (
    ConversationEvent,
    ConversationV2,
    ConversationV3,
    PlatformMessageHistory,
)
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest.mark.asyncio
async def test_concurrent_writers_and_idempotent_delivery(database):
    conv = await database.create_conversation("umo", "p")
    store = database.conversation_store
    snapshot = await store.read(conv.conversation_id)
    writers = [ConversationEventWriter(store, snapshot) for _ in range(2)]
    event_ids = ["b2b69141-452b-4a14-b9cb-87b279a2cd98", "plugin-delivery-1"]
    results = await asyncio.gather(
        *(
            writer.append("plugin.test.result", {"value": i}, event_id=event_ids[i])
            for i, writer in enumerate(writers)
        )
    )
    assert {event.event_id for event in results} == set(event_ids)
    assert len({event.seq for event in results}) == 2
    repeated = await writers[0].append(
        "plugin.test.result", {"value": 0}, event_id=event_ids[0]
    )
    assert repeated.event_id == event_ids[0]
    with pytest.raises(ConversationConflictError):
        await writers[0].append(
            "plugin.test.result", {"value": "different"}, event_id=event_ids[0]
        )
    assert len(await store.events(conv.conversation_id)) == 3


@pytest.mark.asyncio
async def test_plugin_manager_entrypoint_isolates_explicit_conversations(database):
    from astrbot.core.conversation_mgr import ConversationManager

    manager = ConversationManager(database)
    store = database.conversation_store
    writers = []
    for plugin_id in ("memory", "search"):
        conv = await database.create_conversation(plugin_id, "p")
        writer = await manager.create_event_writer(
            conv.conversation_id, unified_msg_origin=plugin_id
        )
        writers.append(writer)

    await asyncio.gather(
        *(
            manager.append_message(plugin_id, cid=writer.cid)
            for writer, plugin_id in zip(writers, ("memory", "search"))
        )
    )
    for writer, plugin_id in zip(writers, ("memory", "search")):
        snapshot = await store.read(writer.cid)
        assert snapshot.messages == [{"role": "user", "content": plugin_id}]
        assert writer.get_messages() == []
        with pytest.raises(ConversationConflictError):
            await writer.save_history([{"role": "user", "content": "stale"}])

    with pytest.raises(ValueError, match="not accessible"):
        await manager.create_event_writer(writers[0].cid, unified_msg_origin="other")


@pytest.mark.asyncio
async def test_migration_drops_old_table_and_preserves_checkpoint_links(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "migration.db"))
    async with db.engine.begin() as connection:
        await connection.run_sync(ConversationV2.__table__.create)
        await connection.execute(
            text(
                "CREATE TABLE platform_message_history (id INTEGER PRIMARY KEY, platform_id TEXT NOT NULL, user_id TEXT NOT NULL, sender_id TEXT, sender_name TEXT, content JSON NOT NULL, llm_checkpoint_id TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"
            )
        )
    history = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
        {"role": "_checkpoint", "content": {"id": "cp1"}},
    ]
    async with db.AsyncSessionLocal() as session:
        session.add(
            ConversationV2(
                conversation_id="old",
                platform_id="webchat",
                user_id="webchat:FriendMessage:webchat!alice!session1",
                content=history,
                token_usage=123,
            )
        )
        await session.execute(
            text(
                "INSERT INTO platform_message_history VALUES (1, 'webchat', 'session1', NULL, NULL, :content, 'cp1', '2026-01-01', '2026-01-01')"
            ),
            {"content": json.dumps({"type": "bot", "message": []})},
        )
        await session.commit()
    await db.initialize()
    await db.initialize()
    restored = await db.get_conversation_by_id("old")
    assert restored.content == history[:2]
    assert restored.token_usage == 123
    async with db.get_db() as session:
        assert not (
            await session.execute(
                text("SELECT 1 FROM sqlite_master WHERE name='conversations'")
            )
        ).first()
        record = await session.get(PlatformMessageHistory, 1)
        event = (
            await session.execute(
                select(ConversationEvent).where(
                    ConversationEvent.event_id == record.context_event_id
                )
            )
        ).scalar_one()
        assert event.payload["message"]["content"] == "world"
        assert record.turn_id == event.payload["turn_id"]
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_webchat_edit_preserves_original_branch_and_side_thread(database):
    store = database.conversation_store
    umo = "webchat:FriendMessage:webchat!alice!session1"
    conv = await store.create(umo=umo, platform_id="webchat")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.start_turn({"kind": "im_wake"}, event_id="t1")
    user = await database.insert_platform_message_history(
        "webchat", "session1", {"type": "user", "message": []}, turn_id="t1"
    )
    await writer.save_history(
        [{"role": "user", "content": "old"}, {"role": "assistant", "content": "answer"}]
    )
    bot = await database.insert_platform_message_history(
        "webchat", "session1", {"type": "bot", "message": []}, turn_id="t1"
    )
    await writer.finish_turn("completed")
    side = await store.create(
        umo="webchat:FriendMessage:webchat!alice!side",
        platform_id="webchat",
        source_event_id=bot.context_event_id,
    )
    snapshot = await store.read(conv.conversation_id)
    replacement = await store.rewind_webchat(
        conv.conversation_id,
        user.id,
        content={"type": "user", "message": [{"type": "plain", "text": "edited"}]},
        expected_head=snapshot.revision.head_seq,
        expected_leaf=snapshot.revision.leaf_event_id,
    )
    assert replacement.id != user.id
    assert (await store.read(conv.conversation_id)).messages == []
    assert [
        m["content"] for m in (await store.read(side.conversation_id)).messages
    ] == ["old", "answer"]
    visible = await database.get_platform_message_history("webchat", "session1")
    assert [r.id for r in visible] == [replacement.id]
    assert (
        await database.get_platform_message_history_by_id(user.id)
    ).is_active is False


@pytest.mark.asyncio
async def test_failed_migration_keeps_legacy_data_and_can_retry(tmp_path, monkeypatch):
    db = SQLiteDatabase(str(tmp_path / "rollback.db"))
    async with db.engine.begin() as connection:
        await connection.run_sync(ConversationV2.__table__.create)
    original = [{"role": "user", "content": "must survive"}]
    async with db.AsyncSessionLocal() as session:
        session.add(
            ConversationV2(
                conversation_id="old", platform_id="p", user_id="umo", content=original
            )
        )
        await session.commit()
    project = db.conversation_store.project

    async def fail_verification(*args, **kwargs):
        raise ValueError("injected verification failure")

    monkeypatch.setattr(db.conversation_store, "project", fail_verification)
    with pytest.raises(ValueError, match="injected"):
        await db.initialize()
    assert not db.inited
    async with db.AsyncSessionLocal() as session:
        old = (await session.execute(select(ConversationV2))).scalar_one()
        assert old.content == original
        assert not (await session.execute(select(ConversationV3))).first()
        assert not (await session.execute(select(ConversationEvent))).first()
    monkeypatch.setattr(db.conversation_store, "project", project)
    await db.initialize()
    assert (await db.get_conversation_by_id("old")).content == original
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_provider_retry_has_distinct_attempts(database):
    from astrbot.core.agent.event_stream import RequestEventRecorder
    from astrbot.core.provider.entities import TokenUsage
    from astrbot.core.provider.sources.request_retry import retry_provider_request

    conv = await database.create_conversation("umo", "p")
    writer = ConversationEventWriter(
        database.conversation_store,
        await database.conversation_store.read(conv.conversation_id),
    )
    await writer.start_turn({"kind": "agent"})
    input_context = {
        "contexts": [{"role": "user", "content": "retry this request"}],
        "extra_user_content_parts": [],
        "complete": True,
    }
    recorder = RequestEventRecorder(
        writer.consume,
        {"turn_id": writer.turn_id, "input_context": input_context},
        invocation_id="runtime-call",
    )
    await recorder.begin()
    attempts = 0

    class RetryableError(RuntimeError):
        status_code = 429

    async def invoke():
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RetryableError("rate limited")
        return "answer"

    assert (
        await retry_provider_request(
            "test", invoke, max_attempts=2, request_event_recorder=recorder
        )
        == "answer"
    )
    await recorder.finish("completed", usage=TokenUsage(input_other=10, output=3))
    events = await database.conversation_store.events(conv.conversation_id)
    for event in events:
        assert len(event.event_id) == 22
        assert set(event.event_id) <= set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        assert UUID(bytes=urlsafe_b64decode(event.event_id + "==")).version == 4
    starts = [e for e in events if e.type == "request.started"]
    finishes = [e for e in events if e.type == "request.finished"]
    assert len(starts) == len(finishes) == 2
    assert [e.payload["invocation_id"] for e in starts] == [
        "runtime-call",
        "runtime-call",
    ]
    assert [e.payload["attempt"] for e in starts] == [1, 2]
    assert [e.payload["request_id"] for e in finishes] == [e.event_id for e in starts]
    assert [e.payload["status"] for e in finishes] == ["failed", "completed"]
    for start in starts:
        assert (
            await database.conversation_store.read_request_context(
                writer.cid, start.event_id
            )
            == input_context
        )
