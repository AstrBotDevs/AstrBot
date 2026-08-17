import asyncio
import threading

import dingtalk_stream
import pytest

from astrbot.api.message_components import At, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.sources.dingtalk import dingtalk_adapter
from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
    DINGTALK_RECONNECT_INITIAL_DELAY,
    DINGTALK_RECONNECT_MAX_DELAY,
    DingtalkPlatformAdapter,
    _dingtalk_reconnect_delay,
)


def _dingtalk_group_message(**payload) -> dingtalk_stream.ChatbotMessage:
    """Build a DingTalk group callback message for adapter tests.

    Args:
        **payload: Callback fields that vary between test cases.

    Returns:
        A parsed DingTalk chatbot message.
    """
    return dingtalk_stream.ChatbotMessage.from_dict(
        {
            "conversationId": "conversation",
            "conversationType": "2",
            "createAt": 1_700_000_000_000,
            "msgId": "message",
            "senderId": "sender",
            "senderNick": "sender",
            "chatbotUserId": "bot",
            **payload,
        }
    )


def test_dingtalk_reconnect_delay_uses_exponential_backoff():
    assert [_dingtalk_reconnect_delay(i) for i in range(1, 5)] == [
        10,
        20,
        40,
        80,
    ]


def test_dingtalk_reconnect_delay_has_minimum_delay():
    assert _dingtalk_reconnect_delay(0) == DINGTALK_RECONNECT_INITIAL_DELAY
    assert _dingtalk_reconnect_delay(-1) == DINGTALK_RECONNECT_INITIAL_DELAY


def test_dingtalk_reconnect_delay_is_capped():
    assert _dingtalk_reconnect_delay(20) == DINGTALK_RECONNECT_MAX_DELAY


@pytest.mark.asyncio
async def test_dingtalk_reconnect_delay_wakes_on_terminate(monkeypatch):
    class ObservedEvent:
        def __init__(self) -> None:
            self._event = threading.Event()
            self.wait_started = threading.Event()
            self.wait_timeout: float | None = None

        def is_set(self) -> bool:
            return self._event.is_set()

        def set(self) -> None:
            self._event.set()

        def wait(self, timeout: float | None = None) -> bool:
            self.wait_timeout = timeout
            self.wait_started.set()
            return self._event.wait(timeout)

    class FailingClient:
        websocket = None

        async def start(self) -> None:
            raise RuntimeError("connect failed")

    terminated_event = ObservedEvent()
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_ = FailingClient()
    adapter._shutdown_event = threading.Event()
    adapter._terminated_event = terminated_event

    monkeypatch.setattr(dingtalk_adapter, "_dingtalk_reconnect_delay", lambda _: 60)

    run_task = asyncio.create_task(adapter.run())
    try:
        wait_started = await asyncio.to_thread(terminated_event.wait_started.wait, 1)
        assert wait_started
        assert terminated_event.wait_timeout == 60

        await adapter.terminate()
        await asyncio.wait_for(run_task, timeout=1)
    finally:
        if not run_task.done():
            await adapter.terminate()
            run_task.cancel()
            await asyncio.gather(run_task, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("use_markdown", "expected_key", "expected_param"),
    [
        (None, "sampleMarkdown", {"title": "AstrBot", "text": "first\nsecond"}),
        (False, "sampleText", {"content": "first\nsecond"}),
    ],
)
async def test_dingtalk_text_respects_markdown_mode(
    use_markdown,
    expected_key,
    expected_param,
):
    sent = []
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)

    async def capture_message(open_conversation_id, robot_code, msg_key, msg_param):
        sent.append((open_conversation_id, robot_code, msg_key, msg_param))

    adapter._send_group_message = capture_message
    chain = MessageChain().message("first\nsecond").use_markdown(use_markdown)

    await adapter._send_message_chain("group", "conversation", "robot", chain)

    assert sent == [("conversation", "robot", expected_key, expected_param)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {
            "atUsers": [{"dingtalkId": "bot"}],
            "isInAtList": True,
            "msgtype": "text",
            "text": {"content": " /server"},
        },
        {
            "atUsers": [{"dingtalkId": "bot"}],
            "isInAtList": True,
            "msgtype": "richText",
            "content": {
                "richText": [
                    {"text": "@ExampleBot"},
                    {"text": "/server"},
                ]
            },
        },
    ],
)
async def test_dingtalk_self_mention_produces_consistent_command_text(payload):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)

    result = await adapter.convert_msg(_dingtalk_group_message(**payload))

    assert result.message_str == "/server"
    assert len(result.message) == 2
    assert isinstance(result.message[0], At)
    assert result.message[0].qq == "bot"
    assert isinstance(result.message[1], Plain)
    assert result.message[1].text == "/server"


@pytest.mark.asyncio
async def test_dingtalk_rich_text_preserves_non_self_mention_text():
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    message = _dingtalk_group_message(
        atUsers=[{"dingtalkId": "another-user"}],
        isInAtList=False,
        msgtype="richText",
        content={
            "richText": [
                {"text": "@AnotherUser"},
                {"text": "/server"},
            ]
        },
    )

    result = await adapter.convert_msg(message)

    assert result.message_str == "@AnotherUser/server"
    assert len(result.message) == 3
    assert isinstance(result.message[0], At)
    assert result.message[0].qq == "another-user"
    assert isinstance(result.message[1], Plain)
    assert result.message[1].text == "@AnotherUser"
    assert isinstance(result.message[2], Plain)
    assert result.message[2].text == "/server"


@pytest.mark.asyncio
async def test_dingtalk_rich_text_preserves_other_leading_mention():
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    message = _dingtalk_group_message(
        atUsers=[{"dingtalkId": "another-user"}, {"dingtalkId": "bot"}],
        isInAtList=True,
        msgtype="richText",
        content={
            "richText": [
                {"text": "@AnotherUser"},
                {"text": "@ExampleBot"},
                {"text": "/server"},
            ]
        },
    )

    result = await adapter.convert_msg(message)

    assert result.message_str == "@AnotherUser@ExampleBot/server"
    assert isinstance(result.message[0], At)
    assert result.message[0].qq == "another-user"
    assert isinstance(result.message[1], At)
    assert result.message[1].qq == "bot"
    assert isinstance(result.message[2], Plain)
    assert result.message[2].text == "@AnotherUser"
