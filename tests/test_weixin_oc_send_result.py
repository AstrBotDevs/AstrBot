from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.weixin_oc import weixin_oc_adapter
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter


def _adapter(payload: dict) -> WeixinOCAdapter:
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
    monkeypatch.setattr(weixin_oc_adapter.logger, "warning", warning)
    adapter = _adapter({"ret": 0})

    sent = await adapter._send_items_to_session(
        "user",
        [{"type": 1, "text_item": {"text": "hi"}}],
    )

    assert sent is True
    warning.assert_called_once()
    assert "without message_id" in warning.call_args.args[0]


@pytest.mark.asyncio
async def test_sendmessage_uses_returned_message_id_without_warning(monkeypatch):
    warning = Mock()
    cached = []
    monkeypatch.setattr(weixin_oc_adapter.logger, "warning", warning)
    adapter = _adapter({"ret": 0, "message_id": "wx-message-1"})
    adapter._cache_recent_message = lambda *args, **kwargs: cached.append(kwargs)

    sent = await adapter._send_items_to_session(
        "user",
        [{"type": 1, "text_item": {"text": "hi"}}],
    )

    assert sent is True
    warning.assert_not_called()
    assert cached[0]["message_id"] == "wx-message-1"
