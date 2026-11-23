"""Current message tool input normalization and early validation contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_runtime.tools.message_tools import (
    SendMessageToUserTool,
    _normalize_message_component,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        ("text", None),
        ({"type": "plain", "text": "hello"}, {"type": "plain", "text": "hello"}),
        (
            {
                "type": "image",
                "path": "output.png",
                "url": "https://example.invalid/image",
            },
            {
                "type": "image",
                "path": "output.png",
                "url": "https://example.invalid/image",
            },
        ),
        (
            {"type": "mention_user", "mention_user_id": "alice", "unknown": "discard"},
            {"type": "mention_user", "mention_user_id": "alice"},
        ),
        ({"type": 7, "text": [], 1: "ignored"}, {}),
    ],
)
def test_component_normalization_accepts_only_known_string_fields(raw, expected):
    assert _normalize_message_component(raw) == expected


def test_message_schemas_are_independent_between_instances():
    first, second = SendMessageToUserTool(), SendMessageToUserTool()
    assert first.name == second.name == "send_message_to_user"
    assert first.parameters["required"] == ["messages"]
    assert first.parameters["properties"]["messages"]["items"]["required"] == ["type"]
    first.parameters["properties"]["messages"]["items"]["required"].append("text")
    assert second.parameters["properties"]["messages"]["items"]["required"] == ["type"]


@pytest.mark.asyncio
async def test_empty_messages_are_rejected_before_delivery():
    event = SimpleNamespace(
        unified_msg_origin="test:FriendMessage:caller", send=AsyncMock()
    )
    context = ContextWrapper(context=SimpleNamespace(event=event))
    result = await SendMessageToUserTool().call(context, messages=[])
    assert result == "error: messages parameter is empty or invalid."
    event.send.assert_not_awaited()
