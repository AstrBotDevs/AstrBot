"""Incremental writer projection, immutable acknowledgments, and retry recovery."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.conversation_events import (
    ConversationEventWriter,
    ConversationPersistenceError,
)
from astrbot.core.db import conversation as conversation_db
from astrbot.core.db.conversation import ConversationConflictError
from astrbot.core.db.sqlite import SQLiteDatabase


@pytest_asyncio.fixture
async def database(tmp_path):
    db = SQLiteDatabase(str(tmp_path / "writer.db"))
    await db.initialize()
    yield db
    await db.engine.dispose()


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
    assert all("json_each" in sql for sql in selects if "conversation_events" in sql)
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
            {"role": "user", "content": "journal only"}, include_in_context=False
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
    writer.request = SimpleNamespace(contexts=history)
    original_append = store.append

    async def stage_before_ack(*args, **kwargs):
        result = await original_append(*args, **kwargs)
        writer.request.contexts = late
        writer.stage_history(late, origin="plugin")
        return result

    with monkeypatch.context() as patch:
        patch.setattr(store, "append", stage_before_ack)
        await writer.save_history(history)
    assert writer.request.contexts == late
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
