"""A completed listener must never unregister its successor for the same key."""

import asyncio

import pytest

from astrbot.core.platform.sources.webchat.webchat_queue_mgr import WebChatQueueMgr
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_queue_mgr import WecomAIQueueMgr


@pytest.mark.asyncio
@pytest.mark.parametrize("manager_type", [WebChatQueueMgr, WecomAIQueueMgr])
@pytest.mark.parametrize("callback_started", [False, True])
async def test_recreated_queue_keeps_new_listener_registered(
    manager_type, callback_started
):
    manager = manager_type()
    entered = asyncio.Event()
    cleanup_started = asyncio.Event()
    cleanup_allowed = asyncio.Event()
    completed = asyncio.Event()
    tasks = []

    async def callback(_message):
        entered.set()
        try:
            await asyncio.Future()
        finally:
            cleanup_started.set()
            await cleanup_allowed.wait()

    manager.set_listener(callback)
    first_queue = manager.get_or_create_queue("session")
    previous = manager._listener_tasks["session"]
    tasks.append(previous)
    previous.add_done_callback(lambda _task: completed.set())
    try:
        if callback_started:
            first_queue.put_nowait({"message": "first"})
            await asyncio.wait_for(entered.wait(), 5)

        manager.remove_queue("session")
        replacement_queue = manager.get_or_create_queue("session")
        replacement = manager._listener_tasks["session"]
        tasks.append(replacement)
        assert replacement_queue is not first_queue
        assert replacement is not previous
        if callback_started:
            await asyncio.wait_for(cleanup_started.wait(), 5)
            assert not previous.done()
            assert manager._listener_tasks["session"] is replacement

        cleanup_allowed.set()
        await asyncio.wait_for(completed.wait(), 5)
        assert manager._listener_tasks.get("session") is replacement
        assert not replacement.done()

        manager.remove_queue("session")
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 5)
        assert "session" not in manager._listener_tasks
        assert all(task.done() for task in tasks)
    finally:
        cleanup_allowed.set()
        manager.remove_queue("session")
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
