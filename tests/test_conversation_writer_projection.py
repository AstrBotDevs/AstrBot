"""Incremental writer projection, immutable acknowledgments, and retry recovery."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.conversation_events import (
    ConversationEventWriter,
    ConversationPersistenceError,
)
from astrbot.core.db import conversation as conversation_db
from astrbot.core.db.conversation import ConversationConflictError


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [32, 128])
async def test_continuous_append_reads_no_old_context_and_copies_only_new_messages(
    database, monkeypatch, count
):
    store = database.conversation_store
    initial = [{"role": "user", "content": "old" * 1024}] * 64
    conv = await store.create(umo="owner", platform_id="p", content=initial)
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    entries = writer._committed_entries
    old_entry = entries[0]
    copied = []
    selects = []

    def track_copy(value):
        copied.append(deepcopy(value))
        return deepcopy(value)

    def track_select(_conn, _cursor, statement, _params, _ctx, _many):
        if statement.startswith("SELECT"):
            selects.append(statement)

    engine = database.engine.sync_engine
    event.listen(engine, "before_cursor_execute", track_select)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(
                store, "project", AsyncMock(side_effect=AssertionError("Full replay"))
            )
            patch.setattr(conversation_db, "deepcopy", track_copy)
            for index in range(count):
                message = {"role": "assistant", "content": str(index)}
                ack = await writer.append_message(message, event_id=f"message-{index}")
                assert writer._committed_entries is entries
                assert writer._entries is entries
                assert entries[0] is old_entry
                assert writer.leaf_event_id == ack.event_id
                message["content"] = "caller mutation"
                ack.payload["message"]["content"] = "ACK mutation"
    finally:
        event.remove(engine, "before_cursor_execute", track_select)

    # Per append: metadata and exact retry-ID lookup; no context range reads.
    assert len(selects) <= 2 * count
    assert all(
        "json_each" in sql or "json_array_elements_text" in sql
        for sql in selects
        if "conversation_events" in sql
    )
    assert copied == [{"role": "assistant", "content": str(i)} for i in range(count)]
    restored = await store.read(conv.conversation_id)
    assert writer._entries == restored.entries
    assert writer.replay_from_event_id == restored.conversation.replay_from_event_id
    assert writer.head_seq == restored.conversation.head_seq


@pytest.mark.asyncio
async def test_rebases_and_excluded_messages_match_persisted_projection(
    database, monkeypatch
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    with monkeypatch.context() as patch:
        patch.setattr(
            store, "project", AsyncMock(side_effect=AssertionError("Full replay"))
        )
        await writer.append_message({"role": "user", "content": "old"}, event_id="old")
        await store.append(
            conv.conversation_id, [{"type": "plugin.test.observed", "payload": {}}]
        )
        await writer.append_message(
            {"role": "user", "content": "journal only", "_no_save": True}
        )
        await writer.append_message(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "keep"},
                    {"type": "text", "text": "temporary", "_no_save": True},
                ],
            },
            event_id="parts",
        )
        assert writer._entries[-1]["message"]["content"] == [
            {"type": "text", "text": "keep"}
        ]
        await writer.append(
            "context.rebased",
            {"reason": "reset", "origin": "user", "messages": []},
            event_id="reset",
        )
        assert writer._entries == []
        await writer.append(
            "context.rebased",
            {
                "reason": "snapshot",
                "origin": "user",
                "messages": [
                    {"id": "retained", "message": {"role": "user", "content": "forked"}}
                ],
            },
            event_id="baseline",
        )
        await writer.append_message(
            {"role": "assistant", "content": "new"}, event_id="new"
        )
    restored = await store.read(conv.conversation_id)
    assert writer._entries == restored.entries
    assert writer.replay_from_event_id == "baseline"
    assert writer._context_seq == restored.context_seq
    fork = await store.create(umo="owner", platform_id="p", source_event_id="parts")
    assert (await store.read(fork.conversation_id)).messages == [
        {"role": "user", "content": "old"},
        {"role": "user", "content": [{"type": "text", "text": "keep"}]},
    ]


@pytest.mark.asyncio
async def test_transaction_failure_keeps_staged_work_unconfirmed(database, monkeypatch):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    writer.stage_history([{"role": "user", "content": "staged"}])
    staged_ids = [draft["event_id"] for draft in writer._pending]
    before = (writer.head_seq, writer.leaf_event_id, writer.replay_from_event_id)
    with monkeypatch.context() as patch:
        patch.setattr(
            conversation_db,
            "project_webchat_event_links",
            AsyncMock(side_effect=SQLAlchemyError("failed before commit")),
        )
        with pytest.raises(ConversationPersistenceError):
            await writer.append_message(
                {"role": "assistant", "content": "reply"}, event_id="reply"
            )
    assert writer._committed_entries == []
    assert writer._entries == [
        {"id": staged_ids[0], "message": {"role": "user", "content": "staged"}}
    ]
    assert (
        writer.head_seq,
        writer.leaf_event_id,
        writer.replay_from_event_id,
    ) == before
    assert (await store.read(conv.conversation_id)).messages == []
    assert [draft["event_id"] for draft in writer._pending] == staged_ids
    await writer.append_message(
        {"role": "assistant", "content": "reply"}, event_id="reply"
    )
    assert writer._committed_entries == (await store.read(conv.conversation_id)).entries
    assert [entry["id"] for entry in writer._entries] == [*staged_ids, "reply"]
    assert not writer._pending


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy_snapshot", [False, True])
async def test_lost_ack_retry_updates_context_even_after_execution_head_advances(
    database, monkeypatch, legacy_snapshot
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    writer.stage_history([{"role": "user", "content": "staged"}])
    original_append = store.append
    message = {"role": "assistant", "content": "reply"}

    async def lose_ack(*args, **kwargs):
        await original_append(*args, **kwargs)
        raise SQLAlchemyError("ACK lost")

    with monkeypatch.context() as patch:
        patch.setattr(store, "append", lose_ack)
        with pytest.raises(ConversationPersistenceError):
            await writer.append_message(message, event_id="reply")
    assert writer._committed_entries == []
    assert writer.leaf_event_id is None
    assert writer._pending
    baseline_id = None
    if legacy_snapshot:
        snapshot = await store.read(conv.conversation_id)
        result = await original_append(
            conv.conversation_id,
            [
                {
                    "type": "context.rebased",
                    "payload": {
                        "reason": "snapshot",
                        "origin": "system",
                        "source_event_id": "reply",
                        "messages": snapshot.entries,
                    },
                }
            ],
        )
        baseline_id = result.events[0].event_id
    await writer.append("plugin.test.observed", {})
    execution_head = writer.head_seq
    project = AsyncMock(wraps=store.project)
    with monkeypatch.context() as patch:
        patch.setattr(store, "project", project)
        await writer.append_message(message, event_id="reply")
        assert project.await_count == (0 if legacy_snapshot else 1)
        await writer.append_message(message, event_id="reply")
        assert project.await_count == (0 if legacy_snapshot else 1)
    assert writer.head_seq == execution_head
    assert writer.leaf_event_id == (baseline_id or "reply")
    assert writer.replay_from_event_id == baseline_id
    assert len(writer._entries) == 2
    assert not writer._pending
    await writer.append_message(
        {"role": "assistant", "content": "next"}, event_id="next"
    )
    assert writer._entries == (await store.read(conv.conversation_id)).entries
    current_head, current_leaf = writer.head_seq, writer.leaf_event_id
    await writer.append_message(message, event_id="reply")
    assert (writer.head_seq, writer.leaf_event_id) == (current_head, current_leaf)
    assert writer._entries == (await store.read(conv.conversation_id)).entries
    with pytest.raises(ConversationConflictError):
        await writer.append_message(
            {"role": "assistant", "content": "different"}, event_id="reply"
        )
    assert (writer.head_seq, writer.leaf_event_id) == (current_head, current_leaf)


@pytest.mark.asyncio
async def test_unseen_retry_recovers_exact_ack_tip_and_preserves_later_conflicts(
    database, monkeypatch
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    other = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await other.append_message(
        {"role": "user", "content": "intervening"}, event_id="gap"
    )
    target = {"role": "assistant", "content": "target"}
    await other.append_message(target, event_id="target")
    await other.append_message(
        {"role": "assistant", "content": "later"}, event_id="later"
    )
    await writer.append("plugin.test.observed", {})
    head = writer.head_seq
    before = (writer.leaf_event_id, writer._context_seq, writer.replay_from_event_id)
    with monkeypatch.context() as patch:
        patch.setattr(
            store, "project", AsyncMock(side_effect=SQLAlchemyError("read failed"))
        )
        with pytest.raises(SQLAlchemyError):
            await writer.append_message(target, event_id="target")
    assert writer._committed_entries == []
    assert (
        writer.leaf_event_id,
        writer._context_seq,
        writer.replay_from_event_id,
    ) == before
    await writer.append_message(target, event_id="target")
    assert [entry["id"] for entry in writer._entries] == ["gap", "target"]
    assert writer.head_seq == head
    before_entries = deepcopy(writer._entries)
    with pytest.raises(ConversationConflictError):
        await writer.append_message({"role": "assistant", "content": "stale"})
    assert writer._entries == before_entries
    assert writer.leaf_event_id == "target"


@pytest.mark.asyncio
async def test_save_history_lost_ack_keeps_metadata_event_identity(
    database, monkeypatch
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    original_append = store.append
    history = [{"role": "user", "content": "input"}]

    async def lose_ack(*args, **kwargs):
        await original_append(*args, **kwargs)
        raise SQLAlchemyError("ACK lost")

    with monkeypatch.context() as patch:
        patch.setattr(store, "append", lose_ack)
        with pytest.raises(SQLAlchemyError):
            await writer.save_history(history, token_usage=42)
    pending_ids = [draft["event_id"] for draft in writer._pending]
    assert len(pending_ids) == 2
    assert writer._committed_entries == []
    await writer.save_history(history, token_usage=42)
    assert writer._entries == (await store.read(conv.conversation_id)).entries
    assert [
        event.event_id for event in (await store.events(conv.conversation_id))[1:]
    ] == pending_ids
    assert (
        await database.get_conversation_by_id(conv.conversation_id)
    ).token_usage == 42
    assert not writer._pending


@pytest.mark.asyncio
async def test_staging_during_commit_remains_pending(database, monkeypatch):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    original_append = store.append
    late = {"role": "user", "content": "staged during await"}
    committed = {"role": "assistant", "content": "committed"}

    async def stage_before_ack(*args, **kwargs):
        result = await original_append(*args, **kwargs)
        writer.stage_history([late])
        return result

    with monkeypatch.context() as patch:
        patch.setattr(store, "append", stage_before_ack)
        await writer.append_message(committed)
    assert [entry["message"] for entry in writer._committed_entries] == [committed]
    assert [entry["message"] for entry in writer._entries] == [committed, late]
    assert len(writer._pending) == 1
    await writer.save_history([committed, late])
    assert writer._entries == (await store.read(conv.conversation_id)).entries
    assert not writer._pending


@pytest.mark.asyncio
async def test_historical_projection_tracks_leaf_sequence_separately_from_head(
    database,
):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    owner = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await owner.append_message({"role": "user", "content": "first"}, event_id="first")
    target = {"role": "assistant", "content": "second"}
    await owner.append_message(target, event_id="second")
    current = await store.read(conv.conversation_id)
    async with database.get_db() as session:
        historical = await store.project(session, current.conversation, "first")
    writer = ConversationEventWriter(store, historical)
    assert writer.head_seq > writer._context_seq
    await writer.append_message(target, event_id="second")
    assert writer._entries == current.entries


@pytest.mark.asyncio
async def test_save_ack_does_not_overwrite_later_hook_work(database, monkeypatch):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    history = [{"role": "user", "content": "committed"}]
    late = [{"role": "user", "content": "hook replacement"}]
    request = SimpleNamespace(contexts=history)
    original_append = store.append

    async def stage_before_ack(*args, **kwargs):
        result = await original_append(*args, **kwargs)
        request.contexts = late
        writer.stage_history(late, origin="plugin")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(store, "append", stage_before_ack)
        await writer.save_history(history)
    assert request.contexts == late
    assert [entry["message"] for entry in writer._committed_entries] == history
    assert [entry["message"] for entry in writer._entries] == late
    assert writer._pending
    await writer.save_history(late)
    assert writer._entries == (await store.read(conv.conversation_id)).entries
    assert not writer._pending


@pytest.mark.asyncio
async def test_failed_turn_discards_only_uncommitted_work(database):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    await writer.start_turn({"kind": "test"})
    await writer.append_message({"role": "user", "content": "committed"})
    writer.stage_history([{"role": "user", "content": "uncommitted"}])
    await writer.finish_turn("failed")
    assert writer.closed
    assert not writer._pending
    assert writer._entries is writer._committed_entries
    assert writer._entries == (await store.read(conv.conversation_id)).entries


@pytest.mark.asyncio
async def test_staged_deltas_keep_committed_state_and_temporary_records(
    database, monkeypatch
):
    store = database.conversation_store
    old = {"role": "user", "content": "existing history"}
    conv = await store.create(umo="owner", platform_id="p", content=[old] * 100)
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    committed = writer._committed_entries
    original = conversation_db.reconcile_history
    compared_lengths = []

    def reconcile(entries, history, **kwargs):
        compared_lengths.append(len(entries))
        return original(entries, history, **kwargs)

    monkeypatch.setattr(
        "astrbot.core.agent.conversation_events.reconcile_history", reconcile
    )
    temporary = {"role": "user", "content": "temporary", "_no_save": True}
    expected = [old] * 100
    for index in range(20):
        message = {"role": "assistant", "content": str(index)}
        writer.stage_messages([message, temporary])
        expected.extend([deepcopy(message), temporary])
        message["content"] = "caller mutation"
    assert compared_lengths == [0] * 20
    assert len(committed) == 100
    assert writer._committed_entries is committed
    assert writer._entries[0] is committed[0]
    detached = writer.get_messages()
    detached[0]["content"] = "caller mutation"
    detached.clear()
    assert writer.get_messages()[0] == old
    await writer.save_history(expected)
    records = await store.events(conv.conversation_id, event_type="message.appended")
    excluded = [e for e in records if e.payload.get("message", {}).get("_no_save") is True]
    assert len(excluded) == 20
    assert writer.get_messages() == (await store.read(conv.conversation_id)).messages
    assert len(writer.get_messages()) == 120


@pytest.mark.asyncio
@pytest.mark.parametrize("batch_size", [2, 100])
@pytest.mark.parametrize("duplicate_finish", [False, True])
async def test_lifecycle_batch_validates_unflushed_references_atomically(
    database, monkeypatch, batch_size, duplicate_finish
):
    monkeypatch.setattr(conversation_db, "EVENT_INSERT_BATCH_ROWS", batch_size)
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    drafts = [
        {"event_id": "turn", "type": "turn.started", "payload": {}},
        {
            "event_id": "request",
            "type": "request.started",
            "payload": {"turn_id": "turn"},
        },
        {
            "event_id": "response",
            "type": "request.finished",
            "payload": {"request_id": "request", "status": "completed"},
        },
        {
            "event_id": "done",
            "type": "turn.finished",
            "payload": {"turn_id": "turn", "status": "completed"},
        },
    ]
    if duplicate_finish:
        drafts.append({**drafts[2], "event_id": "duplicate"})
        with pytest.raises(conversation_db.ConversationConflictError):
            await store.append(conv.conversation_id, drafts)
        assert [record.type for record in await store.events(conv.conversation_id)] == [
            "conversation.created"
        ]
    else:
        result = await store.append(conv.conversation_id, drafts)
        assert [record.event_id for record in result.events] == [
            draft["event_id"] for draft in drafts
        ]
        retry = await store.append(conv.conversation_id, drafts)
        assert retry.replayed


@pytest.mark.asyncio
async def test_execution_load_reuses_projection_without_sharing_plugin_mutations(
    database, monkeypatch
):
    from astrbot.core.conversation_mgr import ConversationManager

    store = database.conversation_store
    conv = await store.create(
        umo="owner", platform_id="p", content=[{"role": "user", "content": "before"}]
    )
    await database.update_conversation(conv.conversation_id, token_usage=123)
    project = AsyncMock(wraps=store.project)
    monkeypatch.setattr(store, "project", project)
    record, snapshot = await store.read_for_execution(conv.conversation_id)
    assert record.token_usage == 123
    manager = ConversationManager(database)
    writer = await manager.create_event_writer(
        conv.conversation_id,
        unified_msg_origin="owner",
        expected_revision=record.revision,
        snapshot=snapshot,
    )
    assert project.await_count == 1
    record.content[0]["content"] = "plugin edit"
    assert writer.get_messages() == [{"role": "user", "content": "before"}]
    await store.append(
        conv.conversation_id, [], history=[{"role": "user", "content": "external edit"}]
    )
    with pytest.raises(ConversationConflictError):
        await manager.create_event_writer(conv.conversation_id, snapshot=snapshot)


@pytest.mark.asyncio
async def test_existing_session_reads_do_not_hold_runtime_registry_lock(
    database, monkeypatch
):
    import asyncio

    from astrbot.core.astr_agent_runtime import AstrAgentRuntime

    store = database.conversation_store
    first = await store.create(umo="first", platform_id="p")
    second = await store.create(umo="second", platform_id="p")
    runtime = AstrAgentRuntime(
        SimpleNamespace(conversation_manager=SimpleNamespace(db=database)),
        agent_configs=None,
        subagents=None,
    )
    entered, release = asyncio.Event(), asyncio.Event()
    get_metadata = store.get_metadata

    async def delayed(cid):
        if cid == first.conversation_id:
            entered.set()
            await release.wait()
        return await get_metadata(cid)

    monkeypatch.setattr(store, "get_metadata", delayed)
    pending = asyncio.create_task(
        runtime.open_session("first", session_id=first.conversation_id)
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        other = await asyncio.wait_for(
            runtime.open_session("second", session_id=second.conversation_id), 2
        )
        assert other.umo == "second" and not pending.done()
        assert (
            await runtime.open_session("second", session_id=second.conversation_id)
            is other
        )
    finally:
        release.set()
        await pending
        await runtime.close()


@pytest.mark.asyncio
async def test_concurrent_first_inputs_create_one_main_session(database):
    import asyncio

    from astrbot.core.astr_agent_runtime import AstrAgentRuntime

    selected = None
    creations = 0

    async def current(umo):
        await asyncio.sleep(0)
        return selected

    async def create(umo, **kwargs):
        nonlocal selected, creations
        creations += 1
        row = await database.conversation_store.create(umo=umo, platform_id="p")
        await asyncio.sleep(0)
        selected = row.conversation_id
        return selected

    runtime = AstrAgentRuntime(
        SimpleNamespace(
            conversation_manager=SimpleNamespace(
                db=database,
                get_curr_conversation_id=current,
                new_conversation=create,
            )
        ),
        agent_configs=None,
        subagents=None,
    )
    try:
        first, second = await asyncio.gather(
            runtime.open_session("owner"), runtime.open_session("owner")
        )
        assert first is second
        assert creations == 1
    finally:
        await runtime.close()
