import asyncio
import threading
from unittest.mock import AsyncMock, call

import dingtalk_stream
import pytest

from astrbot.api.message_components import At, Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
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


def test_message_chain_plain_text_extracts_text_only():
    assert (
        DingtalkPlatformAdapter._message_chain_plain_text(
            MessageChain([Plain("hello"), Plain(" world")])
        )
        == "hello world"
    )
    assert (
        DingtalkPlatformAdapter._message_chain_plain_text(
            MessageChain([Plain("hello"), At(qq="user-id")])
        )
        is None
    )
    assert DingtalkPlatformAdapter._message_chain_plain_text(MessageChain()) is None


@pytest.mark.asyncio
async def test_send_by_session_prefers_card_for_plain_text(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = True
    adapter.send_text_card_by_session = AsyncMock(return_value=True)
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("card content")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_awaited_once_with(session, "card content")
    adapter.send_message_chain_to_group.assert_not_awaited()
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_send_by_session_falls_back_when_card_send_fails(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = True
    adapter.send_text_card_by_session = AsyncMock(return_value=False)
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("fallback content")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_awaited_once_with(
        session,
        "fallback content",
    )
    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="conversation-id",
        robot_code="robot-code",
        message_chain=message,
    )
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_send_by_session_keeps_plain_text_normal_when_card_toggle_is_off(
    monkeypatch,
):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = False
    adapter.send_text_card_by_session = AsyncMock()
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("normal content")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_not_awaited()
    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="conversation-id",
        robot_code="robot-code",
        message_chain=message,
    )
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_send_by_session_keeps_mixed_messages_on_normal_path(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.client_id = "robot-code"
    adapter.config = {"id": "dingtalk"}
    adapter.send_plain_text_as_card = True
    adapter.send_text_card_by_session = AsyncMock()
    adapter.send_message_chain_to_group = AsyncMock()
    base_send_calls = []

    async def base_send(self, session, message_chain):
        base_send_calls.append((self, session, message_chain))

    monkeypatch.setattr(dingtalk_adapter.Platform, "send_by_session", base_send)

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    message = MessageChain([Plain("hello"), At(qq="user-id")])

    await adapter.send_by_session(session, message)

    adapter.send_text_card_by_session.assert_not_awaited()
    adapter.send_message_chain_to_group.assert_awaited_once_with(
        open_conversation_id="conversation-id",
        robot_code="robot-code",
        message_chain=message,
    )
    assert base_send_calls == [(adapter, session, message)]


@pytest.mark.asyncio
async def test_proactive_card_is_created_then_finalized(monkeypatch):
    class FakeResponse:
        status = 200

        async def text(self):
            return "{}"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    class FakeSession:
        def __init__(self):
            self.post_calls = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        def post(self, url, **kwargs):
            self.post_calls.append((url, kwargs))
            return FakeResponse()

    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.card_template_id = "template-id"
    adapter.card_content_key = "content"
    adapter.client_id = "robot-code"
    adapter.get_access_token = AsyncMock(return_value="access-token")
    adapter._finalize_proactive_card = AsyncMock(return_value=True)
    http_session = FakeSession()
    monkeypatch.setattr(
        dingtalk_adapter.aiohttp,
        "ClientSession",
        lambda: http_session,
    )

    session = MessageSession("dingtalk", MessageType.GROUP_MESSAGE, "conversation-id")
    result = await adapter.send_text_card_by_session(session, "future task result")

    assert result is True
    _, post_kwargs = http_session.post_calls[0]
    assert post_kwargs["json"]["cardData"]["cardParamMap"] == {"content": ""}
    out_track_id = post_kwargs["json"]["outTrackId"]
    adapter._finalize_proactive_card.assert_awaited_once_with(
        http_session=http_session,
        access_token="access-token",
        out_track_id=out_track_id,
        content="future task result",
    )


@pytest.mark.asyncio
async def test_proactive_card_animation_streams_full_content_in_steps(monkeypatch):
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.animate_proactive_card = True
    adapter.card_update_interval = 0.35
    adapter._put_proactive_card_content = AsyncMock(return_value=True)
    sleep = AsyncMock()
    monkeypatch.setattr(dingtalk_adapter.asyncio, "sleep", sleep)
    http_session = object()
    content = "abcdefghijklmnopqrstuvwxyz1234"

    result = await adapter._finalize_proactive_card(
        http_session=http_session,
        access_token="access-token",
        out_track_id="out-track-id",
        content=content,
    )

    assert result is True
    assert adapter._put_proactive_card_content.await_args_list == [
        call(
            http_session=http_session,
            access_token="access-token",
            out_track_id="out-track-id",
            content="",
            is_final=False,
        ),
        call(
            http_session=http_session,
            access_token="access-token",
            out_track_id="out-track-id",
            content=content[:8],
            is_final=False,
        ),
        call(
            http_session=http_session,
            access_token="access-token",
            out_track_id="out-track-id",
            content=content[:16],
            is_final=False,
        ),
        call(
            http_session=http_session,
            access_token="access-token",
            out_track_id="out-track-id",
            content=content[:24],
            is_final=False,
        ),
        call(
            http_session=http_session,
            access_token="access-token",
            out_track_id="out-track-id",
            content=content,
            is_final=True,
        ),
    ]
    assert sleep.await_count == 4


@pytest.mark.asyncio
async def test_proactive_card_animation_can_be_disabled():
    adapter = DingtalkPlatformAdapter.__new__(DingtalkPlatformAdapter)
    adapter.animate_proactive_card = False
    adapter._put_proactive_card_content = AsyncMock(return_value=True)
    http_session = object()

    result = await adapter._finalize_proactive_card(
        http_session=http_session,
        access_token="access-token",
        out_track_id="out-track-id",
        content="complete result",
    )

    assert result is True
    adapter._put_proactive_card_content.assert_awaited_once_with(
        http_session=http_session,
        access_token="access-token",
        out_track_id="out-track-id",
        content="complete result",
        is_final=True,
    )


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
