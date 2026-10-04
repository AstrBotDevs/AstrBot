import asyncio
from unittest.mock import AsyncMock

import pytest
from slack_sdk.socket_mode.request import SocketModeRequest

from astrbot.api.message_components import At, Plain
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from tests.fixtures.helpers import make_platform_config


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["socket", "webhook"])
@pytest.mark.parametrize(
    "block_type",
    ["rich_text_section", "inline_code", "rich_text_preformatted", "rich_text_quote"],
)
async def test_slack_rich_text_preserves_body_and_mention(mode, block_type):
    queue = asyncio.Queue()
    adapter = SlackAdapter(
        make_platform_config(
            "slack",
            bot_token="xoxb-test",
            app_token="xapp-test",
            signing_secret="test-secret",
            slack_connection_mode=mode,
        ),
        {},
        queue,
    )
    adapter.bot_self_id = "UBOT"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Tester"}},
    )
    adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": False, "name": "test"}},
    )
    body = "BLOCK_TEST_9527\nRuntimeError: unique_test_9527\n"
    body_element = {"type": "text", "text": body}
    if block_type == "inline_code":
        body_element["style"] = {"code": True}
    event = {
        "type": "message",
        "user": "UTEST",
        "channel": "CTEST",
        "ts": "1700000000.000001",
        "text": f"<@UBOT> Explain this error\n{body}https://example.com\nEnd",
        "blocks": [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {"type": "user", "user_id": "UBOT"},
                            {"type": "text", "text": "Explain this error"},
                        ],
                    },
                    {
                        "type": "rich_text_section"
                        if block_type == "inline_code"
                        else block_type,
                        "elements": [
                            body_element,
                            {"type": "link", "url": "https://example.com"},
                        ],
                    },
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": "End"}],
                    },
                ],
            },
        ],
    }
    payload = {"type": "event_callback", "event": event}
    if mode == "socket":
        await adapter._handle_socket_event(
            SocketModeRequest(type="events_api", envelope_id="test", payload=payload),
        )
    else:
        await adapter._handle_webhook_event(payload)

    received = queue.get_nowait()
    components = received.message_obj.message
    assert isinstance(components[0], At)
    assert components[0].qq == "UBOT"
    expected_body = body + "[https://example.com](https://example.com)"
    if block_type in ("rich_text_preformatted", "rich_text_quote"):
        expected_body = f"\n{expected_body}\n"
    assert received.message_str == f"Explain this error{expected_body}End"
    assert (
        "".join(c.text for c in components if isinstance(c, Plain))
        == received.message_str
    )
    assert queue.empty()


@pytest.mark.parametrize(
    ("before_mention", "after_mention"),
    [
        ("", "quoted text"),
        ("quoted before ", " after"),
        ("quoted text ", ""),
        ("", ""),
    ],
    ids=["mention_first", "mention_middle", "mention_last", "mention_only"],
)
def test_slack_quote_keeps_boundaries_around_mentions(before_mention, after_mention):
    adapter = SlackAdapter(
        make_platform_config("slack", bot_token="xoxb-test", app_token="xapp-test"),
        {},
        asyncio.Queue(),
    )
    components = adapter._parse_blocks(
        [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": "Question:"}],
                    },
                    {
                        "type": "rich_text_quote",
                        "elements": [
                            {"type": "text", "text": before_mention},
                            {"type": "user", "user_id": "UOTHER"},
                            {"type": "text", "text": after_mention},
                        ],
                    },
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": "Next paragraph"}],
                    },
                ],
            },
        ],
    )

    assert "".join(c.text for c in components if isinstance(c, Plain)) == (
        f"Question:\n{before_mention}{after_mention}\nNext paragraph"
    )
    assert [c.qq for c in components if isinstance(c, At)] == ["UOTHER"]
    mention_index = next(i for i, c in enumerate(components) if isinstance(c, At))
    assert "".join(c.text for c in components[:mention_index]) == (
        f"Question:\n{before_mention}"
    )
    assert "".join(c.text for c in components[mention_index + 1 :]) == (
        f"{after_mention}\nNext paragraph"
    )
