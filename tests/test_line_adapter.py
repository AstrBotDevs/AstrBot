import asyncio

import pytest

from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    CallbackAction,
    UrlAction,
)
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)
from astrbot.core.platform.sources.line.line_adapter import LinePlatformAdapter
from astrbot.core.platform.sources.line.line_event import LineMessageEvent
from tests.fixtures.helpers import make_platform_config


def _build_adapter() -> LinePlatformAdapter:
    return LinePlatformAdapter(
        make_platform_config(
            "line",
            channel_access_token="test-token",
            channel_secret="test-secret",
        ),
        {},
        asyncio.Queue(),
    )


@pytest.mark.asyncio
async def test_line_action_row_builds_template_actions():
    row = ActionRow(
        fallback_text="Choose an action",
        buttons=[
            Button(
                id="approve",
                label="Approve",
                action=CallbackAction(data={"request_id": 42}),
            ),
            Button(
                id="docs",
                label="Documentation",
                action=UrlAction(url="https://example.com/docs"),
            ),
        ],
    )

    message = await LineMessageEvent._component_to_message_object(row)

    assert message is not None
    assert message["type"] == "template"
    assert message["altText"] == "Choose an action"
    actions = message["template"]["actions"]
    assert actions[1] == {
        "type": "uri",
        "label": "Documentation",
        "uri": "https://example.com/docs",
    }
    action_id, data = decode_button_callback(actions[0]["data"])
    assert action_id == "approve"
    assert data == {"request_id": 42}


@pytest.mark.asyncio
async def test_line_action_row_uses_compact_postback_token_for_large_data():
    row = ActionRow(
        buttons=[
            Button(
                id="oversized",
                label="Oversized",
                action=CallbackAction(data={"value": "x" * 300}),
            )
        ]
    )

    message = await LineMessageEvent._component_to_message_object(row)

    callback_data = message["template"]["actions"][0]["data"]
    assert len(callback_data.encode("utf-8")) <= 300
    assert decode_button_callback(callback_data) == (
        "oversized",
        {"value": "x" * 300},
    )


@pytest.mark.asyncio
async def test_line_postback_becomes_button_interaction():
    adapter = _build_adapter()
    callback_data = encode_button_callback("approve", {"request_id": 42})

    message = await adapter.convert_message(
        {
            "type": "postback",
            "mode": "active",
            "timestamp": 1_700_000_000_000,
            "webhookEventId": "event-1",
            "source": {"type": "group", "groupId": "group-1", "userId": "user-1"},
            "postback": {"data": callback_data},
        }
    )

    assert message is not None
    assert message.message_id == "event-1"
    assert message.session_id == "group-1"
    assert len(message.message) == 1
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"request_id": 42}
    assert interaction.interaction_id == "event-1"
    event = adapter.create_event(message)
    assert event.is_button_interaction()
    assert event.get_button_interaction() is interaction


@pytest.mark.asyncio
async def test_line_ignores_foreign_postback_payload():
    adapter = _build_adapter()

    message = await adapter.convert_message(
        {
            "type": "postback",
            "source": {"type": "user", "userId": "user-1"},
            "postback": {"data": "third-party=value"},
        }
    )

    assert message is None
