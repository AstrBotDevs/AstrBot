"""Tests for the WeCom AI Bot long-connection client."""

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.wecom_ai_bot.wecomai_long_connection import (
    WecomAIBotLongConnectionClient,
)


@pytest.mark.asyncio
async def test_callback_handler_can_receive_command_ack() -> None:
    """A callback response must not block the socket's ACK receive path."""
    handler_started = asyncio.Event()
    handler_finished = asyncio.Event()

    async def message_handler(_: dict) -> None:
        handler_started.set()
        sent = await client.send_command(
            "aibot_respond_msg",
            "response-request",
            {"msgtype": "stream"},
        )
        assert sent is True
        handler_finished.set()

    client = WecomAIBotLongConnectionClient(
        bot_id="bot-id",
        secret="secret",
        ws_url="wss://example.com",
        heartbeat_interval=30,
        message_handler=message_handler,
    )
    client._ws = AsyncMock(closed=False)

    callback = json.dumps(
        {
            "cmd": "aibot_msg_callback",
            "headers": {"req_id": "callback-request"},
            "body": {},
        }
    )
    await asyncio.wait_for(client._handle_text_message(callback), timeout=0.1)
    await asyncio.wait_for(handler_started.wait(), timeout=0.1)

    acknowledgement = json.dumps(
        {"headers": {"req_id": "response-request"}, "errcode": 0}
    )
    await client._handle_text_message(acknowledgement)

    await asyncio.wait_for(handler_finished.wait(), timeout=0.1)
    await asyncio.sleep(0)
    assert not client._message_handler_tasks


@pytest.mark.asyncio
async def test_callback_concurrency_is_bounded() -> None:
    """Overflow callbacks must not create an unbounded task backlog."""
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def message_handler(_: dict) -> None:
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()

    client = WecomAIBotLongConnectionClient(
        bot_id="bot-id",
        secret="secret",
        ws_url="wss://example.com",
        heartbeat_interval=30,
        message_handler=message_handler,
        max_concurrent_callbacks=1,
    )
    callback = json.dumps({"cmd": "aibot_msg_callback", "headers": {}, "body": {}})

    await client._handle_text_message(callback)
    await started.wait()
    await client._handle_text_message(callback)
    assert len(client._message_handler_tasks) == 1
    assert calls == 1

    release.set()
    await asyncio.gather(*client._message_handler_tasks)
    assert client._active_callback_count == 0
