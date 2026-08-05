"""Tests for acceptance-gated assistant conversation history."""

from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.assistant_history import (
    AssistantHistoryCommitter,
    build_pending_assistant_history,
    make_projection,
)
from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
from astrbot.core.platform.send_result import DeliveryAttempt, DeliveryReceipt
from astrbot.core.star.register import register_on_assistant_history_finalized
from astrbot.core.star.register.star_handler import get_handler_declaration
from astrbot.core.star.star_handler import EventType


def _pending(sequence: int) -> object:
    return build_pending_assistant_history(
        unified_msg_origin="test:private:1",
        conversation_id="conversation-1",
        history_snapshot=[{"role": "user", "content": "question"}],
        token_usage=7,
        assistant_semantic_output="model-only text",
        checkpoint_id="checkpoint-1",
        run_id=f"run-{sequence}",
        sequence=sequence,
    )


@pytest.mark.asyncio
async def test_projection_commits_only_accepted_text_after_pending_created():
    manager = SimpleNamespace(update_conversation=AsyncMock())
    pending = _pending(1)
    receipt = DeliveryReceipt.aggregate(
        [DeliveryAttempt(status="accepted", semantic_text="accepted text")]
    )

    committed = await AssistantHistoryCommitter().commit(
        manager,
        pending,
        make_projection(receipt),
    )

    assert committed is True
    manager.update_conversation.assert_awaited_once()
    history = manager.update_conversation.await_args.kwargs["history"]
    assert history == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "accepted text"},
        {"role": "_checkpoint", "content": {"id": "checkpoint-1"}},
    ]
    with pytest.raises(TypeError):
        pending.history_snapshot[0]["content"] = "mutated"  # type: ignore[index]


@pytest.mark.asyncio
async def test_failed_or_unknown_receipts_do_not_commit_history():
    manager = SimpleNamespace(update_conversation=AsyncMock())
    committer = AssistantHistoryCommitter()
    for status in ("failed", "unknown", "skipped"):
        receipt = DeliveryReceipt.aggregate([DeliveryAttempt(status=status)])
        assert (
            await committer.commit(manager, _pending(1), make_projection(receipt))
            is False
        )

    manager.update_conversation.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_concurrent_snapshot_cannot_overwrite_newer_commit():
    manager = SimpleNamespace(update_conversation=AsyncMock())
    committer = AssistantHistoryCommitter()
    receipt = DeliveryReceipt.aggregate(
        [DeliveryAttempt(status="accepted", semantic_text="visible")]
    )

    assert await committer.commit(manager, _pending(2), make_projection(receipt))
    assert not await committer.commit(manager, _pending(1), make_projection(receipt))
    assert manager.update_conversation.await_count == 1


@pytest.mark.asyncio
async def test_finalized_event_runs_after_commit_and_is_read_only(monkeypatch):
    manager = SimpleNamespace(update_conversation=AsyncMock())
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = manager
    stage.ctx = SimpleNamespace(
        execution_context=SimpleNamespace(
            assistant_history_committer=AssistantHistoryCommitter(),
            persona_runtime_manager=None,
            memory_manager=None,
        ),
        handlers=SimpleNamespace(),
        plugins=SimpleNamespace(),
    )
    receipt = DeliveryReceipt.aggregate(
        [DeliveryAttempt(status="accepted", semantic_text="visible")]
    )
    event = SimpleNamespace(
        _extras={"delivery_receipt": receipt},
        get_extra=lambda key, default=None: event._extras.get(key, default),
        set_extra=lambda key, value: event._extras.__setitem__(key, value),
        get_platform_id=lambda: "test",
    )
    observed = []

    async def observe(_event, _event_type, finalized, **_kwargs):
        assert manager.update_conversation.await_count == 1
        observed.append(finalized)

    monkeypatch.setattr(internal, "call_event_hook", observe)
    await stage._finalize_pending_history(event, SimpleNamespace(), _pending(1))

    assert observed[0].history_committed is True
    with pytest.raises(FrozenInstanceError):
        observed[0].history_committed = False


@pytest.mark.asyncio
async def test_finalized_event_observes_failed_receipt_without_commit(monkeypatch):
    manager = SimpleNamespace(update_conversation=AsyncMock())
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.conv_manager = manager
    stage.ctx = SimpleNamespace(
        execution_context=SimpleNamespace(
            assistant_history_committer=AssistantHistoryCommitter(),
            persona_runtime_manager=None,
            memory_manager=None,
        ),
        handlers=SimpleNamespace(),
        plugins=SimpleNamespace(),
    )
    receipt = DeliveryReceipt.aggregate([DeliveryAttempt(status="failed")])
    event = SimpleNamespace(
        _extras={"delivery_receipt": receipt},
        get_extra=lambda key, default=None: event._extras.get(key, default),
        set_extra=lambda key, value: event._extras.__setitem__(key, value),
        get_platform_id=lambda: "test",
    )
    observed = []

    async def observe(_event, _event_type, finalized, **_kwargs):
        observed.append(finalized)

    monkeypatch.setattr(internal, "call_event_hook", observe)
    await stage._finalize_pending_history(event, SimpleNamespace(), _pending(1))

    manager.update_conversation.assert_not_awaited()
    assert observed[0].receipt.status == "failed"
    assert observed[0].history_committed is False


def test_finalized_event_has_a_dedicated_plugin_registration():
    @register_on_assistant_history_finalized()
    async def handler(_event, _finalized):
        return None

    declaration = get_handler_declaration(
        handler,
        EventType.OnAssistantHistoryFinalized,
    )

    assert declaration.event_type is EventType.OnAssistantHistoryFinalized
