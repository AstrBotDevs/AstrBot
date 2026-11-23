"""Rate-limit decisions are deterministic and do not mutate unrelated sessions."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from astrbot.core.pipeline.rate_limit_check import stage as rate_limit


@pytest.mark.asyncio
async def test_disabled_rate_limit_does_not_inspect_the_event() -> None:
    stage = rate_limit.RateLimitStage()
    await stage.process(object())
    assert dict(stage.event_timestamps) == {}
    assert dict(stage.locks) == {}


@pytest.mark.asyncio
async def test_discard_policy_stops_only_the_over_limit_session(monkeypatch) -> None:
    now = datetime(2026, 1, 1)
    monkeypatch.setattr(rate_limit, "datetime", SimpleNamespace(now=lambda: now))
    stage = rate_limit.RateLimitStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "platform_settings": {
                    "rate_limit": {"count": 1, "time": 10, "strategy": "discard"}
                }
            }
        )
    )
    first = SimpleNamespace(
        unified_msg_origin="one:FriendMessage:alice", stop_event=Mock()
    )
    other = SimpleNamespace(
        unified_msg_origin="two:FriendMessage:alice", stop_event=Mock()
    )
    await stage.process(first)
    await stage.process(first)
    await stage.process(other)
    first.stop_event.assert_called_once_with()
    other.stop_event.assert_not_called()
    assert list(stage.event_timestamps[first.unified_msg_origin]) == [now]
    assert list(stage.event_timestamps[other.unified_msg_origin]) == [now]
    assert stage.rate_limit_time == timedelta(seconds=10)
