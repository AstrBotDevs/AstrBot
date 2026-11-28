import asyncio
from datetime import timedelta

import pytest

from astrbot.core.pipeline.rate_limit_check import stage as rate_limit_stage


class FakeEvent:
    """Minimal message event used by the rate-limit stage tests."""

    session_id = "test-session"
    unified_msg_origin = "test-platform:GroupMessage:test-session"

    def __init__(
        self,
        session_id: str = session_id,
        unified_msg_origin: str = unified_msg_origin,
    ) -> None:
        """Initialize a fake event with scoped and unscoped session IDs.

        Args:
            session_id: Platform-local session identifier.
            unified_msg_origin: Platform-scoped message origin.
        """
        self.session_id = session_id
        self.unified_msg_origin = unified_msg_origin
        self.stopped = False

    def stop_event(self) -> None:
        """Stop event propagation for discard-strategy compatibility."""
        self.stopped = True


@pytest.mark.asyncio
async def test_different_platforms_do_not_share_rate_limit_state():
    """Ensure identical session IDs remain isolated across platform instances."""
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 1
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "discard"

    first_event = FakeEvent(
        session_id="same-session",
        unified_msg_origin="platform-a:GroupMessage:same-session",
    )
    second_event = FakeEvent(
        session_id="same-session",
        unified_msg_origin="platform-b:GroupMessage:same-session",
    )

    await limiter.process(first_event)
    await limiter.process(second_event)

    expected_keys = {
        first_event.unified_msg_origin,
        second_event.unified_msg_origin,
    }
    assert not first_event.stopped
    assert not second_event.stopped
    assert set(limiter.event_timestamps) == expected_keys
    assert set(limiter.locks) == expected_keys


@pytest.mark.asyncio
async def test_stalled_concurrent_events_use_current_time_after_lock(monkeypatch):
    """Ensure queued events do not reuse timestamps captured before lock waits."""
    virtual_seconds = 100.0
    sleep_durations: list[float] = []
    real_sleep = asyncio.sleep

    def fake_monotonic() -> float:
        return virtual_seconds

    async def fake_sleep(duration: float) -> None:
        """Advance virtual time after allowing concurrent tasks to queue.

        Args:
            duration: Requested sleep duration in seconds.
        """
        nonlocal virtual_seconds
        sleep_durations.append(duration)
        target_time = virtual_seconds + duration
        await real_sleep(0)
        virtual_seconds = target_time

    monkeypatch.setattr(rate_limit_stage.time, "monotonic", fake_monotonic)
    monkeypatch.setattr(rate_limit_stage.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(rate_limit_stage.logger, "info", lambda *args, **kwargs: None)

    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 2
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "stall"

    await asyncio.gather(*(limiter.process(FakeEvent()) for _ in range(5)))

    margin = 0.3
    expected_stall = limiter.rate_limit_time.total_seconds() + margin
    assert sleep_durations == pytest.approx([expected_stall, expected_stall])
    timestamps = list(limiter.event_timestamps[FakeEvent.unified_msg_origin])
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_expired_idle_sessions_are_evicted_from_timestamps_and_locks(monkeypatch):
    """Idle session entries and locks are swept once their timestamps expire."""
    virtual_seconds = 10.0
    monkeypatch.setattr(rate_limit_stage.time, "monotonic", lambda: virtual_seconds)

    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 2
    limiter.rate_limit_time = timedelta(seconds=10)
    limiter.rl_strategy = "discard"

    idle_event = FakeEvent(unified_msg_origin="platform-a:FriendMessage:idle")
    await limiter.process(idle_event)
    assert idle_event.unified_msg_origin in limiter.event_timestamps
    assert idle_event.unified_msg_origin in limiter.locks

    # Advance past both window and sweep interval so next event sweeps idle UMO.
    virtual_seconds = 100.0
    active_event = FakeEvent(unified_msg_origin="platform-a:FriendMessage:active")
    await limiter.process(active_event)

    assert idle_event.unified_msg_origin not in limiter.event_timestamps
    assert idle_event.unified_msg_origin not in limiter.locks
    assert active_event.unified_msg_origin in limiter.event_timestamps
    assert active_event.unified_msg_origin in limiter.locks


@pytest.mark.asyncio
async def test_unknown_strategy_discards_without_infinite_loop(monkeypatch):
    """Unknown rate-limit strategies must fail closed by discarding cleanly."""
    monkeypatch.setattr(rate_limit_stage.time, "monotonic", lambda: 50.0)

    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 1
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "unexpected_strategy"

    first = FakeEvent()
    second = FakeEvent()
    await limiter.process(first)
    await asyncio.wait_for(limiter.process(second), timeout=1.0)

    assert not first.stopped
    assert second.stopped


@pytest.mark.asyncio
async def test_non_positive_rate_limit_time_bypasses_limiting():
    """Non-positive window durations disable limiting instead of looping."""
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 1
    limiter.rate_limit_time = timedelta(seconds=0)
    limiter.rl_strategy = "stall"

    events = [FakeEvent() for _ in range(3)]
    await asyncio.wait_for(
        asyncio.gather(*(limiter.process(ev) for ev in events)), timeout=1.0
    )

    assert all(not ev.stopped for ev in events)
    assert limiter.event_timestamps == {}
    assert limiter.locks == {}
