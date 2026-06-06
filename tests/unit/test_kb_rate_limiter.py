import asyncio
from types import SimpleNamespace

import pytest

from astrbot.core.knowledge_base import kb_helper
from astrbot.core.knowledge_base.kb_helper import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_serializes_concurrent_entries(monkeypatch):
    real_sleep = asyncio.sleep
    monotonic_values = iter([0.0, 0.0, 0.0, 0.0])
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(
        kb_helper,
        "time",
        SimpleNamespace(monotonic=lambda: next(monotonic_values)),
    )
    monkeypatch.setattr(
        kb_helper,
        "asyncio",
        SimpleNamespace(Lock=asyncio.Lock, sleep=fake_sleep),
    )

    limiter = RateLimiter(max_rpm=60)
    limiter.last_call_time = -1.0
    await asyncio.gather(
        limiter.__aenter__(),
        limiter.__aenter__(),
    )

    assert sleeps == [1.0]
