import asyncio
import time

import pytest

# Importing the core lifecycle first resolves the import cycle between
# astrbot.core.provider.manager and astrbot.core.knowledge_base.
import astrbot.core.core_lifecycle  # noqa: F401
from astrbot.core.knowledge_base.kb_helper import RateLimiter


@pytest.mark.asyncio
async def test_concurrent_waiters_keep_the_configured_interval():
    limiter = RateLimiter(600)  # 0.1 s between calls
    times: list[float] = []

    async def enter() -> None:
        async with limiter:
            times.append(time.monotonic())

    await asyncio.gather(*(enter() for _ in range(6)))

    times.sort()
    gaps = [b - a for a, b in zip(times, times[1:])]
    assert len(gaps) == 5
    # Every pair of consecutive calls must be at least the interval apart
    # (small tolerance for timer granularity).
    assert min(gaps) >= 0.09, gaps


@pytest.mark.asyncio
async def test_sequential_calls_are_spaced_and_idle_time_counts():
    limiter = RateLimiter(600)
    start = time.monotonic()
    async with limiter:
        pass
    async with limiter:
        pass
    assert time.monotonic() - start >= 0.09

    await asyncio.sleep(0.15)
    before = time.monotonic()
    async with limiter:
        pass
    # An idle limiter does not make the caller wait.
    assert time.monotonic() - before < 0.05


@pytest.mark.asyncio
async def test_zero_rpm_disables_limiting():
    limiter = RateLimiter(0)
    before = time.monotonic()
    for _ in range(3):
        async with limiter:
            pass
    assert time.monotonic() - before < 0.05
