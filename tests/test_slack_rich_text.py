import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.api.message_components import At, Plain
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from tests.fixtures.helpers import make_platform_config


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block_type",
    ["rich_text_preformatted", "rich_text_quote", "rich_text_section", "inline_code"],
)
async def test_slack_rich_text_preserves_body_and_mention(block_type):
    adapter = SlackAdapter(
        make_platform_config("slack", bot_token="xoxb-test", app_token="xapp-test"),
        {},
        asyncio.Queue(),
    )
    adapter.bot_self_id = "UBOT"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Tester"}},
    )
    adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": False, "name": "test"}},
    )
    body = "BLOCK_TEST_9527\nRuntimeError: unique_test_9527"
    body_element = {"type": "text", "text": body}
    if block_type == "inline_code":
        body_element["style"] = {"code": True}
    event = {
        "type": "message",
        "user": "UTEST",
        "channel": "CTEST",
        "ts": "1700000000.000001",
        "text": f"<@UBOT> Explain this error\n{body}\nEnd",
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
                        "elements": [body_element],
                    },
                    {
                        "type": "rich_text_section",
                        "elements": [{"type": "text", "text": "End"}],
                    },
                ],
            },
        ],
    }
    received = await adapter.convert_message(event)
    components = received.message
    assert isinstance(components[0], At)
    assert components[0].qq == "UBOT"
    expected_body = body
    if block_type in ("rich_text_preformatted", "rich_text_quote"):
        expected_body = f"\n{expected_body}\n"
    assert received.message_str == f"Explain this error{expected_body}End"


@pytest.mark.parametrize(
    ("before_mention", "after_mention"),
    [
        ("quoted before ", " after"),
        ("quoted text ", ""),
    ],
    ids=["mention_middle", "mention_last"],
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
