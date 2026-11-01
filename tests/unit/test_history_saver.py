"""Append-only persistence for triggered conversation turns."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.utils.history_saver import persist_agent_history


@pytest.mark.asyncio
@pytest.mark.parametrize("completed", [False, True])
async def test_wakeup_history_keeps_every_existing_entry(completed):
    """Append actual messages while preserving checkpoints and unknown metadata.

    Args:
        completed: Whether the run produced a final assistant response.
    """
    history = [
        {"role": "user", "content": "Original", "metadata": {"retain": True}},
        {"role": "assistant", "content": "Answer"},
        {"role": "_checkpoint", "content": {"id": "checkpoint"}},
    ]
    original = json.dumps(history)
    conversation = SimpleNamespace(cid="conversation", history=original)
    manager = SimpleNamespace(update_conversation=AsyncMock())
    req = ProviderRequest(prompt="Current trigger", conversation=conversation)
    # Request preprocessing or compaction must never replace stored history.
    req.contexts = [{"role": "user", "content": "Compacted context"}]
    response = (
        LLMResponse(role="assistant", completion_text="Current result")
        if completed
        else None
    )

    await persist_agent_history(
        manager,
        event=SimpleNamespace(unified_msg_origin="test:FriendMessage:session"),
        req=req,
        response=response,
    )

    saved = manager.update_conversation.await_args.kwargs["history"]
    assert saved[: len(history)] == history
    assert saved[len(history)] == {"role": "user", "content": "Current trigger"}
    assert len(saved) == len(history) + 1 + int(completed)
    if completed:
        assert saved[-1] == {"role": "assistant", "content": "Current result"}
    assert conversation.history == original


@pytest.mark.asyncio
@pytest.mark.parametrize("history", ["{broken", "{}", "null"])
async def test_invalid_history_is_never_replaced(history):
    """Reject invalid history instead of silently overwriting it with a new turn.

    Args:
        history: Stored history that cannot be treated as a message list.
    """
    manager = SimpleNamespace(update_conversation=AsyncMock())
    req = ProviderRequest(
        prompt="Current trigger",
        conversation=SimpleNamespace(cid="conversation", history=history),
    )
    with pytest.raises(ValueError):
        await persist_agent_history(
            manager, event=SimpleNamespace(), req=req, response=None
        )
    manager.update_conversation.assert_not_awaited()
