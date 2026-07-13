import asyncio

import pytest

from astrbot.api.event import MessageChain
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
