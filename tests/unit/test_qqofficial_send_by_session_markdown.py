import asyncio
from types import SimpleNamespace

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType
from astrbot.core.platform.astr_message_event import MessageSesion
from astrbot.core.platform.sources.qqofficial.qqofficial_message_event import (
    QQOfficialMessageEvent,
)
from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    QQOfficialPlatformAdapter,
)


@pytest.mark.asyncio
async def test_send_by_session_common_uses_markdown_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = QQOfficialPlatformAdapter(
        platform_config={
            "appid": "test-appid",
            "secret": "test-secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        platform_settings={},
        event_queue=asyncio.Queue(),
    )

    captured: dict[str, object] = {}

    async def post_group_message(*, group_openid: str, **payload):
        captured["payload"] = payload
        return {"id": "sent-1"}

    adapter.client = SimpleNamespace(api=SimpleNamespace(post_group_message=post_group_message))

    session = MessageSesion(
        platform_name="qq_official",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="group-openid-1",
    )
    adapter._session_last_message_id[session.session_id] = "msg-1"
    adapter._session_scene[session.session_id] = "group"

    async def fake_parse(_message: MessageChain):
        return ("**hello**", None, None, None, None, None, None)

    monkeypatch.setattr(QQOfficialMessageEvent, "_parse_to_qqofficial", fake_parse)

    await adapter._send_by_session_common(session, MessageChain())

    payload = captured.get("payload")
    assert isinstance(payload, dict)
    assert payload["msg_type"] == 2
    assert payload["msg_id"] == "msg-1"
    assert "content" not in payload
    assert payload["markdown"] == {"content": "**hello**"}


@pytest.mark.asyncio
async def test_send_by_session_common_drops_markdown_for_media(monkeypatch: pytest.MonkeyPatch) -> None:
    adapter = QQOfficialPlatformAdapter(
        platform_config={
            "appid": "test-appid",
            "secret": "test-secret",
            "enable_group_c2c": True,
            "enable_guild_direct_message": False,
        },
        platform_settings={},
        event_queue=asyncio.Queue(),
    )

    captured: dict[str, object] = {}

    async def post_group_message(*, group_openid: str, **payload):
        captured["payload"] = payload
        return {"id": "sent-1"}

    adapter.client = SimpleNamespace(api=SimpleNamespace(post_group_message=post_group_message))

    session = MessageSesion(
        platform_name="qq_official",
        message_type=MessageType.GROUP_MESSAGE,
        session_id="group-openid-1",
    )
    adapter._session_last_message_id[session.session_id] = "msg-1"
    adapter._session_scene[session.session_id] = "group"

    async def fake_parse(_message: MessageChain):
        return ("hello", "base64-image", None, None, None, None, None)

    async def fake_upload_group_and_c2c_image(*_args, **_kwargs):
        return "media-1"

    monkeypatch.setattr(QQOfficialMessageEvent, "_parse_to_qqofficial", fake_parse)
    monkeypatch.setattr(
        QQOfficialMessageEvent,
        "upload_group_and_c2c_image",
        fake_upload_group_and_c2c_image,
    )

    await adapter._send_by_session_common(session, MessageChain())

    payload = captured.get("payload")
    assert isinstance(payload, dict)
    assert payload["msg_type"] == 7
    assert payload["msg_id"] == "msg-1"
    assert payload["media"] == "media-1"
    assert payload["content"] == "hello"
    assert "markdown" not in payload
