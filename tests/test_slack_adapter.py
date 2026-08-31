import asyncio
import hashlib
import hmac
import json
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest

from astrbot.api.message_components import (
    ActionRow,
    Button,
    ButtonInteraction,
    ButtonStyle,
    CallbackAction,
    Plain,
    UrlAction,
)
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.button_interaction import (
    decode_button_callback,
    encode_button_callback,
)
from astrbot.core.platform.sources.slack.client import SlackWebhookClient
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent


@pytest.mark.asyncio
async def test_slack_action_row_renders_block_kit_buttons():
    blocks, fallback_text = await SlackMessageEvent._parse_slack_blocks(
        MessageChain(
            [
                Plain("Choose: "),
                ActionRow(
                    buttons=[
                        Button(
                            id="approve",
                            label="Approve",
                            action=CallbackAction(data={"order_id": 42}),
                            style=ButtonStyle.SUCCESS,
                        ),
                        Button(
                            id="docs",
                            label="Docs",
                            action=UrlAction(url="https://example.com/docs"),
                        ),
                    ],
                    fallback_text="Approve or open docs",
                ),
            ]
        ),
        AsyncMock(),
    )

    assert fallback_text == "Choose: Approve or open docs"
    assert blocks[1] == {
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Approve"},
                "action_id": "approve",
                "value": encode_button_callback("approve", {"order_id": 42}),
                "style": "primary",
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": "Docs"},
                "action_id": "docs",
                "url": "https://example.com/docs",
            },
        ],
    }


@pytest.mark.asyncio
async def test_slack_block_action_converts_to_button_interaction():
    adapter = SlackAdapter.__new__(SlackAdapter)
    adapter.bot_self_id = "B1"
    adapter.web_client = AsyncMock()
    adapter.web_client.conversations_info.return_value = {"channel": {"is_im": False}}

    message = await adapter.convert_button_interaction(
        {
            "type": "block_actions",
            "trigger_id": "trigger-1",
            "user": {"id": "U1", "username": "alice"},
            "channel": {"id": "C1"},
            "container": {"message_ts": "123.456"},
            "actions": [
                {
                    "action_id": "approve",
                    "value": encode_button_callback(
                        "approve",
                        {"order_id": 42},
                    ),
                }
            ],
        }
    )

    assert message is not None
    assert message.session_id == "C1"
    assert message.sender.user_id == "U1"
    assert len(message.message) == 1
    interaction = message.message[0]
    assert isinstance(interaction, ButtonInteraction)
    assert interaction.action_id == "approve"
    assert interaction.data == {"order_id": 42}
    assert interaction.interaction_id == "trigger-1"
    assert interaction.source_message_id == "123.456"


@pytest.mark.asyncio
async def test_slack_webhook_acknowledges_block_action_before_processing():
    signing_secret = "secret"
    processing_started = asyncio.Event()
    release_processing = asyncio.Event()
    processing_finished = asyncio.Event()

    async def handle_event(payload):
        assert payload["type"] == "block_actions"
        processing_started.set()
        await release_processing.wait()
        processing_finished.set()

    client = SlackWebhookClient(
        AsyncMock(),
        signing_secret,
        event_handler=handle_event,
    )
    payload = {
        "type": "block_actions",
        "actions": [
            {
                "action_id": "approve",
                "value": encode_button_callback("approve"),
            }
        ],
    }
    body = urlencode({"payload": json.dumps(payload)}).encode()
    timestamp = "1700000000"
    signature = (
        "v0="
        + hmac.new(
            signing_secret.encode(),
            f"v0:{timestamp}:{body.decode()}".encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    class Request:
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": signature,
        }

        async def get_data(self):
            return body

    response = await asyncio.wait_for(client.handle_callback(Request()), timeout=0.2)

    assert response.status_code == 200
    await asyncio.wait_for(processing_started.wait(), timeout=0.2)
    assert not processing_finished.is_set()
    release_processing.set()
    await asyncio.wait_for(processing_finished.wait(), timeout=0.2)


def test_slack_codec_round_trip_used_by_interactive_buttons():
    encoded = encode_button_callback("approve", {"order_id": 42})

    assert decode_button_callback(encoded) == ("approve", {"order_id": 42})
