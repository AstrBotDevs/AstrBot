import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.api.event import MessageChain
from astrbot.api.message_components import (
    ActionRow,
    Button,
    Plain,
)
from astrbot.api.platform import AstrBotMessage, MessageMember, MessageType
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.platform import Platform
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter
from astrbot.core.platform.sources.weixin_official_account import weixin_offacc_adapter
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_event import (
    WeixinOfficialAccountPlatformEvent,
)


def test_weixin_official_account_client_applies_proxy_to_http_session(monkeypatch):
    client = SimpleNamespace(_http=SimpleNamespace(proxies={}))
    calls = []

    def create_client(*args, **kwargs):
        calls.append((args, kwargs))
        return client

    monkeypatch.setattr(weixin_offacc_adapter, "WeChatClient", create_client)
    monkeypatch.setattr(
        weixin_offacc_adapter,
        "WeixinOfficialAccountServer",
        lambda *args: SimpleNamespace(callback=None, active_send_mode=False),
    )
    weixin_offacc_adapter.WeixinOfficialAccountPlatformAdapter(
        {
            "id": "weixin-test",
            "port": 8080,
            "appid": "app",
            "secret": "secret",
            "proxy": {
                "mode": "custom",
                "type": "socks5",
                "address": "127.0.0.1:1080",
            },
        },
        {},
        asyncio.Queue(),
    )

    assert calls == [(("app", "secret"), {})]
    assert client._http.proxies == {
        "http": "socks5://127.0.0.1:1080",
        "https": "socks5://127.0.0.1:1080",
    }


def _button_row(*, fallback_text: str | None = None) -> ActionRow:
    return ActionRow(
        buttons=[
            Button(
                id="docs",
                label="查看文档",
                action=Button.UrlAction(url="https://example.com/docs"),
            ),
            Button(
                id="confirm",
                label="确认",
                action=Button.CallbackAction(data={"confirmed": True}),
            ),
        ],
        fallback_text=fallback_text,
    )


@pytest.mark.asyncio
async def test_weixin_official_account_buttons_fall_back_to_text(monkeypatch):
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.sender = MessageMember("user", "User")
    message.message = []
    message.message_str = ""
    message.raw_message = {"active_send_mode": False}
    output = {"cached_xml": []}
    event = WeixinOfficialAccountPlatformEvent(
        message_str="",
        message_obj=message,
        platform_meta=PlatformMetadata(
            "weixin_official_account",
            "Weixin Official Account",
            "weixin-test",
        ),
        session_id="user",
        client=object(),
        message_out=output,
    )
    monkeypatch.setattr(AstrMessageEvent, "send", AsyncMock())

    await event.send(
        MessageChain([Plain("正文"), _button_row(fallback_text="请回复 yes 确认")])
    )

    assert output["cached_xml"] == [
        "正文",
        "查看文档: https://example.com/docs\n请回复 yes 确认",
    ]


@pytest.mark.asyncio
async def test_weixin_oc_buttons_fall_back_to_text(monkeypatch):
    adapter = object.__new__(WeixinOCAdapter)
    adapter.metadata = PlatformMetadata("weixin_oc", "Weixin OC", "weixin-test")
    adapter._send_to_session = AsyncMock(return_value=True)
    monkeypatch.setattr(Platform, "send_by_session", AsyncMock())
    session = MessageSession(
        platform_name="weixin-test",
        message_type=MessageType.FRIEND_MESSAGE,
        session_id="user",
    )

    await adapter.send_by_session(
        session,
        MessageChain([Plain("正文"), _button_row()]),
    )

    adapter._send_to_session.assert_awaited_once_with(
        "user",
        "正文\n查看文档: https://example.com/docs\n"
        "可选操作：确认（当前平台不支持按钮，请发送选项名称）",
    )
