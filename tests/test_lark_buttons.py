import asyncio
from unittest.mock import AsyncMock

import pytest
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    ButtonStyle,
    CallbackAction,
    Plain,
    UrlAction,
)
from astrbot.api.platform import MessageType
from astrbot.core.platform.button_interaction import decode_button_callback
from astrbot.core.platform.sources.lark.lark_adapter import LarkPlatformAdapter
from astrbot.core.platform.sources.lark.lark_event import LarkMessageEvent


def test_lark_button_card_maps_callback_and_url_actions():
    card = LarkMessageEvent._build_button_card(
        [
            Plain("Choose an action"),
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve",
                        action=CallbackAction(data={"request_id": 42}),
                        style=ButtonStyle.SUCCESS,
                    ),
                    Button(
                        id="docs",
                        label="Docs",
                        action=UrlAction(url="https://example.com/docs"),
                    ),
                ]
            ),
        ],
        MessageType.GROUP_MESSAGE.value,
    )

    assert card["schema"] == "2.0"
    assert card["body"]["elements"][0] == {
        "tag": "markdown",
        "content": "Choose an action",
    }
    columns = card["body"]["elements"][1]["columns"]
    callback_button = columns[0]["elements"][0]
    callback_value = callback_button["behaviors"][0]["value"]
    assert callback_button["type"] == "primary"
    assert decode_button_callback(callback_value["astrbot_callback"]) == (
        "approve",
        {"request_id": 42},
    )
    assert callback_value["astrbot_message_type"] == MessageType.GROUP_MESSAGE.value

    url_button = columns[1]["elements"][0]
    assert url_button["behaviors"] == [
        {
            "type": "open_url",
            "default_url": "https://example.com/docs",
        }
    ]


@pytest.mark.asyncio
async def test_lark_card_callback_becomes_button_interaction():
    adapter = object.__new__(LarkPlatformAdapter)
    adapter.event_id_timestamps = {}
    adapter.bot_open_id = "ou_bot"
    adapter.bot_name = "AstrBot"
    adapter.handle_msg = AsyncMock()
    card = LarkMessageEvent._build_button_card(
        [
            ActionRow(
                buttons=[
                    Button(
                        id="approve",
                        label="Approve",
                        action=CallbackAction(data={"request_id": 42}),
                    )
                ]
            )
        ],
        MessageType.GROUP_MESSAGE.value,
    )
    callback_value = card["body"]["elements"][0]["columns"][0]["elements"][0][
        "behaviors"
    ][0]["value"]

    await adapter.convert_card_action(
        {
            "header": {
                "event_id": "event-1",
                "create_time": "1720000000000000",
            },
            "event": {
                "operator": {"open_id": "ou_user"},
                "action": {"tag": "button", "value": callback_value},
                "context": {
                    "open_message_id": "om_source",
                    "open_chat_id": "oc_group",
                },
            },
        }
    )

    adapter.handle_msg.assert_awaited_once()
    message = adapter.handle_msg.await_args.args[0]
    assert message.type == MessageType.GROUP_MESSAGE
    assert message.session_id == "oc_group"
    assert message.sender.user_id == "ou_user"
    assert message.timestamp == 1720000000
    assert len(message.message) == 1
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "event-1"
    assert interaction.source_message_id == "om_source"


@pytest.mark.asyncio
async def test_lark_socket_card_callback_returns_immediate_ack():
    adapter = LarkPlatformAdapter(
        {
            "id": "lark-test",
            "app_id": "app-id",
            "app_secret": "app-secret",
        },
        {},
        asyncio.Queue(),
    )
    adapter.convert_card_action = AsyncMock()
    callback = P2CardActionTrigger(
        {
            "schema": "2.0",
            "header": {"event_id": "event-1"},
            "event": {},
        }
    )

    response = adapter.do_card_action_trigger(callback)
    await asyncio.sleep(0)

    assert isinstance(response, P2CardActionTriggerResponse)
    adapter.convert_card_action.assert_awaited_once_with(callback)
