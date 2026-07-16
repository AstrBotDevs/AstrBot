import asyncio

import pytest

from astrbot.core.platform.sources.weixin_oc import weixin_oc_adapter
from astrbot.core.platform.sources.weixin_oc.weixin_oc_adapter import WeixinOCAdapter


class _Config(dict):
    def __init__(self, *args, calls: list[str], **kwargs):
        super().__init__(*args, **kwargs)
        self._calls = calls

    def save_config(self) -> None:
        self._calls.append("save_config")


@pytest.mark.asyncio
async def test_save_account_state_offloads_config_persistence(monkeypatch):
    calls: list[str] = []
    config = _Config(
        {
            "platform": [
                {
                    "id": "weixin-test",
                    "type": "weixin_oc",
                }
            ]
        },
        calls=calls,
    )

    async def fake_to_thread(func, /, *args, **kwargs):
        calls.append("to_thread")
        return func(*args, **kwargs)

    monkeypatch.setattr(weixin_oc_adapter, "astrbot_config", config)
    monkeypatch.setattr(weixin_oc_adapter.asyncio, "to_thread", fake_to_thread)

    adapter = object.__new__(WeixinOCAdapter)
    adapter.config = {"id": "weixin-test", "type": "weixin_oc"}
    adapter.token = "token"
    adapter.account_id = "account"
    adapter._sync_buf = "sync-buffer"
    adapter.base_url = "https://example.com"
    adapter._context_tokens = {"user": "context-token"}
    adapter._context_tokens_dirty = True
    adapter._account_state_save_lock = asyncio.Lock()
    adapter._sync_client_state = lambda: None

    await adapter._save_account_state()

    assert calls == ["to_thread", "save_config"]
    assert config["platform"][0]["weixin_oc_sync_buf"] == "sync-buffer"
    assert adapter._context_tokens_dirty is False
