from unittest.mock import AsyncMock

import pytest

import astrbot.core.message.components as Comp
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_message_event import (
    AiocqhttpMessageEvent,
)


@pytest.mark.asyncio
async def test_aiocqhttp_action_row_degrades_to_plain_text():
    row = Comp.ActionRow(
        fallback_text="Choose an action",
        buttons=[
            Comp.Button(
                id="approve",
                label="Approve",
                action=Comp.CallbackAction(data={"request_id": 42}),
            ),
            Comp.Button(
                id="docs",
                label="Documentation",
                action=Comp.UrlAction(url="https://example.com/docs"),
            ),
        ],
    )

    data = await AiocqhttpMessageEvent._parse_onebot_json(MessageChain([row]))

    assert data == [
        {
            "type": "text",
            "data": {
                "text": (
                    "Choose an action\n"
                    "[Button unavailable] Approve\n"
                    "Documentation: https://example.com/docs"
                )
            },
        }
    ]


@pytest.mark.asyncio
async def test_aiocqhttp_callback_button_never_emits_nonstandard_segment():
    button = Comp.Button(
        id="retry",
        label="Retry",
        action=Comp.CallbackAction(),
    )

    data = await AiocqhttpMessageEvent._parse_onebot_json(MessageChain([button]))

    assert data == [
        {
            "type": "text",
            "data": {"text": "[Button unavailable] Retry"},
        }
    ]
    assert all(segment["type"] not in {"button", "actionrow"} for segment in data)


@pytest.mark.asyncio
async def test_aiocqhttp_sends_url_button_fallback_as_text():
    bot = AsyncMock()
    row = Comp.ActionRow(
        buttons=[
            Comp.Button(
                id="website",
                label="Website",
                action=Comp.UrlAction(url="https://example.com"),
            )
        ]
    )

    await AiocqhttpMessageEvent.send_message(
        bot=bot,
        message_chain=MessageChain([row]),
        event=None,
        is_group=True,
        session_id="123456",
    )

    bot.send_group_msg.assert_awaited_once_with(
        group_id=123456,
        message=[
            {
                "type": "text",
                "data": {"text": "Website: https://example.com"},
            }
        ],
    )
