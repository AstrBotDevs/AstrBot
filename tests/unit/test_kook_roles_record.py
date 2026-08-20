import asyncio
from unittest.mock import MagicMock

import pytest

from astrbot.core.platform.sources.kook.kook_roles_record import KookRolesRecord


@pytest.mark.asyncio
async def test_kook_roles_record_timeout_returns_false_but_background_fetch_warms_cache():
    record = KookRolesRecord("bot-1", MagicMock())
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()
    fetch_count = 0

    async def _fetch_roles(_guild_id: int) -> set[int]:
        nonlocal fetch_count
        fetch_count += 1
        fetch_started.set()
        await release_fetch.wait()
        return {42}

    record._fetch_roles_by_guild_id = _fetch_roles  # type: ignore[method-assign]

    first_result_task = asyncio.create_task(
        record.has_role_in_channel(42, 1001, wait_timeout=0.01)
    )
    await asyncio.wait_for(fetch_started.wait(), timeout=1.0)

    assert await first_result_task is False
    assert fetch_count == 1

    release_fetch.set()
    fetch_tasks = list(record._fetch_tasks.values())
    if fetch_tasks:
        await asyncio.gather(*fetch_tasks, return_exceptions=True)

    assert await record.has_role_in_channel(42, 1001, wait_timeout=0.01) is True
    assert fetch_count == 1
