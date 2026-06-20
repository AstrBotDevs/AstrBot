from unittest.mock import AsyncMock

import pytest
from aiocqhttp import Event
from aiocqhttp.exceptions import ApiNotAvailable

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_aiocqhttp_send_message_falls_back_to_event_send_when_api_unavailable():
    bot = AsyncMock()
    bot.send_private_msg.side_effect = ApiNotAvailable
    event = Event.from_payload(
        {
            "post_type": "message",
            "message_type": "private",
            "sub_type": "friend",
            "self_id": 12345,
            "user_id": 987654,
            "message_id": 1,
            "message": [],
        }
    )
    chain = MessageChain([Comp.Plain("hello")])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=event,
        is_group=False,
        session_id="987654",
    )

    bot.send_private_msg.assert_awaited_once_with(
        user_id=987654,
        message=[{"type": "text", "data": {"text": "hello"}}],
        self_id=12345,
    )
    bot.send.assert_awaited_once_with(
        event=event,
        message=[{"type": "text", "data": {"text": "hello"}}],
        self_id=12345,
    )


@pytest.mark.asyncio
async def test_aiocqhttp_send_message_does_not_raise_when_api_unavailable_without_event():
    bot = AsyncMock()
    bot.send_private_msg.side_effect = ApiNotAvailable
    chain = MessageChain([Comp.Plain("hello")])

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=chain,
        event=None,
        is_group=False,
        session_id="987654",
    )

    bot.send_private_msg.assert_awaited_once_with(
        user_id=987654,
        message=[{"type": "text", "data": {"text": "hello"}}],
    )
    bot.send.assert_not_awaited()
