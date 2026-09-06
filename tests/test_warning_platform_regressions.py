"""Behavioral coverage for platform SDK payload and lifecycle contracts."""

import asyncio
import inspect
import json
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.message.components import Image, Plain, Reply
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


def _message() -> AstrBotMessage:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.message_id = "73"
    message.sender = MessageMember(user_id="123", nickname="Sender")
    message.message = []
    return message


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("suffix", "method"), [(".gif", "send_animation"), (".png", "send_photo")]
)
async def test_telegram_media_preserves_numeric_routing_and_deferred_conversion(
    suffix: str, method: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent

    path = str(tmp_path / f"image{suffix}")
    convert = AsyncMock(return_value=path)
    monkeypatch.setattr(Image, "convert_to_file_path", convert)
    chain = MessageChain([Reply(id="73"), Image.fromFileSystem(path)])
    client = MagicMock()
    client.send_chat_action = AsyncMock()
    sender = AsyncMock()
    setattr(client, method, sender)
    convert.assert_not_awaited()

    await TelegramPlatformEvent.send_with_client(client, chain, "-100#42")

    convert.assert_awaited_once()
    assert sender.await_args is not None
    payload = sender.await_args.kwargs
    assert payload["chat_id"] == "-100"
    assert payload["message_thread_id"] == 42
    assert payload["reply_to_message_id"] == 73
    assert payload["animation" if suffix == ".gif" else "photo"] == path
    assert all(
        call.kwargs["message_thread_id"] == 42
        for call in client.send_chat_action.await_args_list
    )


@pytest.mark.asyncio
async def test_telegram_voice_fallback_keeps_topic_and_reply() -> None:
    from astrbot.core.platform.sources.telegram import tg_event

    client = MagicMock()
    client.send_chat_action = AsyncMock()
    client.send_voice = AsyncMock(
        side_effect=tg_event.BadRequest("Voice_messages_forbidden")
    )
    client.send_document = AsyncMock()
    payload: tg_event.TelegramSendPayload = {
        "chat_id": "-100",
        "reply_to_message_id": 73,
    }

    await tg_event.TelegramPlatformEvent._send_voice_with_fallback(
        client,
        "voice.ogg",
        payload,
        caption="Transcript",
        user_name="-100",
        message_thread_id="42",
        use_media_action=True,
    )

    client.send_document.assert_awaited_once_with(
        document="voice.ogg",
        caption="Transcript",
        chat_id="-100",
        reply_to_message_id=73,
        message_thread_id=42,
    )
    assert "message_thread_id" not in payload


@pytest.mark.asyncio
@pytest.mark.parametrize("stream_id", [None, "stream-1"])
async def test_qq_c2c_response_and_stream_ids_are_json_contracts(
    stream_id: str | None,
) -> None:
    from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
        QQOfficialMessageEvent,
        QQStreamPayload,
    )

    bot = MagicMock()
    response = {"id": "message-2", "timestamp": "2026-09-06T12:00:00Z"}
    bot.api._http.request = AsyncMock(return_value=response)
    event = QQOfficialMessageEvent(
        "",
        _message(),
        PlatformMetadata("qq_official", "QQ", id="qq"),
        "123",
        bot,
    )
    stream: QQStreamPayload = {"state": 1, "id": stream_id, "index": 0, "reset": False}

    result = await event.post_c2c_message("123", content="Hello", stream=stream)

    assert result == response
    request = bot.api._http.request.await_args
    assert request is not None
    assert request.args[0].url.endswith("/v2/users/123/messages")
    assert request.kwargs["json"]["stream"].get("id") == stream_id
    assert ("id" in request.kwargs["json"]["stream"]) == (stream_id is not None)
    assert "msg_id" not in request.kwargs["json"]
    assert stream["id"] == stream_id


@pytest.mark.asyncio
async def test_qq_webhook_multiple_media_uses_shared_session_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
        QQOfficialMessageEvent,
    )
    from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
        QQOfficialWebhookPlatformAdapter,
    )

    adapter = QQOfficialWebhookPlatformAdapter(
        {"id": "qq-test", "appid": "123", "secret": "test-secret"},
        {},
        asyncio.Queue(),
    )
    adapter.client.api.post_group_message = AsyncMock(return_value={"id": "sent"})
    adapter.remember_session_scene("group-1", "group")
    parse = AsyncMock(return_value=("caption", None, None, None, None, None, None))
    monkeypatch.setattr(QQOfficialMessageEvent, "_parse_to_qqofficial", parse)
    chain = MessageChain(
        [
            Image.fromURL("https://example.com/one.png"),
            Image.fromURL("https://example.com/two.png"),
        ]
    )

    await adapter.send_by_session(
        MessageSession("qq-test", MessageType.GROUP_MESSAGE, "group-1"), chain
    )

    assert parse.await_count == 2
    assert adapter.client.api.post_group_message.await_count == 2
    assert all(
        call.kwargs["group_openid"] == "group-1"
        for call in adapter.client.api.post_group_message.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [False, True])
async def test_qq_chunk_upload_uses_matching_sandbox_domain(sandbox: bool) -> None:
    from astrbot.core.platform.sources.qqofficial.qqofficial_chunked_upload import (
        QQOfficialChunkedUploader,
    )

    response = MagicMock()
    response.status = 200
    response.json = AsyncMock(return_value={"code": 0, "upload_id": "upload-1"})
    http = MagicMock()
    http.is_sandbox = sandbox
    http.check_session = AsyncMock()
    http._session.request.return_value.__aenter__.return_value = response
    uploader = QQOfficialChunkedUploader(http)

    result = await uploader._request_json("POST", "/v2/users/123/upload_prepare", {})

    domain = "sandbox.api.sgroup.qq.com" if sandbox else "api.sgroup.qq.com"
    assert (
        http._session.request.call_args.args[1]
        == f"https://{domain}/v2/users/123/upload_prepare"
    )
    assert result["upload_id"] == "upload-1"


@pytest.mark.asyncio
async def test_dingtalk_shutdown_keeps_a_bound_connection_method() -> None:
    from astrbot.core.platform.sources.dingtalk.dingtalk_adapter import (
        DingtalkPlatformAdapter,
    )

    adapter = DingtalkPlatformAdapter(
        {"id": "ding", "client_id": "123", "client_secret": "test-secret"},
        {},
        asyncio.Queue(),
    )
    websocket = MagicMock()
    websocket.close = AsyncMock()
    adapter.client_.websocket = websocket
    adapter._shutdown_event = threading.Event()

    await adapter.terminate()

    assert adapter._terminated_event.is_set()
    assert adapter._shutdown_event.is_set()
    assert inspect.ismethod(adapter.client_.open_connection)
    with pytest.raises(KeyboardInterrupt, match="Graceful shutdown"):
        adapter.client_.open_connection()
    websocket.close.assert_awaited_once_with(code=1000, reason="Graceful shutdown")


def test_mattermost_message_declares_and_tracks_downloaded_attachments(
    tmp_path: Path,
) -> None:
    from astrbot.core.platform.sources.mattermost.mattermost_event import (
        MattermostMessage,
        MattermostMessageEvent,
    )

    path = tmp_path / "attachment.txt"
    path.write_text("attachment", encoding="utf-8")
    message = MattermostMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.message = [Plain("File")]
    message.sender = MessageMember(user_id="123")
    message.temporary_file_paths.append(str(path))

    event = MattermostMessageEvent(
        "File",
        message,
        PlatformMetadata("mattermost", "Mattermost", id="mm"),
        "123",
        MagicMock(),
    )

    assert event._temporary_local_files == [str(path)]
    assert MattermostMessage().temporary_file_paths == []


@pytest.mark.asyncio
async def test_wecom_long_connection_accepts_future_returning_handlers() -> None:
    from astrbot.core.platform.sources.wecom_ai_bot.wecomai_long_connection import (
        WecomAIBotLongConnectionClient,
    )

    completion: asyncio.Future[None] = asyncio.get_running_loop().create_future()
    client = WecomAIBotLongConnectionClient(
        bot_id="123",
        secret="test-secret",
        ws_url="wss://example.com/ws",
        heartbeat_interval=30,
        message_handler=lambda payload: completion,
    )

    await client._handle_text_message(
        json.dumps(
            {
                "cmd": "aibot_msg_callback",
                "headers": {"req_id": "1"},
                "body": {},
            }
        )
    )
    assert len(client._message_handler_tasks) == 1
    completion.set_result(None)
    await asyncio.gather(*client._message_handler_tasks)
    assert not client._message_handler_tasks


@pytest.mark.asyncio
async def test_telegram_failed_initial_stream_send_does_not_use_unbound_message() -> (
    None
):
    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent

    client = MagicMock()
    client.send_chat_action = AsyncMock()
    client.send_message = AsyncMock(side_effect=RuntimeError("Send unavailable"))
    message = _message()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "-100#42"
    event = TelegramPlatformEvent(
        "",
        message,
        PlatformMetadata("telegram", "Telegram", id="tg"),
        "-100#42",
        client,
    )

    async def chunks():
        yield MessageChain([Plain("delta")])

    await event.send_streaming(chunks())

    assert client.send_message.await_count > 0
    assert all(
        call.kwargs["message_thread_id"] == 42
        for call in client.send_message.await_args_list
    )


@pytest.mark.asyncio
async def test_wecom_decodes_binary_text_before_building_message() -> None:
    from astrbot.core.platform.sources.wecom.wecom_adapter import (
        TextMessage,
        WecomPlatformAdapter,
    )

    raw = TextMessage(
        {
            "Content": b"Hello",
            "AgentID": "1",
            "FromUserName": "sender",
            "MsgId": "1",
            "CreateTime": "1",
            "ToUserName": "bot",
        }
    )
    adapter = WecomPlatformAdapter.__new__(WecomPlatformAdapter)
    handle_message = AsyncMock()
    adapter.handle_msg = handle_message

    await adapter.convert_message(raw)

    assert handle_message.await_args is not None
    message = handle_message.await_args.args[0]
    assert message.message_str == "Hello"


def test_weixin_preview_decodes_binary_text() -> None:
    from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
        TextMessage,
        WeixinOfficialAccountServer,
    )

    server = WeixinOfficialAccountServer.__new__(WeixinOfficialAccountServer)

    assert server._preview(TextMessage({"Content": b" Hello "})) == "Hello"
