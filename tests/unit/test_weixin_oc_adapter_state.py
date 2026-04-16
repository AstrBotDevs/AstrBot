from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter


def _build_adapter_for_state_test(config: dict) -> WeixinOCAdapter:
    adapter = WeixinOCAdapter.__new__(WeixinOCAdapter)
    adapter.config = config
    adapter.token = None
    adapter.account_id = None
    adapter.base_url = "https://ilinkai.weixin.qq.com"
    adapter.cdn_base_url = "https://novac2c.cdn.weixin.qq.com/c2c"
    adapter.api_timeout_ms = 15000
    adapter._sync_buf = ""
    adapter._context_tokens = {}
    adapter._context_tokens_dirty = False
    adapter.client = SimpleNamespace(
        base_url="",
        cdn_base_url="",
        api_timeout_ms=0,
        token=None,
    )
    return adapter


def test_load_account_state_restores_context_tokens():
    adapter = _build_adapter_for_state_test(
        {
            "weixin_oc_context_tokens": {
                "user_1": "token_1",
                " user_2 ": " token_2 ",
                "": "ignored",
                "user_3": "",
            }
        }
    )

    adapter._load_account_state()

    assert adapter._context_tokens == {
        "user_1": "token_1",
        "user_2": "token_2",
    }


def test_load_account_state_ignores_invalid_context_token_payload():
    adapter = _build_adapter_for_state_test({"weixin_oc_context_tokens": "invalid"})

    adapter._load_account_state()

    assert adapter._context_tokens == {}


@pytest.mark.asyncio
async def test_save_account_state_persists_context_tokens(monkeypatch):
    config = {"id": "wx-test", "type": "weixin_oc"}
    adapter = _build_adapter_for_state_test(config)
    adapter.token = "bot-token"
    adapter.account_id = "account-id"
    adapter._sync_buf = "sync-buf"
    adapter._context_tokens = {
        "user_1": "token_1",
        " user_2 ": " token_2 ",
        "": "ignored",
        "user_3": "",
    }
    adapter._context_tokens_dirty = True

    platforms = [{"id": "wx-test", "type": "weixin_oc"}]
    save_called = {"value": False}

    fake_astrbot_config = SimpleNamespace(
        get=lambda key, default=None: platforms if key == "platform" else default,
        save_config=lambda: save_called.__setitem__("value", True),
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter.astrbot_config",
        fake_astrbot_config,
    )

    await adapter._save_account_state()

    expected_tokens = {"user_1": "token_1", "user_2": "token_2"}
    assert adapter._context_tokens == expected_tokens
    assert adapter.config["weixin_oc_context_tokens"] == expected_tokens
    assert platforms[0]["weixin_oc_context_tokens"] == expected_tokens
    assert adapter._context_tokens_dirty is False
    assert save_called["value"] is True


@pytest.mark.asyncio
async def test_handle_inbound_message_only_marks_dirty_on_context_token_change():
    adapter = _build_adapter_for_state_test({})
    adapter._context_tokens = {"user_1": "token_1"}
    adapter._item_list_to_components = AsyncMock(return_value=[])
    adapter._message_text_from_item_list = lambda item_list, include_ref_text=False: (
        "hello"
    )
    adapter._cache_recent_message = lambda *args, **kwargs: None
    adapter.meta = lambda: SimpleNamespace(id="wx-test")
    committed_events = []
    adapter.commit_event = committed_events.append

    same_token_message = {
        "from_user_id": "user_1",
        "context_token": "token_1",
        "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
        "create_time": 1,
    }

    await adapter._handle_inbound_message(same_token_message)

    assert adapter._context_tokens == {"user_1": "token_1"}
    assert adapter._context_tokens_dirty is False
    assert len(committed_events) == 1

    new_token_message = {
        "from_user_id": "user_1",
        "context_token": "token_2",
        "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
        "create_time": 1,
    }

    await adapter._handle_inbound_message(new_token_message)

    assert adapter._context_tokens == {"user_1": "token_2"}
    assert adapter._context_tokens_dirty is True
    assert len(committed_events) == 2
