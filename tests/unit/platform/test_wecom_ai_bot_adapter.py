import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.platform import MessageType
from astrbot.core.platform.astr_message_event import MessageSession
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter import (
    WecomAIBotAdapter,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_api import (
    WecomAIBotStreamMessageBuilder,
)
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_long_connection import (
    WecomAIBotLongConnectionClient,
)

pytestmark = pytest.mark.platform


def _adapter() -> WecomAIBotAdapter:
    adapter = WecomAIBotAdapter.__new__(WecomAIBotAdapter)
    adapter.bot_name = "AstrBot"
    adapter.encoding_aes_key = "fallback-aes-key"
    adapter.metadata = SimpleNamespace(
        name="wecom_ai_bot",
        description="",
        id="wecom-ai-test",
        support_proactive_message=True,
    )
    adapter.queue_mgr = SimpleNamespace()
    adapter.api_client = SimpleNamespace()
    adapter.webhook_client = None
    adapter.only_use_webhook_url_to_send = False
    adapter.initial_respond_text = ""
    adapter.friend_message_welcome_text = ""
    adapter._stream_plain_cache = {}
    adapter._send_long_connection_respond_msg = AsyncMock()
    adapter._send_long_connection_respond_welcome = AsyncMock()
    return adapter


def test_wecom_ai_bot_extract_session_id_uses_group_or_user_scope():
    adapter = _adapter()

    assert (
        adapter._extract_session_id({"chattype": "group", "chatid": "group-1"})
        == "wecom_ai_bot_wecomai_group-1"
    )
    assert (
        adapter._extract_session_id(
            {"chattype": "single", "from": {"userid": "user-1"}}
        )
        == "wecom_ai_bot_wecomai_user-1"
    )


@pytest.mark.asyncio
async def test_wecom_ai_bot_convert_message_text_removes_bot_mention_and_marks_friend():
    adapter = _adapter()

    result = await adapter.convert_message(
        {
            "message_data": {
                "msgtype": "text",
                "text": {"content": "@AstrBot hello there"},
                "from": {"userid": "user-1"},
                "chattype": "single",
            },
            "session_id": "wecom_ai_bot_wecomai_user-1",
        }
    )

    assert result.type == MessageType.FRIEND_MESSAGE
    assert result.session_id == "wecom_ai_bot_wecomai_user-1"
    assert result.sender.user_id == "user-1"
    assert result.message_str == "hello there"
    assert [type(component) for component in result.message] == [At, Plain]
    assert result.message[0].qq == "AstrBot"
    assert result.message[0].name == "AstrBot"
    assert result.message[1].text == "hello there"


@pytest.mark.asyncio
async def test_wecom_ai_bot_convert_message_mixed_collects_text_and_images(monkeypatch):
    adapter = _adapter()
    process_image = AsyncMock(side_effect=[(True, "img-b64-1"), (True, "img-b64-2")])
    monkeypatch.setattr(
        "astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter.process_encrypted_image",
        process_image,
    )

    result = await adapter.convert_message(
        {
            "message_data": {
                "msgtype": "mixed",
                "mixed": {
                    "msg_item": [
                        {"msgtype": "text", "text": {"content": "hello"}},
                        {
                            "msgtype": "image",
                            "image": {"url": "https://img/1", "aeskey": "aes-1"},
                        },
                        {"msgtype": "text", "text": {"content": "world"}},
                        {
                            "msgtype": "image",
                            "image": {"url": "https://img/2"},
                        },
                    ]
                },
                "from": {"userid": "user-2"},
                "chattype": "group",
            },
            "session_id": "wecom_ai_bot_wecomai_group-1",
        }
    )

    assert result.type == MessageType.GROUP_MESSAGE
    assert result.message_str == "hello world"
    assert [type(component) for component in result.message] == [Plain, Image, Image]
    assert result.message[0].text == "hello world"
    assert result.message[1].file == "base64://img-b64-1"
    assert result.message[2].file == "base64://img-b64-2"
    assert process_image.await_args_list[0].args == ("https://img/1", "aes-1")
    assert process_image.await_args_list[1].args == (
        "https://img/2",
        "fallback-aes-key",
    )


@pytest.mark.asyncio
async def test_wecom_ai_bot_convert_message_ignores_failed_image_processing(
    monkeypatch,
):
    adapter = _adapter()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter.process_encrypted_image",
        AsyncMock(return_value=(False, "decrypt failed")),
    )

    result = await adapter.convert_message(
        {
            "message_data": {
                "msgtype": "image",
                "image": {"url": "https://img/1", "aeskey": "aes-1"},
                "from": {"userid": "user-3"},
                "chattype": "single",
            },
            "session_id": "wecom_ai_bot_wecomai_user-3",
        }
    )

    assert result.message_str == "[image消息]"
    assert len(result.message) == 1
    assert isinstance(result.message[0], Plain)
    assert result.message[0].text == "[image消息]"


@pytest.mark.asyncio
async def test_wecom_ai_bot_send_by_session_requires_webhook_client():
    adapter = _adapter()

    with pytest.raises(RuntimeError, match="未配置企业微信消息推送 Webhook URL"):
        await adapter.send_by_session(
            MessageSession(
                platform_name="wecom-ai-test",
                message_type=MessageType.FRIEND_MESSAGE,
                session_id="wecom_ai_bot_wecomai_user-1",
            ),
            MessageChain([Plain("hello")]),
        )


@pytest.mark.asyncio
async def test_wecom_ai_bot_send_by_session_wraps_webhook_failures():
    adapter = _adapter()
    adapter.webhook_client = SimpleNamespace(
        send_message_chain=AsyncMock(side_effect=RuntimeError("network down"))
    )

    with pytest.raises(RuntimeError, match="企业微信消息推送失败"):
        await adapter.send_by_session(
            MessageSession(
                platform_name="wecom-ai-test",
                message_type=MessageType.FRIEND_MESSAGE,
                session_id="wecom_ai_bot_wecomai_user-1",
            ),
            MessageChain([Plain("hello")]),
        )


def test_wecom_ai_bot_create_event_marks_wake_flags_and_injects_dependencies():
    adapter = _adapter()
    adapter.webhook_client = SimpleNamespace()
    message = SimpleNamespace(
        message_str="hello",
        session_id="wecom_ai_bot_wecomai_user-1",
        type=MessageType.FRIEND_MESSAGE,
    )

    event = adapter.create_event(message)

    assert event.session_id == "wecom_ai_bot_wecomai_user-1"
    assert event.queue_mgr is adapter.queue_mgr
    assert event.api_client is adapter.api_client
    assert event.webhook_client is adapter.webhook_client
    assert event.long_connection_sender is adapter._send_long_connection_respond_msg
    assert event.get_extra("adapter_preconfigured") is True
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_message_enqueues_and_returns_initial_response(
    monkeypatch,
):
    adapter = _adapter()
    adapter.initial_respond_text = "processing"
    adapter.api_client = SimpleNamespace(
        encrypt_message=AsyncMock(return_value="encrypted")
    )
    adapter.queue_mgr = SimpleNamespace(set_pending_response=MagicMock())
    adapter._enqueue_message = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter.generate_random_string",
        lambda _length: "randtoken",
    )

    result = await adapter._process_message(
        {
            "msgtype": "text",
            "text": {"content": "hello"},
            "from": {"userid": "user-1"},
            "chattype": "single",
        },
        {"nonce": "n1", "timestamp": "t1"},
    )

    stream_id = "wecom_ai_bot_wecomai_user-1_randtoken"
    adapter._enqueue_message.assert_awaited_once_with(
        {
            "msgtype": "text",
            "text": {"content": "hello"},
            "from": {"userid": "user-1"},
            "chattype": "single",
        },
        {"nonce": "n1", "timestamp": "t1"},
        stream_id,
        "wecom_ai_bot_wecomai_user-1",
    )
    adapter.queue_mgr.set_pending_response.assert_called_once_with(
        stream_id,
        {"nonce": "n1", "timestamp": "t1"},
    )
    adapter.api_client.encrypt_message.assert_awaited_once_with(
        WecomAIBotStreamMessageBuilder.make_text_stream(
            stream_id,
            "processing",
            False,
        ),
        "n1",
        "t1",
    )
    assert result == "encrypted"


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_message_with_webhook_only_skips_initial_response(
    monkeypatch,
):
    adapter = _adapter()
    adapter.initial_respond_text = "processing"
    adapter.only_use_webhook_url_to_send = True
    adapter.webhook_client = SimpleNamespace()
    adapter.queue_mgr = SimpleNamespace(set_pending_response=MagicMock())
    adapter._enqueue_message = AsyncMock()
    adapter.api_client = SimpleNamespace(encrypt_message=AsyncMock())
    monkeypatch.setattr(
        "astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter.generate_random_string",
        lambda _length: "randtoken",
    )

    result = await adapter._process_message(
        {
            "msgtype": "text",
            "text": {"content": "hello"},
            "from": {"userid": "user-1"},
            "chattype": "single",
        },
        {"nonce": "n1", "timestamp": "t1"},
    )

    assert result is None
    adapter.api_client.encrypt_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_stream_without_back_queue_returns_finish_message():
    adapter = _adapter()
    adapter.api_client = SimpleNamespace(
        encrypt_message=AsyncMock(return_value="encrypted-end")
    )
    adapter.queue_mgr = SimpleNamespace(
        has_back_queue=MagicMock(return_value=False),
        is_stream_finished=MagicMock(return_value=False),
    )

    result = await adapter._process_message(
        {"msgtype": "stream", "stream": {"id": "stream-1"}},
        {"nonce": "n1", "timestamp": "t1"},
    )

    adapter.api_client.encrypt_message.assert_awaited_once_with(
        WecomAIBotStreamMessageBuilder.make_text_stream("stream-1", "", True),
        "n1",
        "t1",
    )
    assert result == "encrypted-end"


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_stream_returns_none_when_queue_empty():
    adapter = _adapter()
    empty_queue = SimpleNamespace(empty=lambda: True)
    adapter.queue_mgr = SimpleNamespace(
        has_back_queue=MagicMock(return_value=True),
        get_or_create_back_queue=MagicMock(return_value=empty_queue),
    )

    result = await adapter._process_message(
        {"msgtype": "stream", "stream": {"id": "stream-2"}},
        {"nonce": "n1", "timestamp": "t1"},
    )

    assert result is None


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_stream_aggregates_plain_and_images_and_marks_finish():
    adapter = _adapter()
    adapter.api_client = SimpleNamespace(
        encrypt_message=AsyncMock(return_value="encrypted-mixed")
    )
    queue = asyncio.Queue()
    await queue.put({"type": "plain", "data": "Hello", "streaming": True})
    await queue.put({"type": "image", "image_data": "aW1n"})
    await queue.put({"type": "complete"})
    remove_calls: list[tuple[str, bool]] = []
    adapter.queue_mgr = SimpleNamespace(
        has_back_queue=MagicMock(return_value=True),
        get_or_create_back_queue=MagicMock(return_value=queue),
        remove_queues=MagicMock(
            side_effect=lambda session_id, mark_finished=False: remove_calls.append(
                (session_id, mark_finished)
            )
        ),
    )

    result = await adapter._process_message(
        {"msgtype": "stream", "stream": {"id": "stream-3"}},
        {"nonce": "n1", "timestamp": "t1"},
    )

    expected_msg = WecomAIBotStreamMessageBuilder.make_mixed_stream(
        "stream-3",
        "Hello",
        [
            {
                "msgtype": "image",
                "image": {
                    "base64": "aW1n",
                    "md5": "b798abe6e1b1318ee36b0dcb3fb9e4d3",
                },
            }
        ],
        True,
    )
    adapter.api_client.encrypt_message.assert_awaited_once_with(
        expected_msg,
        "n1",
        "t1",
    )
    assert remove_calls == [("stream-3", True)]
    assert "stream-3" not in adapter._stream_plain_cache
    assert result == "encrypted-mixed"


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_event_enter_chat_returns_welcome_message():
    adapter = _adapter()
    adapter.friend_message_welcome_text = "welcome"
    adapter.api_client = SimpleNamespace(
        encrypt_message=AsyncMock(return_value="encrypted-welcome")
    )

    result = await adapter._process_message(
        {"msgtype": "event", "event": "enter_chat"},
        {"nonce": "n1", "timestamp": "t1"},
    )

    adapter.api_client.encrypt_message.assert_awaited_once_with(
        WecomAIBotStreamMessageBuilder.make_text("welcome"),
        "n1",
        "t1",
    )
    assert result == "encrypted-welcome"


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_long_connection_payload_enqueues_and_sends_initial_stream(
    monkeypatch,
):
    adapter = _adapter()
    adapter.initial_respond_text = "processing"
    adapter.queue_mgr = SimpleNamespace(set_pending_response=MagicMock())
    adapter._enqueue_message = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.wecom_ai_bot.wecomai_adapter.generate_random_string",
        lambda _length: "randtoken",
    )

    await adapter._process_long_connection_payload(
        {
            "cmd": "aibot_msg_callback",
            "headers": {"req_id": "req-1"},
            "body": {
                "msgtype": "text",
                "text": {"content": "hello"},
                "from": {"userid": "user-1"},
                "chattype": "single",
            },
        }
    )

    stream_id = "wecom_ai_bot_wecomai_user-1_randtoken"
    adapter._enqueue_message.assert_awaited_once()
    assert adapter._enqueue_message.await_args.args[2:] == (
        stream_id,
        "wecom_ai_bot_wecomai_user-1",
    )
    adapter.queue_mgr.set_pending_response.assert_called_once_with(
        stream_id,
        {"req_id": "req-1", "connection_mode": "long_connection"},
    )
    adapter._send_long_connection_respond_msg.assert_awaited_once_with(
        req_id="req-1",
        body={
            "msgtype": "stream",
            "stream": {
                "id": stream_id,
                "finish": False,
                "content": "processing",
            },
        },
    )


@pytest.mark.asyncio
async def test_wecom_ai_bot_process_long_connection_event_callback_sends_welcome():
    adapter = _adapter()
    adapter.friend_message_welcome_text = "welcome"

    await adapter._process_long_connection_payload(
        {
            "cmd": "aibot_event_callback",
            "headers": {"req_id": "req-2"},
            "body": {"event": {"eventtype": "enter_chat"}},
        }
    )

    adapter._send_long_connection_respond_welcome.assert_awaited_once_with("req-2")


@pytest.mark.asyncio
async def test_wecom_ai_long_connection_background_dispatch_allows_command_response():
    class _FakeWebSocket:
        def __init__(self) -> None:
            self.closed = False
            self.sent_payloads: list[dict[str, object]] = []

        async def send_json(self, payload: dict[str, object]) -> None:
            self.sent_payloads.append(payload)

    client = WecomAIBotLongConnectionClient(
        bot_id="bot-1",
        secret="secret-1",
        ws_url="wss://example.test/ws",
        heartbeat_interval=30,
        message_handler=AsyncMock(),
    )
    fake_ws = _FakeWebSocket()
    client._ws = fake_ws

    command_started = asyncio.Event()
    command_finished = asyncio.Event()

    async def _handler(_payload: dict[str, object]) -> None:
        command_started.set()
        ok = await client.send_command(
            "aibot_respond_msg",
            "req-1",
            {"msgtype": "text", "text": {"content": "hello"}},
        )
        assert ok is True
        command_finished.set()

    client.message_handler = _handler
    client._start_message_task(
        json.dumps(
            {
                "cmd": "aibot_msg_callback",
                "headers": {"req_id": "callback-1"},
                "body": {"msgtype": "text", "text": {"content": "hi"}},
            }
        )
    )

    await asyncio.wait_for(command_started.wait(), timeout=1.0)
    assert len(fake_ws.sent_payloads) == 1
    assert fake_ws.sent_payloads[0]["cmd"] == "aibot_respond_msg"

    await client._handle_text_message(
        json.dumps(
            {
                "errcode": 0,
                "errmsg": "ok",
                "headers": {"req_id": "req-1"},
            }
        )
    )

    await asyncio.wait_for(command_finished.wait(), timeout=1.0)
    if client._message_tasks:
        await asyncio.gather(*list(client._message_tasks), return_exceptions=True)
