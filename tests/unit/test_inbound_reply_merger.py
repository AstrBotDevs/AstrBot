"""Tests for session-scoped private inbound reply consolidation."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal import (
    _INBOUND_MERGE_MAX_AGE_SECONDS,
    _InboundReplyMerger,
    _merge_inbound_prompt,
)
from astrbot.core.platform.message_type import MessageType


def build_event(umo: str, text: str, timestamp: float):
    """Build the event surface used by the inbound merger."""
    extras = {}
    event = SimpleNamespace(
        unified_msg_origin=umo,
        created_at=timestamp,
        message_str=text,
        message_obj=SimpleNamespace(timestamp=timestamp, message=[], message_str=text),
        get_extra=Mock(side_effect=lambda key, default=None: extras.get(key, default)),
        set_extra=Mock(side_effect=lambda key, value: extras.__setitem__(key, value)),
        get_message_type=Mock(return_value=MessageType.FRIEND_MESSAGE),
        get_platform_name=Mock(return_value="aiocqhttp"),
        get_message_str=Mock(return_value=text),
        get_message_outline=Mock(return_value=text),
    )
    event.extras = extras
    return event


def test_newest_event_claims_one_same_session_batch(monkeypatch):
    """Only the newest queued event may reply for a session."""
    merger = _InboundReplyMerger()
    monkeypatch.setattr(
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.time",
        lambda: 1_000.0,
    )
    first = build_event("Perrin:FriendMessage:1", "第一条", 999.0)
    second = build_event("Perrin:FriendMessage:1", "第二条", 999.5)

    assert merger.register(first)
    assert merger.register(second)
    assert merger.decide(first, now=1_000.0).action == "superseded"
    decision = merger.decide(second, now=1_000.0)

    assert decision.action == "ready"
    assert [item.text for item in decision.messages] == ["第一条", "第二条"]
    prompt = _merge_inbound_prompt(decision.messages)
    assert "只回复一次" in prompt
    assert "1. 第一条" in prompt
    assert "2. 第二条" in prompt


def test_sessions_never_share_pending_messages(monkeypatch):
    """Messages from different contacts remain in separate batches."""
    merger = _InboundReplyMerger()
    monkeypatch.setattr(
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.time",
        lambda: 2_000.0,
    )
    left = build_event("Perrin:FriendMessage:1", "甲", 1_999.0)
    right = build_event("Perrin:FriendMessage:2", "乙", 1_999.0)

    assert merger.register(left)
    assert merger.register(right)

    assert [item.text for item in merger.decide(left, now=2_000.0).messages] == ["甲"]
    assert [item.text for item in merger.decide(right, now=2_000.0).messages] == ["乙"]


def test_stale_backlog_is_dropped(monkeypatch):
    """An old QQ message must not start a much later model response."""
    merger = _InboundReplyMerger()
    now = 3_000.0
    monkeypatch.setattr(
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.time",
        lambda: now,
    )
    event = build_event(
        "Perrin:FriendMessage:1",
        "旧消息",
        now - _INBOUND_MERGE_MAX_AGE_SECONDS - 1,
    )

    assert merger.register(event)
    decision = merger.decide(event, now=now)

    assert decision.action == "stale"
    assert len(decision.messages) == 1


def test_commands_are_not_merged():
    """Private commands preserve immediate command routing semantics."""
    merger = _InboundReplyMerger()
    event = build_event("Perrin:FriendMessage:1", "/help", 1_000.0)

    assert not merger.register(event)


def test_oversized_latest_message_is_kept_instead_of_older_input(monkeypatch):
    """Keep the newest message within the budget and disclose truncation.

    Args:
        monkeypatch: Scoped clock replacement.
    """
    monkeypatch.setattr(
        "astrbot.core.pipeline.process_stage.method.agent_sub_stages.internal.time",
        lambda: 1000.0,
    )
    merger = _InboundReplyMerger()
    old = build_event("p:1", "older input", 999.0)
    latest = build_event("p:1", "LATEST " + "x" * 6500, 1000.0)
    merger.register(old)
    merger.register(latest)
    prompt = _merge_inbound_prompt(merger.decide(latest, now=1000).messages)
    assert "LATEST " in prompt
    assert "older input" not in prompt
    assert "最新消息过长" in prompt
    assert len(prompt.split("\n", 1)[1]) <= 6003


def test_state_budget_preserves_active_queues_and_cooldowns(monkeypatch):
    """Bound retained sessions without evicting pending work or live cooldowns.

    Args:
        monkeypatch: Scoped clock and state-budget replacements.
    """
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal

    now = [1000.0]
    monkeypatch.setattr(internal, "time", lambda: now[0])
    monkeypatch.setattr(internal, "_INBOUND_MERGE_MAX_STATES", 2)
    merger = _InboundReplyMerger()
    a, b, c = [build_event("p:" + key, key, now[0]) for key in "abc"]
    assert merger.register(a) and merger.register(b)
    assert not merger.register(c)
    assert len(merger._states) == 2
    assert merger.decide(a, now=now[0]).action == "ready"
    now[0] += 1
    assert not merger.register(c)  # The first session is still cooling down.
    now[0] += 14
    assert merger.register(c)
    assert set(merger._states) == {"p:b", "p:c"}
    assert merger.decide(b, now=now[0]).messages[0].text == "b"


def test_evicted_state_cannot_reuse_an_old_event_sequence(monkeypatch):
    """Old handlers must not claim a newly created queue for the same UMO.

    Args:
        monkeypatch: Scoped clock replacement.
    """
    from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal

    now = [1000.0]
    monkeypatch.setattr(internal, "time", lambda: now[0])
    merger = _InboundReplyMerger()
    old = build_event("p:1", "old", 1000)
    merger.register(old)
    merger.decide(old, now=now[0])
    now[0] = 1020
    new = build_event("p:1", "new", 1020)
    merger.register(new)
    assert merger.decide(old, now=now[0]).action == "superseded"
    assert merger.decide(new, now=now[0]).messages[0].text == "new"


@pytest.mark.asyncio
async def test_cancel_while_waiting_removes_only_that_message(monkeypatch):
    """Canceled queued input must not reappear in a later model request.

    Args:
        monkeypatch: Scoped merger, hooks and clock replacements.
    """
    import asyncio
    from unittest.mock import AsyncMock

    from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal
    from astrbot.core.utils.session_lock import SessionLockManager

    merger = _InboundReplyMerger()
    manager = SessionLockManager()
    monkeypatch.setattr(internal, "_inbound_reply_merger", merger)
    monkeypatch.setattr(internal, "session_lock_manager", manager)
    monkeypatch.setattr(internal, "time", lambda: 1000.0)
    monkeypatch.setattr(internal, "try_capture_follow_up", Mock(return_value=None))
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    event = build_event("p:1", "canceled input", 1000)
    event.is_stopped = Mock(return_value=False)
    registered = asyncio.Event()
    original_set = event.set_extra
    event.set_extra = Mock(
        side_effect=lambda key, value: (
            original_set(key, value),
            registered.set() if key == "_inbound_merge_sequence" else None,
        )
    )
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_reasoning = False

    async def run_stage():
        """Drain the pipeline until canceled by the test."""
        async for _ in stage.process(event, ""):
            pass

    async with manager.acquire_lock("p:1"):
        task = asyncio.create_task(run_stage())
        await asyncio.wait_for(registered.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert "p:1" not in merger._states
    new = build_event("p:1", "fresh input", 1000)
    merger.register(new)
    assert [m.text for m in merger.decide(new, now=1000).messages] == ["fresh input"]


@pytest.mark.asyncio
async def test_stopped_after_registration_does_not_keep_pending_input(monkeypatch):
    """A stopped queued event is removed before another request can merge it.

    Args:
        monkeypatch: Scoped merger, hooks and clock replacements.
    """
    from unittest.mock import AsyncMock

    from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal

    merger = _InboundReplyMerger()
    monkeypatch.setattr(internal, "_inbound_reply_merger", merger)
    monkeypatch.setattr(internal, "time", lambda: 1000.0)
    monkeypatch.setattr(internal, "try_capture_follow_up", Mock(return_value=None))
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    event = build_event("p:stopped", "stopped input", 1000)
    event.is_stopped = Mock(side_effect=[False, True])
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_reasoning = False
    async for _ in stage.process(event, ""):
        pass
    assert "p:stopped" not in merger._states


@pytest.mark.asyncio
async def test_superseded_input_is_preserved_for_the_newest_request(monkeypatch):
    """Keep normal superseded input available to its consolidated reply.

    Args:
        monkeypatch: Scoped merger, hooks and clock replacements.
    """
    from unittest.mock import AsyncMock

    from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal

    merger = _InboundReplyMerger()
    monkeypatch.setattr(internal, "_inbound_reply_merger", merger)
    monkeypatch.setattr(internal, "time", lambda: 1000.0)
    monkeypatch.setattr(internal, "try_capture_follow_up", Mock(return_value=None))
    monkeypatch.setattr(internal, "call_event_hook", AsyncMock(return_value=False))
    first = build_event("p:superseded", "first", 1000)
    second = build_event("p:superseded", "second", 1000)
    first.is_stopped = Mock(return_value=False)
    original_set = first.set_extra
    first.set_extra = Mock(
        side_effect=lambda key, value: (
            original_set(key, value),
            merger.register(second) if key == "_inbound_received_at" else None,
        )
    )
    stage = internal.InternalAgentSubStage.__new__(internal.InternalAgentSubStage)
    stage.streaming_response = False
    stage.show_reasoning = False
    async for _ in stage.process(first, ""):
        pass
    assert [m.text for m in merger.decide(second, now=1000).messages] == [
        "first",
        "second",
    ]
