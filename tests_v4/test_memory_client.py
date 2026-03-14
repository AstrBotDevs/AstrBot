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

    @pytest.mark.asyncio
    async def test_search_returns_empty_list_for_malformed_items(self):
        """search() should ignore malformed non-list item payloads."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"items": "bad"})

        client = MemoryClient(proxy)
        result = await client.search("test")

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


class TestMemoryClientGet:
    """Tests for MemoryClient.get() method."""

    @pytest.mark.asyncio
    async def test_get_returns_dict_value(self):
        """get() should return dict value from proxy response."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": {"theme": "dark"}})

        client = MemoryClient(proxy)
        result = await client.get("user_pref")

        proxy.call.assert_called_once_with("memory.get", {"key": "user_pref"})
        assert result == {"theme": "dark"}

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_value(self):
        """get() should return None when memory is absent."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": None})

        client = MemoryClient(proxy)
        result = await client.get("missing")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_none_for_non_dict_value(self):
        """get() should ignore malformed non-dict payloads."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": "bad"})

        client = MemoryClient(proxy)
        result = await client.get("bad")

        assert result is None


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


class TestMemoryClientSaveWithTTL:
    """Tests for MemoryClient.save_with_ttl() method."""

    @pytest.mark.asyncio
    async def test_save_with_ttl_calls_proxy(self):
        """save_with_ttl() should call proxy with key, value, and ttl_seconds."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        await client.save_with_ttl("temp_key", {"data": "value"}, ttl_seconds=3600)

        proxy.call.assert_called_once_with(
            "memory.save_with_ttl",
            {"key": "temp_key", "value": {"data": "value"}, "ttl_seconds": 3600},
        )

    @pytest.mark.asyncio
    async def test_save_with_ttl_raises_type_error_for_non_dict(self):
        """save_with_ttl() should raise TypeError for non-dict value."""
        proxy = AsyncMock(spec=CapabilityProxy)
        client = MemoryClient(proxy)

        with pytest.raises(
            TypeError, match="memory.save_with_ttl 的 value 必须是 dict"
        ):
            await client.save_with_ttl("key", "not a dict", ttl_seconds=60)

    @pytest.mark.asyncio
    async def test_save_with_ttl_raises_value_error_for_invalid_ttl(self):
        """save_with_ttl() should raise ValueError for ttl_seconds < 1."""
        proxy = AsyncMock(spec=CapabilityProxy)
        client = MemoryClient(proxy)

        with pytest.raises(ValueError, match="ttl_seconds 必须大于 0"):
            await client.save_with_ttl("key", {"data": 1}, ttl_seconds=0)

        with pytest.raises(ValueError, match="ttl_seconds 必须大于 0"):
            await client.save_with_ttl("key", {"data": 1}, ttl_seconds=-1)


class TestMemoryClientGetMany:
    """Tests for MemoryClient.get_many() method."""

    @pytest.mark.asyncio
    async def test_get_many_returns_items(self):
        """get_many() should return list of items with key and value."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(
            return_value={
                "items": [
                    {"key": "k1", "value": {"a": 1}},
                    {"key": "k2", "value": {"b": 2}},
                ]
            }
        )

        client = MemoryClient(proxy)
        result = await client.get_many(["k1", "k2"])

        proxy.call.assert_called_once_with("memory.get_many", {"keys": ["k1", "k2"]})
        assert len(result) == 2
        assert result[0]["key"] == "k1"
        assert result[0]["value"] == {"a": 1}

    @pytest.mark.asyncio
    async def test_get_many_returns_empty_list_for_malformed_response(self):
        """get_many() should return empty list for malformed response."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"items": "not a list"})

        client = MemoryClient(proxy)
        result = await client.get_many(["k1", "k2"])

        assert result == []

    @pytest.mark.asyncio
    async def test_get_many_returns_empty_list_for_missing_items(self):
        """get_many() should return empty list when items key missing."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        result = await client.get_many(["k1"])

        assert result == []


class TestMemoryClientDeleteMany:
    """Tests for MemoryClient.delete_many() method."""

    @pytest.mark.asyncio
    async def test_delete_many_returns_count(self):
        """delete_many() should return number of deleted items."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"deleted_count": 3})

        client = MemoryClient(proxy)
        result = await client.delete_many(["k1", "k2", "k3"])

        proxy.call.assert_called_once_with(
            "memory.delete_many", {"keys": ["k1", "k2", "k3"]}
        )
        assert result == 3

    @pytest.mark.asyncio
    async def test_delete_many_returns_zero_for_missing_count(self):
        """delete_many() should return 0 when deleted_count missing."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        result = await client.delete_many(["k1"])

        assert result == 0


class TestMemoryClientStats:
    """Tests for MemoryClient.stats() method."""

    @pytest.mark.asyncio
    async def test_stats_returns_total_items(self):
        """stats() should return total_items count."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"total_items": 42, "total_bytes": 1024})

        client = MemoryClient(proxy)
        result = await client.stats()

        proxy.call.assert_called_once_with("memory.stats", {})
        assert result["total_items"] == 42
        assert result["total_bytes"] == 1024

    @pytest.mark.asyncio
    async def test_stats_defaults_to_zero(self):
        """stats() should default total_items to 0 if missing."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = MemoryClient(proxy)
        result = await client.stats()

        assert result["total_items"] == 0
        assert result["total_bytes"] is None
