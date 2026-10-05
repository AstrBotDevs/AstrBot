import pytest

from astrbot.core.message.components import Forward, Plain
from astrbot.core.platform.sources.aiocqhttp.aiocqhttp_platform_adapter import (
    AiocqhttpAdapter,
)


class _FakeEvent(dict):
    def __getattr__(self, name):
        return self[name]


class _FakeBot:
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    async def call_action(self, action, **params):
        self.calls.append((action, params))
        forward_id = params.get("message_id") or params.get("id")
        key = (action, str(forward_id))
        if key not in self.responses:
            raise RuntimeError(f"no mock response for {key}")
        return self.responses[key]


def _make_group_event(message):
    return _FakeEvent(
        {
            "self_id": 10000,
            "post_type": "message",
            "message_type": "group",
            "message_id": 123,
            "group_id": 456,
            "group_name": "test group",
            "sender": {
                "user_id": 20000,
                "nickname": "Alice",
                "card": "",
            },
            "message": message,
        }
    )


@pytest.mark.asyncio
async def test_aiocqhttp_forward_segment_expands_forward_text():
    adapter = object.__new__(AiocqhttpAdapter)
    adapter.bot = _FakeBot(
        {
            (
                "get_forward_msg",
                "fwd_1",
            ): {
                "data": {
                    "messages": [
                        {
                            "sender": {"nickname": "Alice"},
                            "message": [{"type": "text", "data": {"text": "hello"}}],
                        },
                        {
                            "sender": {"nickname": "Bot", "user_id": 10000},
                            "message": [
                                {
                                    "type": "text",
                                    "data": {"text": "bot reply"},
                                }
                            ],
                        },
                    ]
                }
            },
        }
    )

    abm = await adapter._convert_handle_message_event(
        _make_group_event(
            [
                {"type": "text", "data": {"text": "context"}},
                {"type": "forward", "data": {"id": "fwd_1"}},
            ]
        )
    )

    assert isinstance(abm.message[0], Plain)
    assert isinstance(abm.message[1], Forward)
    assert isinstance(abm.message[2], Plain)
    assert abm.message[1].id == "fwd_1"
    assert abm.message_str == "context\nAlice: hello\nBot: bot reply"
    assert abm.message[2].text == "Alice: hello\nBot: bot reply"


@pytest.mark.asyncio
async def test_aiocqhttp_forward_segment_keeps_placeholder_when_fetch_fails():
    adapter = object.__new__(AiocqhttpAdapter)
    adapter.bot = _FakeBot({})

    abm = await adapter._convert_handle_message_event(
        _make_group_event([{"type": "forward", "data": {"id": "missing"}}])
    )

    assert len(abm.message) == 1
    assert isinstance(abm.message[0], Forward)
    assert abm.message[0].id == "missing"
    assert abm.message_str == "[Forward Message]"
