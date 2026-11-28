import asyncio
from datetime import datetime as real_datetime
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
    assert not limiter.locks  # Immediate discard admission does not acquire locks.


@pytest.mark.asyncio
async def test_stalled_concurrent_events_use_current_time_after_lock(monkeypatch):
    """Ensure queued events do not reuse timestamps captured before lock waits."""
    virtual_seconds = 0.0
    sleep_durations: list[float] = []
    real_sleep = asyncio.sleep
    base_time = real_datetime(2026, 1, 1)

    class FakeDateTime(real_datetime):
        """Subclass of datetime with a deterministic now()."""

        @classmethod
        def now(cls) -> real_datetime:
            """Return the current virtual wall-clock time.

            Returns:
                Current virtual time.
            """
            return base_time + timedelta(seconds=virtual_seconds)

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

    monkeypatch.setattr(rate_limit_stage, "datetime", FakeDateTime)
    monkeypatch.setattr(rate_limit_stage.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(rate_limit_stage.logger, "info", lambda *args, **kwargs: None)

    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 2
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "stall"
    limiter.max_pending = 3  # Allow all three events beyond the initial burst to wait.

    await asyncio.gather(*(limiter.process(FakeEvent()) for _ in range(5)))

    margin = 0.3
    expected_stall = limiter.rate_limit_time.total_seconds() + margin
    assert sleep_durations == pytest.approx([expected_stall, expected_stall])
    timestamps = list(limiter.event_timestamps[FakeEvent.unified_msg_origin])
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_discard_never_waits_for_a_held_session_lock():
    """Drop excess messages without joining an existing session lock queue."""
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 1
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "discard"
    first, excess = FakeEvent(), FakeEvent()
    await limiter.process(first)

    lock = limiter.locks[excess.unified_msg_origin]
    async with lock:
        await asyncio.wait_for(limiter.process(excess), timeout=1)

    assert excess.stopped
    assert not limiter._pending_events


@pytest.mark.asyncio
async def test_concurrent_discard_admits_only_the_available_capacity():
    """Concurrent arrivals cannot oversubscribe the no-await admission path."""
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 5
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "discard"
    events = [FakeEvent() for _ in range(100)]

    await asyncio.gather(*(limiter.process(event) for event in events))

    assert sum(not event.stopped for event in events) == 5
    assert len(limiter.event_timestamps[FakeEvent.unified_msg_origin]) == 5
    assert not limiter._pending_events
    assert not limiter.locks


@pytest.mark.asyncio
@pytest.mark.parametrize("max_pending", [0, 1, 3])
async def test_stall_waiter_budget_includes_lock_holder_and_lock_waiters(
    monkeypatch, max_pending
):
    """Bound all waiting events before any of them acquires the session lock."""
    virtual_seconds = 0.0
    base_time = real_datetime(2026, 1, 1)
    release_sleep = asyncio.Event()
    real_sleep = asyncio.sleep

    class FakeDateTime(real_datetime):
        @classmethod
        def now(cls):
            """Return deterministic time.

            Returns:
                Current virtual wall-clock time.
            """
            return base_time + timedelta(seconds=virtual_seconds)

    async def fake_sleep(duration):
        """Hold a rate-limit sleeper until the test releases it.

        Args:
            duration: Requested wait, added to virtual time after release.
        """
        nonlocal virtual_seconds
        await release_sleep.wait()
        virtual_seconds += duration
        await real_sleep(0)

    monkeypatch.setattr(rate_limit_stage, "datetime", FakeDateTime)
    monkeypatch.setattr(rate_limit_stage.asyncio, "sleep", fake_sleep)
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 1
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "stall"
    limiter.max_pending = max_pending
    await limiter.process(FakeEvent())
    events = [FakeEvent() for _ in range(20)]
    tasks = [asyncio.create_task(limiter.process(event)) for event in events]
    try:
        await real_sleep(0)
        assert sum(not task.done() for task in tasks) == max_pending
        assert sum(event.stopped for event in events) == 20 - max_pending
        assert limiter._pending_events.get(FakeEvent.unified_msg_origin, 0) == max_pending
    finally:
        release_sleep.set()
        await asyncio.gather(*tasks)
    assert not limiter._pending_events


@pytest.mark.asyncio
async def test_cancelling_stall_waiters_releases_all_pending_slots(monkeypatch):
    """Cancellation while sleeping or acquiring the lock must release admission."""
    sleeping = asyncio.Event()
    blocker = asyncio.Event()
    real_sleep = asyncio.sleep

    async def fake_sleep(duration):
        """Expose and hold a waiting task without a wall-clock delay.

        Args:
            duration: Unused production sleep duration.
        """
        sleeping.set()
        await blocker.wait()

    monkeypatch.setattr(rate_limit_stage.asyncio, "sleep", fake_sleep)
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 1
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "stall"
    limiter.max_pending = 2
    await limiter.process(FakeEvent())
    holder = asyncio.create_task(limiter.process(FakeEvent()))
    await sleeping.wait()
    waiter = asyncio.create_task(limiter.process(FakeEvent()))
    await real_sleep(0)
    assert limiter._pending_events[FakeEvent.unified_msg_origin] == 2
    waiter.cancel()
    await asyncio.gather(waiter, return_exceptions=True)
    assert limiter._pending_events[FakeEvent.unified_msg_origin] == 1
    holder.cancel()
    await asyncio.gather(holder, return_exceptions=True)
    assert not limiter._pending_events
    assert not limiter.locks[FakeEvent.unified_msg_origin].locked()


@pytest.mark.asyncio
async def test_stall_waiter_budgets_are_isolated_by_session(monkeypatch):
    """A full waiting budget in one session must not block another session."""
    sleeping = asyncio.Event()
    blocker = asyncio.Event()

    async def fake_sleep(duration):
        """Expose and hold a waiting task without a wall-clock delay.

        Args:
            duration: Unused production sleep duration.
        """
        sleeping.set()
        await blocker.wait()

    monkeypatch.setattr(rate_limit_stage.asyncio, "sleep", fake_sleep)
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 1
    limiter.rate_limit_time = timedelta(seconds=60)
    limiter.rl_strategy = "stall"
    await limiter.process(FakeEvent())
    holder = asyncio.create_task(limiter.process(FakeEvent()))
    try:
        await sleeping.wait()
        other = FakeEvent(unified_msg_origin="other:GroupMessage:another-session")
        await limiter.process(other)
        assert not other.stopped
        excess = FakeEvent()
        await limiter.process(excess)
        assert excess.stopped
    finally:
        holder.cancel()
        await asyncio.gather(holder, return_exceptions=True)
    assert not limiter._pending_events


@pytest.mark.asyncio
async def test_disabled_limiter_does_not_allocate_waiting_state():
    """A nonpositive message limit must bypass both rate and waiting limits."""
    limiter = rate_limit_stage.RateLimitStage()
    limiter.rate_limit_count = 0
    limiter.max_pending = 0
    event = FakeEvent()
    await limiter.process(event)
    assert not event.stopped
    assert not limiter.event_timestamps
    assert not limiter._pending_events


@pytest.mark.asyncio
async def test_existing_stall_config_gets_a_finite_default_waiter_budget():
    """Old configurations that omit max_pending must not create unlimited waits."""
    from types import SimpleNamespace

    limiter = rate_limit_stage.RateLimitStage()
    await limiter.initialize(
        SimpleNamespace(
            astrbot_config={
                "platform_settings": {
                    "rate_limit": {"time": 60, "count": 5, "strategy": "stall"}
                }
            }
        )
    )
    assert limiter.rl_strategy == "stall"
    assert limiter.max_pending == 1
