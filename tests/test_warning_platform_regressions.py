"""Exercise current platform contracts using real SDK and message objects."""

import asyncio
import base64
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import pytest
import pytest_asyncio
from botpy.http import Route
from PIL import Image as PillowImage
from telegram.error import BadRequest, TimedOut
from telegram.ext import ExtBot
from telegram.request import HTTPXRequest
from wechatpy.enterprise.messages import TextMessage as WecomTextMessage
from wechatpy.messages import TextMessage as OfficialAccountTextMessage

from astrbot.api.event import MessageChain
from astrbot.api.message_components import Image, Plain, Reply
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)
from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
from astrbot.core.platform.sources.wecom.wecom_adapter import WecomPlatformAdapter
from astrbot.core.platform.sources.wecom_ai_bot.wecomai_long_connection import (
    WecomAIBotLongConnectionClient,
)
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
    WeixinOfficialAccountServer,
)
from astrbot.core.utils.metrics import Metric


@pytest.fixture(autouse=True)
def disable_metric_upload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the telemetry I/O boundary without replacing platform classes."""
    monkeypatch.setattr(Metric, "upload", AsyncMock(return_value=None))


@pytest.fixture
def wechat_config() -> dict[str, str]:
    return {
        "id": "warning-platform-test",
        "appid": "test-app",
        "corpid": "test-corp",
        "secret": "test-secret",
        "token": "test-token",
        "port": "0",
        "encoding_aes_key": base64.b64encode(bytes(range(32))).decode().rstrip("="),
    }


def make_image(path: Path, color: str = "red") -> Image:
    with PillowImage.new("RGB", (2, 2), color) as image:
        image.save(path)
    return Image.fromFileSystem(path)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scene", "message_type", "recipient", "resource"),
    [
        ("group", MessageType.GROUP_MESSAGE, "group-1", "groups"),
        ("friend", MessageType.FRIEND_MESSAGE, "user-1", "users"),
    ],
)
async def test_webhook_sends_both_media_through_real_adapter(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    scene: str,
    message_type: MessageType,
    recipient: str,
    resource: str,
) -> None:
    """Shared send recursion must work on the separate webhook adapter class."""
    adapter = QQOfficialWebhookPlatformAdapter(
        {
            "id": "qq-webhook-test",
            "appid": "123",
            "secret": "test",
            "use_markdown": False,
        },
        {},
        asyncio.Queue(),
    )
    adapter.remember_session_scene(recipient, scene)
    paths = [tmp_path / "first.png", tmp_path / "second.png"]
    images = [make_image(paths[0], "red"), make_image(paths[1], "blue")]
    requests: list[tuple[str, dict[str, object]]] = []
    upload_path = f"/v2/{resource}/{recipient}/files"
    message_path = f"/v2/{resource}/{recipient}/messages"

    async def record_request(
        route: Route, *, json: dict[str, object]
    ) -> dict[str, object]:
        path = urlsplit(route.url).path
        assert route.method == "POST"
        assert path in {upload_path, message_path}
        requests.append((path, dict(json)))
        if path == upload_path:
            index = sum(path == upload_path for path, _ in requests)
            return {
                "file_uuid": f"file-{index}",
                "file_info": f"info-{index}",
                "ttl": 60,
            }
        return {"id": f"sent-{sum(path == message_path for path, _ in requests)}"}

    monkeypatch.setattr(
        adapter.client.http, "request", AsyncMock(side_effect=record_request)
    )
    try:
        await adapter.send_by_session(
            MessageSession("qq_official_webhook", message_type, recipient),
            MessageChain(chain=images),
        )
        assert [path for path, _ in requests] == [upload_path, message_path] * 2
        uploads = [payload for path, payload in requests if path == upload_path]
        deliveries = [payload for path, payload in requests if path == message_path]
        assert [payload["file_data"] for payload in uploads] == [
            base64.b64encode(path.read_bytes()).decode() for path in paths
        ]
        assert [payload["media"] for payload in deliveries] == [
            {"file_uuid": f"file-{index}", "file_info": f"info-{index}", "ttl": 60}
            for index in (1, 2)
        ]
        assert all(payload["msg_type"] == 7 for payload in deliveries)
    finally:
        await adapter.client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("command", ["aibot_msg_callback", "aibot_event_callback"])
async def test_wecom_long_connection_tracks_future_returning_handler(
    command: str,
) -> None:
    """An Awaitable callback may return a Future instead of a coroutine."""
    future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    started = asyncio.Event()
    completed = asyncio.Event()
    received: list[dict[str, object]] = []
    payload = {
        "cmd": command,
        "headers": {"req_id": "callback-1"},
        "body": {"text": "Hello"},
    }

    def handler(message: dict[str, object]) -> asyncio.Future[None]:
        received.append(message)
        started.set()
        return future

    client = WecomAIBotLongConnectionClient(
        bot_id="test-bot",
        secret="test-secret",
        ws_url="wss://invalid.example/ws",
        heartbeat_interval=30,
        message_handler=handler,
    )
    try:
        await client._handle_text_message(json.dumps(payload))
        await asyncio.wait_for(started.wait(), timeout=1)
        assert received == [payload]
        assert not future.done()
        tasks = tuple(client._message_handler_tasks)
        assert len(tasks) == 1
        tasks[0].add_done_callback(lambda task: completed.set())
        future.set_result(None)
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=1)
        await asyncio.wait_for(completed.wait(), timeout=1)
        assert not client._message_handler_tasks
    finally:
        future.cancel()
        remaining = tuple(client._message_handler_tasks)
        for task in remaining:
            task.cancel()
        await asyncio.gather(*remaining, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "expected"),
    [(b"Hello", "Hello"), ("你好".encode(), "你好"), (b"Hello\xff", "Hello\ufffd")],
)
async def test_wecom_sdk_bytes_become_text_before_dispatch(
    monkeypatch: pytest.MonkeyPatch,
    wechat_config: dict[str, str],
    content: bytes,
    expected: str,
) -> None:
    adapter = WecomPlatformAdapter(wechat_config, {}, asyncio.Queue())
    dispatch = AsyncMock(return_value=None)
    monkeypatch.setattr(adapter, "handle_msg", dispatch)
    source = WecomTextMessage(
        {
            "Content": content,
            "AgentID": "1",
            "FromUserName": "sender",
            "MsgId": "1",
            "CreateTime": "1",
            "ToUserName": "bot",
        }
    )
    result = await adapter.convert_message(source)
    assert isinstance(result, AstrBotMessage)
    dispatch.assert_awaited_once_with(result)
    assert result.raw_message is source
    assert result.message_str == expected
    assert isinstance(result.message_str, str)
    assert len(result.message) == 1
    assert isinstance(result.message[0], Plain)
    assert result.message[0].text == expected


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b" Hello ", "Hello"),
        ("你".encode() * 30, "你" * 24 + "..."),
        (b"Hello\xff", "Hello\ufffd"),
        (b" \t ", "空消息"),
    ],
)
def test_official_account_preview_decodes_sdk_bytes_before_truncating(
    wechat_config: dict[str, str], content: bytes, expected: str
) -> None:
    server = WeixinOfficialAccountServer(asyncio.Queue(), wechat_config, {})
    source = OfficialAccountTextMessage({"Content": content})
    result = server._preview(source)
    assert isinstance(result, str)
    assert result == expected


@dataclass
class TelegramTransport:
    client: ExtBot
    calls: dict[str, AsyncMock]


@pytest_asyncio.fixture
async def telegram_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[TelegramTransport]:
    """Keep the real SDK client and replace only outbound delivery methods."""
    request = HTTPXRequest()
    client = ExtBot("123456:test-token", request=request, get_updates_request=request)
    calls = {
        name: AsyncMock(return_value=None)
        for name in (
            "send_chat_action",
            "send_message",
            "edit_message_text",
            "send_photo",
            "send_animation",
            "send_voice",
            "send_document",
        )
    }
    for name, callback in calls.items():
        monkeypatch.setattr(ExtBot, name, callback)
    try:
        yield TelegramTransport(client, calls)
    finally:
        await request.shutdown()


def telegram_group_event(client: ExtBot) -> TelegramPlatformEvent:
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.self_id = "123456"
    message.session_id = "-100#42"
    message.group_id = "-100#42"
    message.message_id = "73"
    message.sender = MessageMember("1001", "Tester")
    message.message = [Plain("question")]
    message.message_str = "question"
    message.raw_message = None
    return TelegramPlatformEvent(
        message.message_str,
        message,
        PlatformMetadata("telegram", "Telegram test", "telegram-test"),
        message.session_id,
        client,
    )


def assert_integer_topic_actions(calls: dict[str, AsyncMock]) -> None:
    assert calls["send_chat_action"].await_count >= 1
    for call in calls["send_chat_action"].await_args_list:
        assert call.kwargs["chat_id"] == "-100"
        assert call.kwargs["message_thread_id"] == 42
        assert type(call.kwargs["message_thread_id"]) is int


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, TimedOut])
async def test_telegram_first_stream_send_preserves_failure_and_closes_source(
    telegram_transport: TelegramTransport, error_type: type[Exception]
) -> None:
    error = error_type("Send unavailable")
    calls = telegram_transport.calls
    calls["send_message"].side_effect = error
    closed = asyncio.Event()

    async def chunks() -> AsyncIterator[MessageChain]:
        try:
            yield MessageChain(chain=[Plain("delta")])
        finally:
            closed.set()

    source = chunks()
    try:
        event = telegram_group_event(telegram_transport.client)
        with pytest.raises(error_type) as caught:
            await event.send_streaming(source, use_fallback=True)
        assert caught.value is error
        calls["send_message"].assert_awaited_once_with(
            text="delta", chat_id="-100", message_thread_id=42
        )
        calls["edit_message_text"].assert_not_awaited()
        assert_integer_topic_actions(calls)
        assert closed.is_set()
    finally:
        await source.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "send_method", "media_key", "unused_method"),
    [
        (".png", "send_photo", "photo", "send_animation"),
        (".gif", "send_animation", "animation", "send_photo"),
    ],
)
async def test_telegram_media_resolves_once_and_uses_integer_routing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    telegram_transport: TelegramTransport,
    suffix: str,
    send_method: str,
    media_key: str,
    unused_method: str,
) -> None:
    path = tmp_path / f"media{suffix}"
    component = make_image(path)
    original_resolve = Image.convert_to_file_path
    resolutions: list[Image] = []

    async def resolve(image: Image) -> str:
        resolutions.append(image)
        return await original_resolve(image)

    monkeypatch.setattr(Image, "convert_to_file_path", resolve)
    assert not resolutions
    await TelegramPlatformEvent.send_with_client(
        telegram_transport.client,
        MessageChain(chain=[Reply(id="73"), component]),
        "-100#42",
    )
    assert resolutions == [component]
    calls = telegram_transport.calls
    calls[send_method].assert_awaited_once_with(
        **{
            media_key: str(path),
            "chat_id": "-100",
            "reply_to_message_id": 73,
            "message_thread_id": 42,
        }
    )
    calls[unused_method].assert_not_awaited()
    assert_integer_topic_actions(calls)


@pytest.mark.asyncio
async def test_telegram_voice_fallback_preserves_payload_and_integer_topic(
    tmp_path: Path, telegram_transport: TelegramTransport
) -> None:
    path = tmp_path / "voice.ogg"
    path.write_bytes(b"OggS")
    calls = telegram_transport.calls
    calls["send_voice"].side_effect = BadRequest("Voice_messages_forbidden")
    payload = {"chat_id": "-100", "reply_to_message_id": 73}
    original = payload.copy()
    await TelegramPlatformEvent._send_voice_with_fallback(
        telegram_transport.client,
        str(path),
        payload,
        caption="Transcript",
        user_name="-100",
        message_thread_id="42",
        use_media_action=True,
    )
    assert payload == original
    calls["send_voice"].assert_awaited_once_with(
        voice=str(path), **original, message_thread_id=42
    )
    calls["send_document"].assert_awaited_once_with(
        document=str(path), caption="Transcript", **original, message_thread_id=42
    )
    assert_integer_topic_actions(calls)
