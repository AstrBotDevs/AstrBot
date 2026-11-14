import asyncio
from unittest.mock import MagicMock, patch

import pytest
from aiocqhttp import Event

from astrbot.core.platform.sources.aiocqhttp import (
    aiocqhttp_platform_adapter as adapter_module,
)
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_duplicate_message_delivery():
    bot = MagicMock()
    bot.on_message.side_effect = lambda kind: (
        lambda callback: callbacks.setdefault(kind, callback)
    )
    callbacks = {}
    config = {"id": "test", "ws_reverse_host": "localhost", "ws_reverse_port": 6199}
    queue = asyncio.Queue()
    with patch.object(adapter_module, "CQHttp", return_value=bot):
        adapter = adapter_module.AiocqhttpAdapter(config, {}, queue)
        other = adapter_module.AiocqhttpAdapter(config, {}, asyncio.Queue())

    payload = {
        "post_type": "message",
        "message_type": "private",
        "self_id": 1,
        "user_id": 2,
        "sender": {"user_id": 2},
        "message_id": 0,
        "message": [{"type": "text", "data": {"text": "same text"}}],
    }
    with patch.object(adapter_module.time, "monotonic", return_value=100) as clock:
        for kind in ("private", "group"):
            event = Event.from_payload(dict(payload, message_type=kind, group_id=3))
            await asyncio.gather(callbacks[kind](event), callbacks[kind](event))
        assert queue.qsize() == 2
        assert all(
            isinstance(queue.get_nowait(), AiocqhttpMessageEvent) for _ in range(2)
        )

        message = await adapter.convert_message(Event.from_payload(payload))
        await other.handle_msg(message)
        assert other._event_queue.qsize() == 1
        await adapter.handle_msg(
            await adapter.convert_message(
                Event.from_payload(
                    dict(
                        payload,
                        self_id="1",
                        user_id="2",
                        sender={"user_id": "2"},
                        message_id="0",
                    )
                )
            )
        )
        assert queue.empty()

        for changes in (
            {"self_id": 4},
            {"sender": {"user_id": 5}},
            {"message_type": "group", "group_id": 4},
            {"message_id": 1},
        ):
            converted = await adapter.convert_message(
                Event.from_payload(dict(payload, **changes))
            )
            await asyncio.gather(
                adapter.handle_msg(converted), adapter.handle_msg(converted)
            )
        assert queue.qsize() == 4

        for message_id in (None, ""):
            raw = dict(payload, message_id=message_id)
            if message_id is None:
                raw.pop("message_id")
            converted = await adapter.convert_message(Event.from_payload(raw))
            await adapter.handle_msg(converted)
            await adapter.handle_msg(converted)
        assert queue.qsize() == 8

        for post_type in ("notice", "request"):
            converted = await adapter.convert_message(
                Event.from_payload(
                    dict(
                        payload,
                        post_type=post_type,
                        notice_type="notify",
                        request_type="friend",
                        sub_type="poke",
                        target_id=1,
                    )
                )
            )
            await adapter.handle_msg(converted)
            await adapter.handle_msg(converted)
        assert queue.qsize() == 12

        clock.return_value = 159
        await adapter.handle_msg(message)
        assert queue.qsize() == 12
        clock.return_value = 160
        await adapter.handle_msg(message)
        assert queue.qsize() == 13

        for message_id in range(10, 1035):
            converted = await adapter.convert_message(
                Event.from_payload(dict(payload, message_id=message_id))
            )
            await adapter.handle_msg(converted)
        size = queue.qsize()
        await adapter.handle_msg(converted)
        assert queue.qsize() == size
        assert len(adapter._recent_messages) == 1024
        await adapter.handle_msg(message)
        assert queue.qsize() == size + 1
        await adapter.terminate()
        assert not adapter._recent_messages
        await adapter.handle_msg(message)
        assert queue.qsize() == size + 2

    for failure in ("create_event", "put_nowait"):
        await adapter.terminate()
        target = adapter if failure == "create_event" else queue
        with patch.object(target, failure, side_effect=RuntimeError("enqueue failed")):
            with pytest.raises(RuntimeError, match="enqueue failed"):
                await adapter.handle_msg(message)
        size = queue.qsize()
        await adapter.handle_msg(message)
        await adapter.handle_msg(message)
        assert queue.qsize() == size + 1
