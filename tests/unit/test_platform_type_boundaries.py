"""Verify platform payload and SDK boundaries repaired by type checking."""

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from botpy.http import Route
from wechatpy import parse_message

from astrbot.api.event import MessageChain
from astrbot.api.message_components import File, Image, Plain
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    PlatformMetadata,
)
from astrbot.core.platform import webhook_server
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.sources.discord.discord_platform_adapter import (
    DiscordPlatformAdapter,
)
from astrbot.core.platform.sources.misskey.misskey_event import MisskeyPlatformEvent
from astrbot.core.platform.sources.qqofficial.qqofficial_chunked_upload import (
    QQOfficialChunkedUploader,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
    QQOfficialWebhook,
)
from astrbot.core.platform.sources.slack.slack_event import SlackMessageEvent
from astrbot.core.platform.sources.wecom_ai_bot import WXBizJsonMsgCrypt as crypto
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_adapter import (
    WeixinOfficialAccountPlatformAdapter,
)


@pytest.mark.asyncio
async def test_discord_valid_callback_without_user_is_not_dispatched() -> None:
    adapter = object.__new__(DiscordPlatformAdapter)
    interaction = SimpleNamespace(user=None, data={"custom_id": "legacy-action"})

    assert (
        await adapter.convert_message(
            {"type": "interaction", "interaction": interaction}
        )
        is None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("visibility", ["specified", "home", "followers", "public"])
async def test_misskey_reply_preserves_original_audience(
    monkeypatch: pytest.MonkeyPatch, visibility: str
) -> None:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.session_id = "note-session"
    message.message_id = "original-note"
    message.sender = MessageMember("sender", "Alice")
    message.message = [Plain("input")]
    message.message_str = "input"
    message.raw_message = {
        "userId": "sender",
        "user": {"username": "alice"},
        "visibility": visibility,
        "visibleUserIds": ["recipient"],
    }
    client = SimpleNamespace(create_note=AsyncMock())
    completed = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send", completed)
    event = MisskeyPlatformEvent(
        "input",
        message,
        PlatformMetadata("misskey", "Misskey", "misskey-test"),
        "note-session",
        client,
    )
    chain = MessageChain([Plain("reply")])

    await event.send(chain)

    client.create_note.assert_awaited_once()
    sent = client.create_note.call_args
    assert "reply" in sent.args[0]
    assert sent.kwargs["reply_id"] == "original-note"
    assert sent.kwargs["visibility"] == visibility
    if visibility == "specified":
        assert set(sent.kwargs["visible_user_ids"]) == {"sender", "recipient"}
    else:
        assert sent.kwargs["visible_user_ids"] is None
    assert message.raw_message["visibleUserIds"] == ["recipient"]
    completed.assert_awaited_once_with(chain)


@pytest.mark.parametrize("reported_failure", [True, False])
def test_wecom_encrypt_failure_returns_error_without_decoding_missing_ciphertext(
    monkeypatch: pytest.MonkeyPatch, reported_failure: bool
) -> None:
    key = base64.b64encode(b"0123456789abcdef0123456789abcdef").decode().rstrip("=")
    cipher = crypto.WXBizJsonMsgCrypt("token", key, "receiver")
    error = crypto.ierror.WXBizMsgCrypt_EncryptAES_Error
    encrypt = Mock(return_value=(error if reported_failure else 0, None))
    monkeypatch.setattr(crypto.Prpcrypt, "encrypt", encrypt)

    assert cipher.EncryptMsg("payload", "nonce", "1700000000") == (error, None)
    encrypt.assert_called_once_with("payload", "receiver")


@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", [False, True])
async def test_qq_chunk_request_uses_real_sdk_route_and_preserves_timeout(
    sandbox: bool,
) -> None:
    response = SimpleNamespace(status=200, json=AsyncMock(return_value={"code": 0}))
    context = AsyncMock()
    context.__aenter__.return_value = response
    session = SimpleNamespace(request=Mock(return_value=context))
    http = SimpleNamespace(
        _session=session,
        _headers={"Authorization": "QQBot test-token"},
        is_sandbox=sandbox,
        check_session=AsyncMock(),
    )
    uploader = QQOfficialChunkedUploader(http)
    body = {"file_name": "sample.txt"}

    result = await uploader._request_json("POST", "/v2/users/u/upload_prepare", body)

    assert result == {"code": 0}
    http.check_session.assert_awaited_once()
    session.request.assert_called_once()
    request = session.request.call_args
    domain = Route.SANDBOX_DOMAIN if sandbox else Route.DOMAIN
    assert request.args == (
        "POST",
        f"{Route.SCHEME}://{domain}/v2/users/u/upload_prepare",
    )
    assert request.kwargs["headers"] is http._headers
    assert request.kwargs["json"] == body
    assert request.kwargs["timeout"].total == 300
    response.json.assert_awaited_once_with(content_type=None)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [None, [], "invalid", 1])
async def test_qq_webhook_rejects_nonobject_validation_before_signing(
    payload: object,
) -> None:
    webhook = object.__new__(QQOfficialWebhook)
    webhook.secret = "test-secret"
    webhook.webhook_validation = AsyncMock()
    request = SimpleNamespace(
        get_data=AsyncMock(return_value=json.dumps({"op": 13, "d": payload}).encode())
    )

    assert await webhook.handle_callback(request) == (
        {"error": "Invalid validation payload"},
        400,
    )
    webhook.webhook_validation.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("files", [None, [], [{}], [{"permalink": 123}]])
async def test_slack_malformed_receipt_does_not_repeat_upload_or_remove_local_file(
    tmp_path: Path, files: object
) -> None:
    source = tmp_path / "message.txt"
    source.write_bytes(b"local content")
    client = SimpleNamespace(
        files_upload_v2=AsyncMock(return_value={"ok": True, "files": files})
    )
    segment = File(file=str(source), name="message.txt")

    with pytest.raises(ValueError, match="Slack upload"):
        await SlackMessageEvent._from_segment_to_slack_block(segment, client)

    client.files_upload_v2.assert_awaited_once_with(
        file=b"local content", filename="message.txt"
    )
    assert source.read_bytes() == b"local content"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["text", "image"])
async def test_wechatpy_message_fields_keep_sdk_payload_values(kind: str) -> None:
    content = (
        "<Content><![CDATA[hello 世界]]></Content>"
        if kind == "text"
        else "<PicUrl><![CDATA[https://example.test/photo.jpg]]></PicUrl>"
    )
    raw = parse_message(
        "<xml><ToUserName><![CDATA[bot]]></ToUserName>"
        "<FromUserName><![CDATA[sender]]></FromUserName>"
        "<CreateTime>1700000000</CreateTime>"
        f"<MsgType><![CDATA[{kind}]]></MsgType>{content}"
        "<MsgId>123456</MsgId></xml>"
    )
    adapter = object.__new__(WeixinOfficialAccountPlatformAdapter)
    adapter.active_send_mode = False
    adapter.handle_msg = AsyncMock()

    message = await adapter.convert_message(raw)

    assert message is not None
    assert message.self_id == "bot"
    assert message.sender == MessageMember("sender", "sender")
    assert message.session_id == "sender"
    assert message.message_id == "123456"
    assert message.timestamp == 1700000000
    assert message.raw_message["message"] is raw
    if kind == "text":
        assert message.message_str == "hello 世界"
        assert isinstance(message.message[0], Plain)
        assert message.message[0].text == "hello 世界"
    else:
        assert isinstance(message.message[0], Image)
        assert message.message[0].url == "https://example.test/photo.jpg"
    adapter.handle_msg.assert_awaited_once_with(message)


@pytest.mark.asyncio
async def test_webhook_server_keeps_asgi_app_and_shutdown_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server = webhook_server.FastAPIWebhookServer("type-boundary")
    serve = AsyncMock()
    shutdown = AsyncMock()
    monkeypatch.setattr(webhook_server, "serve", serve)

    async def callback(request: webhook_server.WebhookRequest):
        return {"echo": await request.get_json()}, 202

    server.add_url_rule("/callback", callback, ["POST"])
    await server.run_task(host="127.0.0.1", port=8765, shutdown_trigger=shutdown)

    serve.assert_awaited_once()
    served = serve.call_args
    assert served.args[0] is server.app
    assert served.args[1].bind == ["127.0.0.1:8765"]
    assert served.kwargs["shutdown_trigger"] is shutdown
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://localhost"
    ) as client:
        response = await client.post("/callback", json={"message": "unchanged"})
    assert response.status_code == 202
    assert response.json() == {"echo": {"message": "unchanged"}}
