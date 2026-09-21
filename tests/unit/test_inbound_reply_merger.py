"""Tests for session-scoped private inbound reply consolidation."""

from types import SimpleNamespace
from unittest.mock import Mock

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
