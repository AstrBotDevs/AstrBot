import asyncio

import pytest

from astrbot.core.platform.sources.webchat.webchat_queue_mgr import WebChatQueueMgr


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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("detail", "code"),
    [
        ("ffmpeg not found", "ffmpegNotFound"),
        ("private detail", "messageProcessingFailed"),
    ],
)
async def test_listener_failure_emits_error_then_end(detail, code):
    manager = WebChatQueueMgr()

    async def fail(data):
        raise RuntimeError(detail)

    manager.set_listener(fail)
    back = manager.get_or_create_back_queue("request", "session")
    queue = manager.get_or_create_queue("session")
    try:
        await queue.put(("user", "session", {"message_id": "request"}))
        error = await asyncio.wait_for(back.get(), 2)
        end = await asyncio.wait_for(back.get(), 2)
        assert error["type"] == "error"
        assert error["error_code"] == code
        assert "private detail" not in error["data"]
        assert end["type"] == "end"
    finally:
        manager.remove_queues("session")
        await asyncio.sleep(0)
