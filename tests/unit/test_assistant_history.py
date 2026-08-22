from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.assistant_history import (
    AssistantHistoryCommitter,
    build_pending_assistant_history,
    make_projection,
)
from astrbot.core.platform.send_result import DeliveryAttempt, DeliveryReceipt


def _pending(
    *,
    sequence: int = 1,
    snapshot: list[dict] | None = None,
    base_history: list[dict] | None = None,
    unit_start: int | None = None,
    expected_total: int | None = None,
    checkpoint_id: str | None = None,
):
    return build_pending_assistant_history(
        unified_msg_origin="aiocqhttp:GroupMessage:g1",
        conversation_id="conversation-1",
        history_snapshot=snapshot or [{"role": "user", "content": "question"}],
        token_usage=7,
        assistant_semantic_output="model-only text",
        checkpoint_id=checkpoint_id,
        run_id=f"run-{sequence}",
        sequence=sequence,
        base_history=base_history,
        unit_start=unit_start,
        expected_total=expected_total,
    )


def _accepted(text: str = "accepted text") -> object:
    return make_projection(
        DeliveryReceipt.aggregate(
            [DeliveryAttempt(status="accepted", semantic_text=text)]
        )
    )


@pytest.mark.asyncio
async def test_commit_without_merge_matches_today():
    manager = SimpleNamespace(update_conversation=AsyncMock())
    pending = _pending()
    committed = await AssistantHistoryCommitter().commit(manager, pending, _accepted())
    assert committed is True
    history = manager.update_conversation.await_args.kwargs["history"]
    assert history == [
        {"role": "user", "content": "question"},
        {"role": "assistant", "content": "accepted text"},
    ]
    manager.get_conversation = AsyncMock()
    manager.get_conversation.assert_not_called()


@pytest.mark.asyncio
async def test_stale_sequence_still_skipped_when_merge_enabled():
    manager = SimpleNamespace(
        update_conversation=AsyncMock(),
        get_conversation=AsyncMock(),
    )
    committer = AssistantHistoryCommitter()
    base = [{"role": "user", "content": "old"}]
    first = _pending(sequence=2, base_history=base, unit_start=0, expected_total=2)
    second = _pending(sequence=1, base_history=base, unit_start=0, expected_total=2)
    assert await committer.commit(manager, first, _accepted("newer"))
    assert not await committer.commit(manager, second, _accepted("older"))
    assert manager.update_conversation.await_count == 1


@pytest.mark.asyncio
async def test_no_receipt_does_not_commit_even_with_merge_fields():
    manager = SimpleNamespace(update_conversation=AsyncMock())
    pending = _pending(
        base_history=[{"role": "user", "content": "q"}],
        unit_start=0,
        expected_total=2,
    )
    assert (
        await AssistantHistoryCommitter().commit(
            manager,
            pending,
            make_projection(
                DeliveryReceipt.aggregate([DeliveryAttempt(status="failed")])
            ),
        )
        is False
    )
    manager.update_conversation.assert_not_called()


@pytest.mark.asyncio
async def test_merge_keeps_other_sender_complete_turn():
    base: list[dict] = []
    written_a = [
        {"role": "user", "content": "from-a"},
        {"role": "assistant", "content": "a-answer"},
    ]
    manager = SimpleNamespace(
        update_conversation=AsyncMock(),
        get_conversation=AsyncMock(
            side_effect=[
                SimpleNamespace(history=base),
                SimpleNamespace(history=written_a),
            ]
        ),
    )
    committer = AssistantHistoryCommitter()
    await committer.commit(
        manager,
        _pending(
            sequence=1,
            snapshot=[{"role": "user", "content": "from-a"}],
            base_history=base,
            unit_start=0,
            expected_total=2,
        ),
        _accepted("a-answer"),
    )
    await committer.commit(
        manager,
        _pending(
            sequence=2,
            snapshot=[{"role": "user", "content": "from-b"}],
            base_history=base,
            unit_start=0,
            expected_total=2,
        ),
        _accepted("b-answer"),
    )
    history = manager.update_conversation.await_args.kwargs["history"]
    assert history == [
        *written_a,
        {"role": "user", "content": "from-b"},
        {"role": "assistant", "content": "b-answer"},
    ]
    assert manager.update_conversation.await_args.kwargs["token_usage"] == 0


@pytest.mark.asyncio
async def test_truncated_latest_does_not_resurrect_long_base():
    long_base = [{"role": "user", "content": f"old-{i}"} for i in range(20)]
    truncated = [{"role": "user", "content": "summary"}]
    after_first = [
        {"role": "user", "content": "summary"},
        {"role": "assistant", "content": "first"},
    ]
    manager = SimpleNamespace(
        update_conversation=AsyncMock(),
        get_conversation=AsyncMock(
            side_effect=[
                SimpleNamespace(history=truncated),
                SimpleNamespace(history=after_first),
            ]
        ),
    )
    committer = AssistantHistoryCommitter()
    await committer.commit(
        manager,
        _pending(
            sequence=1,
            snapshot=truncated,
            base_history=truncated,
            unit_start=0,
            expected_total=2,
        ),
        _accepted("first"),
    )
    pending = _pending(
        sequence=2,
        snapshot=[{"role": "user", "content": "now"}],
        base_history=long_base,
        unit_start=0,
        expected_total=2,
    )
    await committer.commit(manager, pending, _accepted("now-answer"))
    history = manager.update_conversation.await_args.kwargs["history"]
    assert history[0] == {"role": "user", "content": "summary"}
    assert {"role": "user", "content": "old-0"} not in history
    assert history[-2:] == [
        {"role": "user", "content": "now"},
        {"role": "assistant", "content": "now-answer"},
    ]


@pytest.mark.asyncio
async def test_missing_anchor_uses_new_history():
    manager = SimpleNamespace(
        update_conversation=AsyncMock(),
        get_conversation=AsyncMock(
            return_value=SimpleNamespace(history=[{"role": "user", "content": "other"}])
        ),
    )
    pending = _pending(
        snapshot=[{"role": "assistant", "content": "tool-only"}],
        base_history=[{"role": "user", "content": "base"}],
        unit_start=None,
        expected_total=2,
    )
    await AssistantHistoryCommitter().commit(manager, pending, _accepted("x"))
    history = manager.update_conversation.await_args.kwargs["history"]
    assert history[-1]["content"] == "x"
    assert history[0]["role"] == "assistant"
