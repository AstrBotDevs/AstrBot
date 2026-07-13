import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Json, Plain
from astrbot.core.platform.sources.webchat import webchat_event
from astrbot.core.platform.sources.webchat.webchat_queue_mgr import WebChatQueueMgr


@pytest.mark.asyncio
async def test_removed_back_queue_unblocks_sender_and_is_not_recreated(monkeypatch):
    queue_manager = WebChatQueueMgr(back_queue_maxsize=1)
    monkeypatch.setattr(webchat_event, "webchat_queue_mgr", queue_manager)

    request_id = "request-1"
    conversation_id = "conversation-1"
    session_id = f"webchat!user!{conversation_id}"
    back_queue = queue_manager.get_or_create_back_queue(
        request_id,
        conversation_id,
    )
    await back_queue.put({"type": "plain", "data": "pending"})

    blocked_sender = asyncio.create_task(
        webchat_event.WebChatMessageEvent._send(
            request_id,
            MessageChain().message("first late chunk"),
            session_id,
            streaming=True,
        )
    )
    await asyncio.sleep(0)
    assert not blocked_sender.done()

    queue_manager.remove_back_queue(request_id)
    await asyncio.wait_for(blocked_sender, timeout=1)

    await asyncio.wait_for(
        webchat_event.WebChatMessageEvent._send(
            request_id,
            MessageChain().message("second late chunk"),
            session_id,
            streaming=True,
        ),
        timeout=1,
    )

    assert request_id not in queue_manager.back_queues
    assert queue_manager.list_back_request_ids(conversation_id) == []


@pytest.mark.asyncio
async def test_audio_stream_stops_when_back_queue_is_closed(monkeypatch):
    put_back_queue = AsyncMock(return_value=False)
    monkeypatch.setattr(
        webchat_event.webchat_queue_mgr,
        "put_back_queue",
        put_back_queue,
    )
    second_chunk_requested = False

    async def generate_audio_chunks():
        nonlocal second_chunk_requested
        yield MessageChain(
            chain=[Plain("audio-data"), Json(data={"text": "transcript"})],
            type="audio_chunk",
        )
        second_chunk_requested = True
        yield MessageChain(chain=[Plain("late-audio")], type="audio_chunk")

    generator = generate_audio_chunks()
    event = SimpleNamespace(
        message_obj=SimpleNamespace(message_id="request-1"),
        session_id="webchat!user!conversation-1",
    )
    try:
        await webchat_event.WebChatMessageEvent.send_streaming(event, generator)
    finally:
        await generator.aclose()

    put_back_queue.assert_awaited_once()
    assert not second_chunk_requested
