"""
Tests for clients/memory.py - MemoryClient implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.clients.memory import MemoryClient
from astrbot_sdk.clients._proxy import CapabilityProxy


class TestMemoryClientInit:
    """Tests for MemoryClient initialization."""

    def test_init_with_proxy(self):
        """MemoryClient should store proxy reference."""
        proxy = MagicMock(spec=CapabilityProxy)
        client = MemoryClient(proxy)
        assert client._proxy is proxy


class TestMemoryClientSearch:
    """Tests for MemoryClient.search() method."""

    @pytest.mark.asyncio
    async def test_search_returns_items(self):
        """search() should return list of items."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(
            return_value={
                "items": [
                    {"id": "1", "content": "first"},
                    {"id": "2", "content": "second"},
                ]
            }
        )

        client = MemoryClient(proxy)
        result = await client.search("test query")

        proxy.call.assert_called_once_with(
            "memory.search",
            {"query": "test query"},
        )
        assert len(result) == 2
        assert result[0]["content"] == "first"

    @pytest.mark.asyncio
    async def test_search_returns_empty_list_for_no_results(self):
        """search() should return empty list when no items found."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        result = await client.search("nonexistent")

        assert result == []

    @pytest.mark.asyncio
    async def test_search_with_empty_query(self):
        """search() should work with empty query."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"items": []})

        client = MemoryClient(proxy)
        result = await client.search("")

        proxy.call.assert_called_once_with("memory.search", {"query": ""})
        assert result == []


class TestMemoryClientSave:
    """Tests for MemoryClient.save() method."""

    @pytest.mark.asyncio
    async def test_save_with_key_and_value(self):
        """save() should call proxy with key and value."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.save("my_key", {"data": "value"})

        proxy.call.assert_called_once_with(
            "memory.save",
            {"key": "my_key", "value": {"data": "value"}},
        )

    @pytest.mark.asyncio
    async def test_save_with_extra_kwargs(self):
        """save() should merge extra kwargs into value."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.save("key", {"base": 1}, extra="added", another=2)

        call_args = proxy.call.call_args[0][1]
        assert call_args["value"] == {"base": 1, "extra": "added", "another": 2}

    @pytest.mark.asyncio
    async def test_save_with_only_kwargs(self):
        """save() should work with only kwargs (no value)."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.save("key", name="test", count=5)

        call_args = proxy.call.call_args[0][1]
        assert call_args["value"] == {"name": "test", "count": 5}

    @pytest.mark.asyncio
    async def test_save_with_none_value(self):
        """save() should handle None value with kwargs."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.save("key", None, field="value")

        call_args = proxy.call.call_args[0][1]
        assert call_args["value"] == {"field": "value"}

    @pytest.mark.asyncio
    async def test_save_with_empty_value_and_no_kwargs(self):
        """save() should work with empty dict."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.save("key", {})

        proxy.call.assert_called_once_with(
            "memory.save",
            {"key": "key", "value": {}},
        )

    @pytest.mark.asyncio
    async def test_save_raises_type_error_for_non_dict_value(self):
        """save() should raise TypeError for non-dict value."""
        proxy = AsyncMock(spec=CapabilityProxy)

        client = MemoryClient(proxy)

        with pytest.raises(TypeError, match="memory.save 的 value 必须是 dict"):
            await client.save("key", "not a dict")

    @pytest.mark.asyncio
    async def test_save_raises_type_error_for_list_value(self):
        """save() should raise TypeError for list value."""
        proxy = AsyncMock(spec=CapabilityProxy)

        client = MemoryClient(proxy)

        with pytest.raises(TypeError, match="memory.save 的 value 必须是 dict"):
            await client.save("key", [1, 2, 3])


class TestMemoryClientDelete:
    """Tests for MemoryClient.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_calls_proxy_with_key(self):
        """delete() should call proxy with correct key."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.delete("to_delete")

        proxy.call.assert_called_once_with("memory.delete", {"key": "to_delete"})

    @pytest.mark.asyncio
    async def test_delete_with_empty_key(self):
        """delete() should work with empty string key."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.delete("")

        proxy.call.assert_called_once_with("memory.delete", {"key": ""})
