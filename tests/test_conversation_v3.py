"""Behavioral checks for event storage, migration, and runner compatibility."""

import asyncio
import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlmodel import select

from astrbot.core.agent.conversation_events import ConversationEventWriter
from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.db.po import ConversationEvent, ConversationV2, ConversationV3, PlatformMessageHistory
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def database(tmp_path: Path):
    db = SQLiteDatabase(str(tmp_path / "events.db"))
    await db.initialize()
    yield db
    await db.engine.dispose()


@pytest.mark.asyncio
async def test_legacy_api_appends_and_rebases_without_losing_old_events(database):
    conv = await database.create_conversation("umo", "platform", [{"role": "user", "content": "old"}])
    await database.update_conversation(conv.conversation_id, content=[
        {"role": "user", "content": "old"}, {"role": "assistant", "content": "reply"}])
    before = await database.conversation_store.events(conv.conversation_id)
    assert before[-1].type == "message.appended"
    await database.update_conversation(conv.conversation_id, content=[{"role": "user", "content": "edited"}])
    after = await database.conversation_store.events(conv.conversation_id)
    assert [e.model_dump() for e in after[:len(before)]] == [e.model_dump() for e in before]
    assert after[-1].type == "context.rebased"
    restored = await database.get_conversation_by_id(conv.conversation_id)
    assert restored.content == [{"role": "user", "content": "edited"}]
    restored.content[0]["content"] = "local mutation"
    assert (await database.get_conversation_by_id(conv.conversation_id)).content[0]["content"] == "edited"


@pytest.mark.asyncio
async def test_branches_null_parent_and_excluded_messages(database):
    conv = await database.create_conversation("umo", "p")
    store = database.conversation_store
    first = (await store.append(conv.conversation_id, [{"event_id": "root", "type": "message.appended", "payload": {"message": {"role": "user", "content": "root"}}}]))[0]
    await store.append(conv.conversation_id, [{"type": "message.appended", "payload": {"include_in_context": False, "message": {"role": "user", "content": "temporary"}}}])
    await store.append(conv.conversation_id, [{"type": "message.appended", "payload": {"message": {"role": "assistant", "content": "reply"}}}])
    assert [m["content"] for m in (await store.read(conv.conversation_id)).messages] == ["root", "reply"]
    branch = await store.create(umo="umo", platform_id="p", parent_event_id=first.event_id)
    await store.append(branch.conversation_id, [{"type": "message.appended", "payload": {"message": {"role": "assistant", "content": "branch"}}}])
    assert [m["content"] for m in (await store.read(branch.conversation_id)).messages] == ["root", "branch"]
    with pytest.raises(ValueError, match="referenced"):
        await store.delete(cid=conv.conversation_id)
    await store.append(branch.conversation_id, [{"type": "message.appended", "parent_event_id": None, "payload": {"message": {"role": "user", "content": "new root"}}}])
    assert (await store.read(branch.conversation_id)).messages == [{"role": "user", "content": "new root"}]
    with pytest.raises(ValueError, match="accessible"):
        await store.create(umo="other", platform_id="p", parent_event_id=first.event_id)


@pytest.mark.asyncio
async def test_concurrent_writers_and_idempotent_delivery(database):
    conv = await database.create_conversation("umo", "p")
    store = database.conversation_store
    snapshot = await store.read(conv.conversation_id)
    writers = [ConversationEventWriter(store, snapshot) for _ in range(2)]
    results = await asyncio.gather(*(w.append("plugin.test.result", {"value": i}, event_id=f"p{i}") for i, w in enumerate(writers)), return_exceptions=True)
    assert sum(isinstance(r, ConversationConflictError) for r in results) == 1
    succeeded = next(i for i, r in enumerate(results) if not isinstance(r, Exception))
    repeated = await writers[succeeded].append("plugin.test.result", {"value": succeeded}, event_id=f"p{succeeded}")
    assert repeated.event_id == f"p{succeeded}"
    with pytest.raises(ConversationConflictError):
        await writers[succeeded].append("plugin.test.result", {"value": "different"}, event_id=f"p{succeeded}")
    assert len(await store.events(conv.conversation_id)) == 2


@pytest.mark.asyncio
async def test_staged_plugin_changes_no_save_and_private_journal(database):
    conv = await database.create_conversation("umo", "p")
    writer = ConversationEventWriter(database.conversation_store, await database.conversation_store.read(conv.conversation_id))
    await writer.start_turn({"kind": "plugin"})
    writer.stage_history([{"role": "user", "content": "secret", "_no_save": True}, {"role": "user", "content": "old"}])
    writer.stage_history([{"role": "user", "content": "summary"}], reason="compaction")
    assert (await database.get_conversation_by_id(conv.conversation_id)).content == []
    plugin = writer.plugin("memory")
    await plugin.append("retrieval_finished", {"document_ids": ["d1"]})
    assert (await plugin.latest("retrieval_finished")).payload["document_ids"] == ["d1"]
    await writer.save_history([{"role": "user", "content": "summary"}])
    await writer.finish_turn("completed")
    events = await database.conversation_store.events(conv.conversation_id)
    serialized = json.dumps([e.payload for e in events])
    assert "secret" in serialized and "old" in serialized
    assert next(e for e in events if e.payload.get("message", {}).get("content") == "secret").payload["include_in_context"] is False
    assert (await database.get_conversation_by_id(conv.conversation_id)).content == [{"role": "user", "content": "summary"}]


@pytest.mark.asyncio
async def test_replay_ignores_large_execution_log_and_pages_by_cursor(database):
    conv = await database.create_conversation("umo", "p", [{"role": "user", "content": "kept"}])
    async with database.get_db() as session:
        await session.execute(ConversationEvent.__table__.insert(), [
            {"conversation_ref": conv.inner_conversation_id, "seq": i + 3, "event_id": f"log{i}", "type": "plugin.test.progress", "payload": {"i": i}}
            for i in range(100_000)
        ])
        metadata = await session.get(ConversationV3, conv.inner_conversation_id)
        metadata.head_seq = 100_002
        await session.commit()
    snapshot = await database.conversation_store.read(conv.conversation_id)
    assert snapshot.replay_count == 1
    assert snapshot.messages == [{"role": "user", "content": "kept"}]
    page = await database.conversation_store.events(conv.conversation_id, after_seq=99_998, limit=3)
    assert [e.seq for e in page] == [99_999, 100_000, 100_001]


@pytest.mark.asyncio
async def test_plugin_manager_entrypoint_isolates_concurrent_hooks(database):
    from astrbot.core.agent.conversation_events import (
        active_conversation_writer,
        active_plugin_id,
    )
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.conversation_mgr import ConversationManager

    manager = ConversationManager(database)
    store = database.conversation_store
    writers = []
    for plugin_id in ("memory", "search"):
        conv = await database.create_conversation(plugin_id, "p")
        writer = await manager.event_writer(plugin_id, conv.conversation_id)
        writer.runtime_context = ContextWrapper(context=None, messages=[])
        writers.append(writer)

    async def run_hook(writer, plugin_id):
        writer_token = active_conversation_writer.set(writer)
        plugin_token = active_plugin_id.set(plugin_id)
        try:
            await asyncio.sleep(0)
            events = manager.get_conversation_events()
            saved = await events.append("retrieval_completed", {"source": plugin_id})
            await events.append_message(
                {"role": "user", "content": plugin_id}, event_id=plugin_id
            )
            await events.append_message(
                {"role": "user", "content": "temporary"}, include_in_context=False
            )
            assert (await events.latest("retrieval_completed")).event_id == saved.event_id
            assert len(await events.list("retrieval_completed")) == 1
            assert await events.list("retrieval_completed", after_seq=saved.seq) == []
        finally:
            active_plugin_id.reset(plugin_token)
            active_conversation_writer.reset(writer_token)

    await asyncio.gather(
        *(run_hook(writer, plugin_id) for writer, plugin_id in zip(writers, ("memory", "search")))
    )
    for writer, plugin_id in zip(writers, ("memory", "search")):
        snapshot = await store.read(writer.cid)
        assert snapshot.messages == [{"role": "user", "content": plugin_id}]
        private = await store.events(writer.cid, event_type=f"plugin.{plugin_id}.retrieval_completed")
        assert len(private) == 1
        assert private[0].payload == {"source": plugin_id}
        assert writer.runtime_context.messages[0].content == plugin_id
        assert writer.runtime_context.messages[1]._no_save

    with pytest.raises(RuntimeError, match="active conversation hook"):
        manager.get_conversation_events()

    writer_token = active_conversation_writer.set(writers[0])
    try:
        with pytest.raises(RuntimeError, match="active conversation hook"):
            manager.get_conversation_events()
    finally:
        active_conversation_writer.reset(writer_token)


@pytest.mark.asyncio
async def test_migration_drops_old_table_and_preserves_checkpoint_links(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "migration.db"))
    async with db.engine.begin() as connection:
        await connection.run_sync(ConversationV2.__table__.create)
        await connection.execute(text("CREATE TABLE platform_message_history (id INTEGER PRIMARY KEY, platform_id TEXT NOT NULL, user_id TEXT NOT NULL, sender_id TEXT, sender_name TEXT, content JSON NOT NULL, llm_checkpoint_id TEXT, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL)"))
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "world"}, {"role": "_checkpoint", "content": {"id": "cp1"}}]
    async with db.AsyncSessionLocal() as session:
        session.add(ConversationV2(conversation_id="old", platform_id="webchat", user_id="webchat:FriendMessage:webchat!alice!session1", content=history, token_usage=123))
        await session.execute(text("INSERT INTO platform_message_history VALUES (1, 'webchat', 'session1', NULL, NULL, :content, 'cp1', '2026-01-01', '2026-01-01')"), {"content": json.dumps({"type": "bot", "message": []})})
        await session.commit()
    await db.initialize()
    await db.initialize()
    restored = await db.get_conversation_by_id("old")
    assert restored.content == history[:2]
    assert restored.token_usage == 123
    async with db.get_db() as session:
        assert not (await session.execute(text("SELECT 1 FROM sqlite_master WHERE name='conversations'"))).first()
        record = await session.get(PlatformMessageHistory, 1)
        event = (await session.execute(select(ConversationEvent).where(ConversationEvent.event_id == record.context_event_id))).scalar_one()
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
    user = await database.insert_platform_message_history("webchat", "session1", {"type": "user", "message": []}, turn_id="t1")
    await writer.save_history([{"role": "user", "content": "old"}, {"role": "assistant", "content": "answer"}])
    bot = await database.insert_platform_message_history("webchat", "session1", {"type": "bot", "message": []}, turn_id="t1")
    await writer.finish_turn("completed")
    side = await store.create(umo="webchat:FriendMessage:webchat!alice!side", platform_id="webchat", parent_event_id=bot.context_event_id)
    snapshot = await store.read(conv.conversation_id)
    replacement = await store.rewind_webchat(conv.conversation_id, user.id, content={"type": "user", "message": [{"type": "plain", "text": "edited"}]}, expected_head=snapshot.conversation.head_seq, expected_leaf=snapshot.conversation.leaf_event_id)
    assert replacement.id != user.id
    assert (await store.read(conv.conversation_id)).messages == []
    assert [m["content"] for m in (await store.read(side.conversation_id)).messages] == ["old", "answer"]
    visible = await database.get_platform_message_history("webchat", "session1")
    assert [r.id for r in visible] == [replacement.id]
    assert (await database.get_platform_message_history_by_id(user.id)).is_active is False


@pytest.mark.asyncio
async def test_failed_migration_keeps_legacy_data_and_can_retry(tmp_path, monkeypatch):
    db = SQLiteDatabase(str(tmp_path / "rollback.db"))
    async with db.engine.begin() as connection:
        await connection.run_sync(ConversationV2.__table__.create)
    original = [{"role": "user", "content": "must survive"}]
    async with db.AsyncSessionLocal() as session:
        session.add(ConversationV2(conversation_id="old", platform_id="p", user_id="umo", content=original))
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
async def test_native_append_and_legacy_nested_edits_share_runtime(database):
    from astrbot.core.agent.message import Message, dump_messages_with_checkpoints
    from astrbot.core.agent.run_context import ContextWrapper

    conv = await database.create_conversation("umo", "p")
    writer = ConversationEventWriter(database.conversation_store, await database.conversation_store.read(conv.conversation_id))
    await writer.start_turn({"kind": "agent"})
    writer.runtime_context = ContextWrapper(context=None, messages=[Message(role="user", content="input")])
    writer.stage_history([{"role": "user", "content": "input"}])
    native = await writer.append_message({"role": "assistant", "content": [{"type": "text", "text": "native"}]}, event_id="native")
    assert len(writer.runtime_context.messages) == 2
    await writer.append_message({"role": "user", "content": "journal only"}, include_in_context=False)
    assert writer.runtime_context.messages[-1]._no_save
    writer.runtime_context.messages[1].content[0].text = "plugin edited"
    history = dump_messages_with_checkpoints([m for m in writer.runtime_context.messages if not m._no_save])
    await writer.save_history(history)
    restored = await database.conversation_store.read(conv.conversation_id)
    assert restored.messages == history
    assert len(restored.messages) == 2
    assert restored.messages[1]["content"][0]["text"] == "plugin edited"
    events = await database.conversation_store.events(conv.conversation_id)
    assert next(e for e in events if e.event_id == native.event_id).payload["message"]["content"][0]["text"] == "native"


@pytest.mark.asyncio
async def test_large_baseline_does_not_repeat_snapshots(database):
    store = database.conversation_store
    conv = await database.create_conversation("umo", "p", [{"role": "user", "content": "x" * (4 * 1024 * 1024 + 1)}])
    before = await store.read(conv.conversation_id)
    events = await store.append(conv.conversation_id, [{"type": "message.appended", "payload": {"message": {"role": "assistant", "content": "small"}}}])
    assert [e.type for e in events] == ["message.appended"]
    after = await store.read(conv.conversation_id)
    assert after.conversation.replay_from_event_id == before.conversation.replay_from_event_id
    assert after.replay_bytes < 1024


@pytest.mark.asyncio
async def test_execution_protocol_rejects_invalid_relationships_and_usage(database):
    conv = await database.create_conversation("umo", "p")
    store = database.conversation_store
    await store.append(conv.conversation_id, [{"event_id": "turn", "type": "turn.started", "payload": {}}])
    await store.append(conv.conversation_id, [{"event_id": "request", "type": "request.started", "payload": {"turn_id": "turn"}}])
    with pytest.raises(ValueError, match="subset"):
        await store.append(conv.conversation_id, [{"type": "request.finished", "payload": {"request_id": "request", "status": "completed", "usage": {"input_tokens": 1, "cached_input_tokens": 2}}}])
    await store.append(conv.conversation_id, [{"type": "request.finished", "payload": {"request_id": "request", "status": "failed"}}])
    with pytest.raises(ConversationConflictError, match="finished"):
        await store.append(conv.conversation_id, [{"type": "request.finished", "payload": {"request_id": "request", "status": "completed"}}])
    with pytest.raises(ValueError, match="parent turn"):
        await store.append(conv.conversation_id, [{"type": "tool.started", "payload": {"turn_id": "request"}}])


@pytest.mark.asyncio
async def test_old_backup_import_and_new_backup_round_trip(database):
    from astrbot.core.backup.exporter import AstrBotExporter
    from astrbot.core.backup.importer import AstrBotImporter

    importer = AstrBotImporter(database)
    original = [{"role": "user", "content": "backup"}, {"role": "assistant", "content": "restored"}, {"role": "_checkpoint", "content": {"id": "cp"}}]
    counts = await importer._import_main_database({
        "conversations": [{"inner_conversation_id": 7, "conversation_id": "old-backup", "platform_id": "webchat", "user_id": "webchat:FriendMessage:webchat!alice!s1", "content": original, "token_usage": 42}],
        "platform_message_history": [{"id": 9, "platform_id": "webchat", "user_id": "s1", "content": {"type": "bot", "message": []}, "llm_checkpoint_id": "cp"}],
    })
    assert counts["conversations"] == 1
    restored = await database.get_conversation_by_id("old-backup")
    assert restored.content == original[:2]
    linked = await database.get_platform_message_history_by_id(9)
    assert linked.context_event_id and linked.turn_id != "cp"
    exported = await AstrBotExporter(database)._export_main_database()
    assert "conversations" not in exported and exported["conversation_events"]
    await importer._clear_main_db()
    await importer._import_main_database(exported)
    assert (await database.get_conversation_by_id("old-backup")).content == original[:2]
    assert (await database.get_platform_message_history_by_id(9)).context_event_id == linked.context_event_id


@pytest.mark.asyncio
async def test_temporary_parts_are_recorded_once_and_excluded_from_projection(database):
    from astrbot.core.agent.message import Message, TextPart, dump_messages_with_checkpoints
    conv = await database.create_conversation("umo", "p")
    writer = ConversationEventWriter(database.conversation_store, await database.conversation_store.read(conv.conversation_id))
    await writer.start_turn({"kind": "agent"})
    messages = [Message(role="user", content=[TextPart(text="keep"), TextPart(text="temporary").mark_as_temp()])]
    raw = dump_messages_with_checkpoints(messages, include_temporary=True)
    writer.stage_history(raw)
    writer.stage_history(raw)
    await writer.save_history(raw)
    events = await database.conversation_store.events(conv.conversation_id)
    assert len([e for e in events if e.payload.get("include_in_context") is False]) == 1
    assert "temporary" in json.dumps([e.payload for e in events])
    projected = (await database.conversation_store.read(conv.conversation_id)).messages
    assert projected[0]["content"] == [{"type": "text", "text": "keep"}]


@pytest.mark.asyncio
async def test_provider_retry_has_distinct_attempts(database):
    from astrbot.core.agent.event_stream import RequestEventRecorder
    from astrbot.core.provider.entities import TokenUsage
    from astrbot.core.provider.sources.request_retry import retry_provider_request

    conv = await database.create_conversation("umo", "p")
    writer = ConversationEventWriter(database.conversation_store, await database.conversation_store.read(conv.conversation_id))
    await writer.start_turn({"kind": "agent"})
    recorder = RequestEventRecorder(writer.consume, {"turn_id": writer.turn_id})
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

    assert await retry_provider_request(
        "test", invoke, max_attempts=2, request_event_recorder=recorder
    ) == "answer"
    await recorder.finish("completed", usage=TokenUsage(input_other=10, output=3))
    events = await database.conversation_store.events(conv.conversation_id)
    starts = [e for e in events if e.type == "request.started"]
    finishes = [e for e in events if e.type == "request.finished"]
    assert len(starts) == len(finishes) == 2
    assert [e.payload["request_id"] for e in finishes] == [e.event_id for e in starts]
    assert [e.payload["status"] for e in finishes] == ["failed", "completed"]


@pytest.mark.asyncio
async def test_idempotent_batch_includes_its_automatic_rebase(database):
    conv = await database.create_conversation("umo", "p")
    store = database.conversation_store
    drafts = [{"event_id": f"m{i}", "type": "message.appended", "payload": {"message": {"role": "user", "content": str(i)}}} for i in range(257)]
    first = await store.append(conv.conversation_id, drafts, expected_head=1, expected_leaf=None)
    assert first[-1].payload["reason"] == "snapshot"
    retried = await store.append(conv.conversation_id, drafts, expected_head=1, expected_leaf=None)
    assert [e.event_id for e in retried] == [e.event_id for e in first]
    assert (await store.read(conv.conversation_id)).replay_count == 1


@pytest.mark.asyncio
async def test_webchat_links_plugin_replacement_without_an_appended_reply(database):
    store = database.conversation_store
    conv = await database.create_conversation("umo", "p", [{"role": "user", "content": "old"}])
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.start_turn({"kind": "agent"})
    await writer.save_history([{"role": "user", "content": "rewritten"}, {"role": "assistant", "content": "new answer"}])
    record = await database.insert_platform_message_history("webchat", "s1", {"type": "bot", "message": []}, turn_id=writer.turn_id)
    assert record.context_event_id == writer.leaf_event_id
    fork = await store.create(umo="umo", platform_id="p", parent_event_id=record.context_event_id)
    assert (await store.read(fork.conversation_id)).messages[-1]["content"] == "new answer"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["append", "select_branch"])
async def test_declared_read_revision_rejects_context_changes(database, change):
    from dataclasses import FrozenInstanceError

    from astrbot.core.conversation_mgr import ConversationManager
    from astrbot.core.db.po import ConversationRead, ConversationRevision

    store = database.conversation_store
    manager = ConversationManager(database)
    created = await database.create_conversation("umo", "p")
    first = (await store.append(created.conversation_id, [
        {"type": "message.appended", "payload": {"message": {"role": "user", "content": "first"}}},
        {"type": "message.appended", "payload": {"message": {"role": "assistant", "content": "second"}}},
    ]))[0]
    record = await database.get_conversation_by_id(created.conversation_id)
    conversation = await manager.get_conversation("umo", created.conversation_id)
    assert isinstance(record, ConversationRead)
    assert isinstance(record.revision, ConversationRevision)
    assert conversation.revision == record.revision
    assert json.loads(conversation.history) == record.content
    assert "revision" not in ConversationV3.__table__.columns
    assert "revision" not in ConversationV2.__table__.columns
    with pytest.raises(FrozenInstanceError):
        conversation.revision.head_seq = 0
    writer = await manager.event_writer("umo", created.conversation_id, expected_revision=conversation.revision)
    if change == "append":
        await writer.append("plugin.test.changed", {})
    else:
        await store.select_branch(
            created.conversation_id, first.event_id,
            expected_head=record.revision.head_seq,
            expected_leaf=record.revision.leaf_event_id,
        )
    with pytest.raises(ConversationConflictError, match="preparing"):
        await manager.event_writer("umo", created.conversation_id, expected_revision=conversation.revision)


@pytest.mark.asyncio
async def test_autonomous_summary_uses_the_same_writer_after_execution_events(database):
    from types import SimpleNamespace

    from astrbot.core.agent.response import AgentResponse
    from astrbot.core.provider.entities import ProviderRequest
    from astrbot.core.utils.history_saver import persist_agent_history

    conv = await database.create_conversation("umo", "p")
    store = database.conversation_store
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.consume(AgentResponse("turn.started", {}, "summary-turn"))
    await writer.consume(AgentResponse("request.started", {}, "summary-request"))
    await writer.consume(AgentResponse("request.finished", {
        "request_id": "summary-request", "status": "completed",
    }))
    req = ProviderRequest()
    req.conversation = SimpleNamespace(history="[]", cid=conv.conversation_id)
    await persist_agent_history(
        None, event=SimpleNamespace(unified_msg_origin="umo"), req=req,
        summary_note="Task completed", conversation_events=writer,
    )
    await writer.finish_turn("completed")
    assert (await store.read(conv.conversation_id)).messages == [
        {"role": "user", "content": "Output your last task result below."},
        {"role": "assistant", "content": "Task completed"},
    ]
    events = await store.events(conv.conversation_id)
    assert [e.type for e in events] == [
        "conversation.created", "turn.started", "request.started", "request.finished",
        "message.appended", "message.appended", "turn.finished",
    ]


@pytest.mark.asyncio
async def test_display_context_lookup_holds_the_write_transaction(database, monkeypatch):
    """An event commit must not slip between link lookup and display insertion."""
    import sqlite3

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql import Select

    store = database.conversation_store
    conv = await store.create(umo="umo", platform_id="webchat")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.start_turn({"kind": "agent"})
    original_execute = AsyncSession.execute
    checked = False

    async def execute(session, statement, *args, **kwargs):
        nonlocal checked
        result = await original_execute(session, statement, *args, **kwargs)
        if isinstance(statement, Select) and any(
            column.get("entity") is ConversationEvent
            for column in statement.column_descriptions
        ):
            contender = sqlite3.connect(database.engine.url.database, timeout=0)
            try:
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    contender.execute("BEGIN IMMEDIATE")
                checked = True
            finally:
                contender.close()
        return result

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "execute", execute)
        record = await database.insert_platform_message_history(
            "webchat", "session", {"type": "bot", "message": []},
            turn_id=writer.turn_id,
        )
    assert checked
    assert record.context_event_id is None
    await writer.save_history([{"role": "assistant", "content": "answer"}])
    linked = await database.get_platform_message_history_by_id(record.id)
    assert linked.context_event_id == writer.leaf_event_id


@pytest.mark.asyncio
@pytest.mark.parametrize("display_first", [False, True])
async def test_edited_turn_reply_can_fork_without_original_or_later_messages(database, display_first):
    store = database.conversation_store
    umo = "webchat:FriendMessage:webchat!alice!edited-session"
    conv = await store.create(umo=umo, platform_id="webchat")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.start_turn({"kind": "agent"})
    user = await database.insert_platform_message_history(
        "webchat", "edited-session", {"type": "user", "message": []}, turn_id=writer.turn_id,
    )
    await writer.save_history([
        {"role": "user", "content": "original"},
        {"role": "assistant", "content": "original answer"},
    ])
    await writer.finish_turn("completed")
    snapshot = await store.read(conv.conversation_id)
    replacement = await store.rewind_webchat(
        conv.conversation_id, user.id,
        content={"type": "user", "message": [{"type": "plain", "text": "edited"}]},
        expected_head=snapshot.conversation.head_seq,
        expected_leaf=snapshot.conversation.leaf_event_id,
    )
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.start_turn({"kind": "agent"}, event_id=replacement.turn_id)
    messages = [{"role": "user", "content": "edited"}, {"role": "assistant", "content": "edited answer"}]
    if not display_first:
        await writer.save_history(messages)
    bot = await database.insert_platform_message_history(
        "webchat", "edited-session", {"type": "bot", "message": []}, turn_id=replacement.turn_id,
    )
    if display_first:
        await writer.save_history(messages)
    await writer.finish_turn("completed")
    linked = await database.get_platform_message_history_by_id(bot.id)
    assert linked.context_event_id
    later = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await later.append_message({"role": "user", "content": "later message"})
    branch = await store.create(umo=umo, platform_id="webchat", parent_event_id=linked.context_event_id)
    assert (await store.read(branch.conversation_id)).messages == messages
