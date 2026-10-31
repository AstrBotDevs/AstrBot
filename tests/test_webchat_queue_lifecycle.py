import asyncio

import pytest

from astrbot.core.platform.sources.webchat.webchat_queue_mgr import WebChatQueueMgr


@pytest.mark.asyncio
async def test_listener_restart_consumes_existing_conversation_queue() -> None:
    """Restarting the listener must resume delivery for existing conversations."""
    manager = WebChatQueueMgr()
    received: asyncio.Queue[tuple] = asyncio.Queue()

    async def callback(data: tuple) -> None:
        await received.put(data)

    manager.set_listener(callback)
    queue = manager.get_or_create_queue("existing")
    try:
        await queue.put(("before",))
        assert await asyncio.wait_for(received.get(), 1) == ("before",)
        await manager.clear_listener()
        await queue.put(("during-stop",))
        manager.set_listener(callback)
        assert manager.get_or_create_queue("existing") is queue
        assert await asyncio.wait_for(received.get(), 1) == ("during-stop",)
        await queue.put(("after",))
        assert await asyncio.wait_for(received.get(), 1) == ("after",)
    finally:
        await manager.clear_listener()


@pytest.mark.asyncio
async def test_registration_during_clear_waits_for_old_consumer() -> None:
    """A new callback must get exactly one tracked consumer after teardown."""
    manager = WebChatQueueMgr()
    started = asyncio.Event()
    cancelling = asyncio.Event()
    release = asyncio.Event()
    received: asyncio.Queue[tuple] = asyncio.Queue()

    async def old_callback(data: tuple) -> None:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelling.set()
            await release.wait()
            raise

    async def new_callback(data: tuple) -> None:
        await received.put(data)

    manager.set_listener(old_callback)
    queue = manager.get_or_create_queue("existing")
    await queue.put(("old",))
    await asyncio.wait_for(started.wait(), 1)
    clearing = asyncio.create_task(manager.clear_listener())
    try:
        await asyncio.wait_for(cancelling.wait(), 1)
        manager.set_listener(new_callback)
        new_queue = manager.get_or_create_queue("new")
        await queue.put(("existing",))
        await new_queue.put(("new",))
        assert "new" not in manager._listener_tasks
        release.set()
        await asyncio.wait_for(clearing, 1)
        assert set(manager._listener_tasks) == {"existing", "new"}
        task = manager._listener_tasks["existing"]
        manager.set_listener(new_callback)
        assert manager._listener_tasks["existing"] is task
        messages = {await asyncio.wait_for(received.get(), 1) for _ in range(2)}
        assert messages == {("existing",), ("new",)}
    finally:
        release.set()
        await asyncio.gather(clearing, return_exceptions=True)
        await manager.clear_listener()


@pytest.mark.asyncio
async def test_removed_back_queue_unblocks_pending_writer():
    queue_manager = WebChatQueueMgr(back_queue_maxsize=1)
    request_id = "request-1"
    queue = queue_manager.get_or_create_back_queue(request_id, "conversation-1")
    await queue.put({"type": "plain", "data": "first"})

    blocked_writer = asyncio.create_task(
        queue_manager.put_back_queue(
            request_id,
            {"type": "plain", "data": "second"},
        )
    )
    await asyncio.sleep(0)
    assert not blocked_writer.done()

    queue_manager.remove_back_queue(request_id)

    assert await asyncio.wait_for(blocked_writer, timeout=1) is False
    assert not await queue_manager.put_back_queue(
        request_id,
        {"type": "plain", "data": "late"},
    )
