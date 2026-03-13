"""
Tests for clients/db.py - DBClient implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.clients.db import DBClient
from astrbot_sdk.clients._proxy import CapabilityProxy


class TestDBClientInit:
    """Tests for DBClient initialization."""

    def test_init_with_proxy(self):
        """DBClient should store proxy reference."""
        proxy = MagicMock(spec=CapabilityProxy)
        client = DBClient(proxy)
        assert client._proxy is proxy


class TestDBClientGet:
    """Tests for DBClient.get() method."""

    @pytest.mark.asyncio
    async def test_get_returns_dict_value(self):
        """get() should return dict value from proxy response."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": {"data": "test"}})

        client = DBClient(proxy)
        result = await client.get("my_key")

        proxy.call.assert_called_once_with("db.get", {"key": "my_key"})
        assert result == {"data": "test"}

    @pytest.mark.asyncio
    async def test_get_returns_none_for_missing_key(self):
        """get() should return None when value is not found."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": None})

        client = DBClient(proxy)
        result = await client.get("missing_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_returns_scalar_value(self):
        """get() should preserve non-dict scalar values."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": True})

        client = DBClient(proxy)
        result = await client.get("my_key")

        assert result is True

    @pytest.mark.asyncio
    async def test_get_returns_none_when_value_key_missing(self):
        """get() should return None when 'value' key is missing in response."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = DBClient(proxy)
        result = await client.get("my_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_with_empty_key(self):
        """get() should work with empty string key."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": {"empty": True}})

        client = DBClient(proxy)
        result = await client.get("")

        proxy.call.assert_called_once_with("db.get", {"key": ""})
        assert result == {"empty": True}


class TestDBClientSet:
    """Tests for DBClient.set() method."""

    @pytest.mark.asyncio
    async def test_set_calls_proxy_with_key_and_value(self):
        """set() should call proxy with correct parameters."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = DBClient(proxy)
        await client.set("test_key", {"name": "value"})

        proxy.call.assert_called_once_with(
            "db.set",
            {"key": "test_key", "value": {"name": "value"}},
        )

    @pytest.mark.asyncio
    async def test_set_with_empty_dict(self):
        """set() should work with empty dict value."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = DBClient(proxy)
        await client.set("empty", {})

        proxy.call.assert_called_once_with("db.set", {"key": "empty", "value": {}})

    @pytest.mark.asyncio
    async def test_set_with_nested_dict(self):
        """set() should work with nested dict."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = DBClient(proxy)
        await client.set("nested", {"level1": {"level2": {"level3": "deep"}}})

        proxy.call.assert_called_once_with(
            "db.set",
            {"key": "nested", "value": {"level1": {"level2": {"level3": "deep"}}}},
        )

    @pytest.mark.asyncio
    async def test_set_accepts_scalar_value(self):
        """set() should accept scalar JSON values."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})
        client = DBClient(proxy)

        await client.set("flag", True)

        proxy.call.assert_called_once_with(
            "db.set",
            {"key": "flag", "value": True},
        )


class TestDBClientDelete:
    """Tests for DBClient.delete() method."""

    @pytest.mark.asyncio
    async def test_delete_calls_proxy_with_key(self):
        """delete() should call proxy with correct key."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = DBClient(proxy)
        await client.delete("to_delete")

        proxy.call.assert_called_once_with("db.delete", {"key": "to_delete"})

    @pytest.mark.asyncio
    async def test_delete_with_empty_key(self):
        """delete() should work with empty string key."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = DBClient(proxy)
        await client.delete("")

        proxy.call.assert_called_once_with("db.delete", {"key": ""})


class TestDBClientList:
    """Tests for DBClient.list() method."""

    @pytest.mark.asyncio
    async def test_list_returns_keys(self):
        """list() should return list of keys."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"keys": ["key1", "key2", "key3"]})

        client = DBClient(proxy)
        result = await client.list()

        proxy.call.assert_called_once_with("db.list", {"prefix": None})
        assert result == ["key1", "key2", "key3"]

    @pytest.mark.asyncio
    async def test_list_with_prefix(self):
        """list() should pass prefix parameter."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"keys": ["user:1", "user:2"]})

        client = DBClient(proxy)
        result = await client.list(prefix="user:")

        proxy.call.assert_called_once_with("db.list", {"prefix": "user:"})
        assert result == ["user:1", "user:2"]

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_when_no_keys(self):
        """list() should return empty list when no keys found."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = DBClient(proxy)
        result = await client.list()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_converts_non_string_items(self):
        """list() should convert non-string items to string."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"keys": [123, 456]})

        client = DBClient(proxy)
        result = await client.list()

        assert result == ["123", "456"]

    @pytest.mark.asyncio
    async def test_list_returns_empty_list_for_malformed_keys(self):
        """list() should ignore malformed non-list key payloads."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"keys": "not-a-list"})

        client = DBClient(proxy)
        result = await client.list()

        assert result == []

    @pytest.mark.asyncio
    async def test_list_with_none_prefix(self):
        """list() should handle None prefix."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"keys": []})

        client = DBClient(proxy)
        result = await client.list(prefix=None)

        proxy.call.assert_called_once_with("db.list", {"prefix": None})
        assert result == []


class TestDBClientGetMany:
    """Tests for DBClient.get_many() method."""

    @pytest.mark.asyncio
    async def test_get_many_returns_mapping(self):
        proxy = MagicMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(
            return_value={
                "items": [
                    {"key": "a", "value": 1},
                    {"key": "b", "value": None},
                ]
            }
        )
        client = DBClient(proxy)

        result = await client.get_many(["a", "b"])

        proxy.call.assert_called_once_with("db.get_many", {"keys": ["a", "b"]})
        assert result == {"a": 1, "b": None}

    @pytest.mark.asyncio
    async def test_get_many_returns_empty_dict_for_malformed_items(self):
        proxy = MagicMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"items": "not-a-list"})
        client = DBClient(proxy)

        result = await client.get_many(["a"])

        assert result == {}


class TestDBClientSetMany:
    """Tests for DBClient.set_many() method."""

    @pytest.mark.asyncio
    async def test_set_many_accepts_mapping(self):
        proxy = MagicMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})
        client = DBClient(proxy)

        await client.set_many({"a": 1, "b": 2})

        proxy.call.assert_called_once_with(
            "db.set_many",
            {"items": [{"key": "a", "value": 1}, {"key": "b", "value": 2}]},
        )

    @pytest.mark.asyncio
    async def test_set_many_accepts_sequence_pairs(self):
        proxy = MagicMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})
        client = DBClient(proxy)

        await client.set_many([("a", True), ("b", {"x": 1})])

        proxy.call.assert_called_once_with(
            "db.set_many",
            {"items": [{"key": "a", "value": True}, {"key": "b", "value": {"x": 1}}]},
        )


class TestDBClientWatch:
    """Tests for DBClient.watch() method."""

    @pytest.mark.asyncio
    async def test_watch_calls_proxy_stream_and_yields_events(self):
        async def gen():
            yield {"op": "set", "key": "a", "value": 1}
            yield {"op": "delete", "key": "a", "value": None}

        proxy = MagicMock(spec=CapabilityProxy)
        proxy.stream = MagicMock(return_value=gen())
        client = DBClient(proxy)

        iterator = client.watch()

        proxy.stream.assert_called_once_with("db.watch", {"prefix": None})
        events = [event async for event in iterator]
        assert events == [
            {"op": "set", "key": "a", "value": 1},
            {"op": "delete", "key": "a", "value": None},
        ]

    @pytest.mark.asyncio
    async def test_watch_with_prefix(self):
        async def gen():
            yield {"op": "set", "key": "user:1", "value": {"ok": True}}

        proxy = MagicMock(spec=CapabilityProxy)
        proxy.stream = MagicMock(return_value=gen())
        client = DBClient(proxy)

        iterator = client.watch(prefix="user:")

        proxy.stream.assert_called_once_with("db.watch", {"prefix": "user:"})
        events = [event async for event in iterator]
        assert events == [{"op": "set", "key": "user:1", "value": {"ok": True}}]
