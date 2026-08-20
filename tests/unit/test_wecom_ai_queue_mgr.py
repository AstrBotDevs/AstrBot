import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter import (
    WecomAIQueueListener,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_queue_mgr import WecomAIQueueMgr


@pytest.mark.asyncio
async def test_wecom_ai_queue_listener_processes_messages_concurrently() -> None:
    queue_mgr = WecomAIQueueMgr()
    queue = queue_mgr.get_or_create_queue("stream-1")

    first_started = asyncio.Event()
    release_first = asyncio.Event()
    second_handled = asyncio.Event()
    handled: list[str] = []

    async def _callback(data: dict) -> None:
        stream_id = data["stream_id"]
        if stream_id == "first":
            first_started.set()
            await release_first.wait()
        handled.append(stream_id)
        if stream_id == "second":
            second_handled.set()

    queue_mgr.set_listener(_callback)

    await queue.put({"stream_id": "first"})
    await asyncio.wait_for(first_started.wait(), timeout=1.0)

    await queue.put({"stream_id": "second"})
    await asyncio.wait_for(second_handled.wait(), timeout=1.0)

    release_first.set()
    await queue_mgr.clear_listener()

    assert "first" in handled
    assert "second" in handled


@pytest.mark.asyncio
async def test_wecom_ai_queue_listener_stops_and_clears_listener() -> None:
    queue_mgr = WecomAIQueueMgr()
    stop_event = asyncio.Event()
    callback = AsyncMock()
    listener = WecomAIQueueListener(queue_mgr, callback, stop_event)

    task = asyncio.create_task(listener.run())
    await asyncio.sleep(0)
    assert queue_mgr._listener_callback is callback

    stop_event.set()
    await asyncio.wait_for(task, timeout=1.0)

    assert queue_mgr._listener_callback is None
