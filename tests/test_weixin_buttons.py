from pathlib import Path
from unittest.mock import AsyncMock, Mock

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
from astrbot.core.platform.sources.weixin_oc import weixin_oc_adapter
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter
from astrbot.core.platform.sources.weixin_official_account.weixin_offacc_event import (
    WeixinOfficialAccountPlatformEvent,
)


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


def _send_result_adapter(payload: dict) -> WeixinOCAdapter:
    adapter = object.__new__(WeixinOCAdapter)
    adapter.metadata = PlatformMetadata("weixin_oc", "Weixin OC", "weixin-test")
    adapter.token = "token"
    adapter.account_id = "bot-account"
    adapter._context_tokens = {"user": "context-token"}
    adapter.client = AsyncMock()
    adapter.client.request_json.return_value = payload
    adapter._build_cache_components_from_items = lambda _items: []
    adapter._message_text_from_item_list = lambda _items, include_ref_text=False: "hi"
    adapter._cache_recent_message = lambda *args, **kwargs: None
    return adapter


@pytest.mark.asyncio
async def test_sendmessage_warns_when_success_has_no_message_id(monkeypatch):
    warning = Mock()
    cache = Mock()
    monkeypatch.setattr(weixin_oc_adapter.logger, "warning", warning)
    adapter = _send_result_adapter({"ret": 0})
    adapter._cache_recent_message = cache

    sent = await adapter._send_items_to_session(
        "user",
        [{"type": 1, "text_item": {"text": "hi"}}],
    )

    assert sent is False
    warning.assert_called_once()
    assert "without message_id" in warning.call_args.args[0]
    cache.assert_not_called()


@pytest.mark.asyncio
async def test_sendmessage_uses_returned_message_id_without_warning(monkeypatch):
    warning = Mock()
    cached = []
    monkeypatch.setattr(weixin_oc_adapter.logger, "warning", warning)
    adapter = _send_result_adapter({"ret": 0, "message_id": "wx-message-1"})
    adapter._cache_recent_message = lambda *args, **kwargs: cached.append(kwargs)

    sent = await adapter._send_items_to_session(
        "user",
        [{"type": 1, "text_item": {"text": "hi"}}],
    )

    assert sent is True
    warning.assert_not_called()
    assert cached[0]["message_id"] == "wx-message-1"


@pytest.mark.asyncio
async def test_weixin_oc_media_send_reports_text_failure():
    adapter = object.__new__(WeixinOCAdapter)
    adapter.token = "token"
    adapter._resolve_media_file_path = AsyncMock(return_value=Path("image.png"))
    adapter._prepare_media_item = AsyncMock(return_value={"type": 2})
    adapter._send_items_to_session = AsyncMock(side_effect=[False, True])

    sent = await adapter._send_media_segment("user", object(), text="hi")

    assert sent is False
    assert adapter._send_items_to_session.await_count == 2
