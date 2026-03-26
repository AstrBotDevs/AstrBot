from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.clients._proxy import CapabilityProxy
from astrbot_sdk.clients.memory import MemoryClient
from astrbot_sdk.clients.metadata import MetadataClient


class _FakeProxy:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, dict(payload)))
        return dict(self.responses.get(name, {}))


@pytest.mark.asyncio
async def test_memory_get_many_skips_non_dict_items() -> None:
    proxy = _FakeProxy(
        {
            "memory.get_many": {
                "items": [
                    {"key": "pref1", "value": {"theme": "dark"}},
                    ["unexpected"],
                    None,
                    {"key": "pref2", "value": None},
                ]
            }
        }
    )
    client = MemoryClient(proxy)  # type: ignore[arg-type]

    items = await client.get_many(["pref1", "pref2"])

    assert items == [
        {"key": "pref1", "value": {"theme": "dark"}},
        {"key": "pref2", "value": None},
    ]


@pytest.mark.asyncio
async def test_capability_proxy_ignores_magicmock_placeholder_attributes() -> None:
    peer = MagicMock()
    peer.invoke = AsyncMock(return_value={})
    proxy = CapabilityProxy(peer)

    result = await proxy.call("metadata.get_plugin", {"name": "demo"})

    assert result == {}
    peer.invoke.assert_awaited_once_with(
        "metadata.get_plugin",
        {"name": "demo"},
        stream=False,
    )


@pytest.mark.asyncio
async def test_metadata_client_rejects_cross_plugin_config_access() -> None:
    proxy = _FakeProxy(
        {
            "metadata.get_plugin_config": {
                "config": {"api_key": "hidden"},
            }
        }
    )
    client = MetadataClient(proxy, plugin_id="current-plugin")

    with pytest.raises(PermissionError, match="只允许访问当前插件自己的配置"):
        await client.get_plugin_config("other-plugin")

    assert proxy.calls == []
