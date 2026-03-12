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
    async def test_get_returns_none_for_non_dict_value(self):
        """get() should return None when value is not a dict."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"value": "not a dict"})

        client = DBClient(proxy)
        result = await client.get("my_key")

        assert result is None

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
    async def test_list_with_none_prefix(self):
        """list() should handle None prefix."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"keys": []})

        client = DBClient(proxy)
        result = await client.list(prefix=None)

        proxy.call.assert_called_once_with("db.list", {"prefix": None})
        assert result == []
