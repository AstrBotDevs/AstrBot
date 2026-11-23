"""Rate limits follow release times without relying on wall-clock timing."""

import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.knowledge_base import kb_helper


@pytest.fixture
def clock(monkeypatch):
    state = SimpleNamespace(now=1000.0, sleeps=[], stall=0.0)

    async def sleep(delay):
        state.sleeps.append(delay)
        await asyncio.sleep(0)
        state.now += delay + state.stall
        state.stall = 0.0

    monkeypatch.setattr(kb_helper, "time", SimpleNamespace(monotonic=lambda: state.now))
    monkeypatch.setattr(
        kb_helper, "asyncio", SimpleNamespace(Lock=asyncio.Lock, sleep=sleep)
    )
    return state


@pytest.mark.asyncio
@pytest.mark.parametrize("stall", [0.0, 0.4])
async def test_concurrent_waiters_keep_the_configured_interval(clock, stall):
    limiter = kb_helper.RateLimiter(600)
    clock.stall = stall
    released = []

    async def enter():
        async with limiter:
            released.append(clock.now)

    await asyncio.wait_for(asyncio.gather(*(enter() for _ in range(6))), timeout=2)

    assert released == pytest.approx(
        [1000.0] + [1000.0 + stall + index * 0.1 for index in range(1, 6)]
    )
    assert clock.sleeps == pytest.approx([0.1] * 5)
    assert limiter.last_call_time == released[-1]


@pytest.mark.asyncio
async def test_sequential_calls_are_spaced_and_idle_time_counts(clock):
    limiter = kb_helper.RateLimiter(600)
    async with limiter:
        pass
    async with limiter:
        pass
    assert clock.sleeps == pytest.approx([0.1])

    clock.now += 0.5
    async with limiter:
        pass
    assert clock.sleeps == pytest.approx([0.1])
    assert limiter.last_call_time == clock.now


@pytest.mark.asyncio
async def test_zero_rpm_disables_limiting(clock):
    limiter = kb_helper.RateLimiter(0)
    for _ in range(3):
        async with limiter:
            pass
    assert clock.sleeps == []
    assert clock.now == 1000.0


@pytest.mark.asyncio
async def test_cancelled_wait_releases_lock_and_keeps_last_release(clock, monkeypatch):
    limiter = kb_helper.RateLimiter(600)
    async with limiter:
        pass
    sleep = kb_helper.asyncio.sleep

    async def cancel(_delay):
        raise asyncio.CancelledError

    monkeypatch.setattr(kb_helper.asyncio, "sleep", cancel)
    with pytest.raises(asyncio.CancelledError):
        async with limiter:
            pytest.fail("A cancelled waiter must not enter the request body")
    assert limiter.last_call_time == 1000.0
    assert not limiter._lock.locked()

    monkeypatch.setattr(kb_helper.asyncio, "sleep", sleep)
    async with limiter:
        assert clock.now == pytest.approx(1000.1)
