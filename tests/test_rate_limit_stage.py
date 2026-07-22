import asyncio
from datetime import datetime as real_datetime
from datetime import timedelta

import pytest

from astrbot.core.pipeline.rate_limit_check import stage as rate_limit_stage


class FakeEvent:
    """Minimal message event used by the rate-limit stage tests."""

    session_id = "test-session"

    def stop_event(self) -> None:
        """Stop event propagation for discard-strategy compatibility."""


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

    await asyncio.gather(*(limiter.process(FakeEvent()) for _ in range(5)))

    margin = 0.3
    expected_stall = limiter.rate_limit_time.total_seconds() + margin
    assert sleep_durations == pytest.approx([expected_stall, expected_stall])
    timestamps = list(limiter.event_timestamps[FakeEvent.session_id])
    assert timestamps == sorted(timestamps)
