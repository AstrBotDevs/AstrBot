"""Incremental writer projection, immutable acknowledgments, and retry recovery."""

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import SQLAlchemyError

from astrbot.core.agent.conversation_events import (
    ConversationEventWriter,
    ConversationPersistenceError,
)
from astrbot.core.db import conversation as conversation_db
from astrbot.core.db.conversation import ConversationConflictError


@pytest.mark.asyncio
async def test_continuous_append_updates_context_without_full_replay(
    database, monkeypatch
):
    store = database.conversation_store
    initial = [{"role": "user", "content": "old" * 1024}] * 64
    conv = await store.create(umo="owner", platform_id="p", content=initial)
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    expected = initial + [{"role": "assistant", "content": str(i)} for i in range(32)]
    with monkeypatch.context() as patch:
        patch.setattr(
            store, "project", AsyncMock(side_effect=AssertionError("Full replay"))
        )
        for index in range(32):
            message = {"role": "assistant", "content": str(index)}
            ack = await writer.append_message(message, event_id=f"message-{index}")
            message["content"] = "caller mutation"
            ack.payload["message"]["content"] = "ACK mutation"
    assert (
        writer.get_messages()
        == (await store.read(conv.conversation_id)).messages
        == expected
    )


@pytest.mark.asyncio
async def test_transaction_failure_keeps_staged_work_unconfirmed(database, monkeypatch):
    store = database.conversation_store
    conv = await store.create(umo="owner", platform_id="p")
    writer = ConversationEventWriter(store, await store.read(conv.conversation_id))
    writer.stage_history([{"role": "user", "content": "staged"}])
    staged_ids = [draft["event_id"] for draft in writer._pending]
    before = (writer.head_seq, writer.leaf_event_id)
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
