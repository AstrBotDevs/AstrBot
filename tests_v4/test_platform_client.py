"""
Tests for clients/platform.py - PlatformClient implementation.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.clients.platform import PlatformClient
from astrbot_sdk.clients._proxy import CapabilityProxy


class TestPlatformClientInit:
    """Tests for PlatformClient initialization."""

    def test_init_with_proxy(self):
        """PlatformClient should store proxy reference."""
        proxy = MagicMock(spec=CapabilityProxy)
        client = PlatformClient(proxy)
        assert client._proxy is proxy


class TestPlatformClientSend:
    """Tests for PlatformClient.send() method."""

    @pytest.mark.asyncio
    async def test_send_returns_response(self):
        """send() should return response dict."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"message_id": "msg_123", "sent": True})

        client = PlatformClient(proxy)
        result = await client.send("session-1", "Hello")

        proxy.call.assert_called_once_with(
            "platform.send",
            {"session": "session-1", "text": "Hello"},
        )
        assert result["message_id"] == "msg_123"

    @pytest.mark.asyncio
    async def test_send_with_empty_text(self):
        """send() should work with empty text."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = PlatformClient(proxy)
        await client.send("session-1", "")

        call_args = proxy.call.call_args[0][1]
        assert call_args["text"] == ""

    @pytest.mark.asyncio
    async def test_send_with_special_characters(self):
        """send() should handle special characters in text."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = PlatformClient(proxy)
        await client.send("session-1", "Hello\nWorld\t! @#$%")

        call_args = proxy.call.call_args[0][1]
        assert call_args["text"] == "Hello\nWorld\t! @#$%"


class TestPlatformClientSendImage:
    """Tests for PlatformClient.send_image() method."""

    @pytest.mark.asyncio
    async def test_send_image_returns_response(self):
        """send_image() should return response dict."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"image_id": "img_456"})

        client = PlatformClient(proxy)
        result = await client.send_image("session-1", "https://example.com/image.png")

        proxy.call.assert_called_once_with(
            "platform.send_image",
            {"session": "session-1", "image_url": "https://example.com/image.png"},
        )
        assert result["image_id"] == "img_456"

    @pytest.mark.asyncio
    async def test_send_image_with_file_url(self):
        """send_image() should work with file:// URL."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = PlatformClient(proxy)
        await client.send_image("session-1", "file:///path/to/image.jpg")

        call_args = proxy.call.call_args[0][1]
        assert call_args["image_url"] == "file:///path/to/image.jpg"

    @pytest.mark.asyncio
    async def test_send_image_with_base64_url(self):
        """send_image() should work with data URL."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = PlatformClient(proxy)
        await client.send_image("session-1", "data:image/png;base64,abc123")

        call_args = proxy.call.call_args[0][1]
        assert call_args["image_url"] == "data:image/png;base64,abc123"


class TestPlatformClientGetMembers:
    """Tests for PlatformClient.get_members() method."""

    @pytest.mark.asyncio
    async def test_get_members_returns_list(self):
        """get_members() should return list of members."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(
            return_value={
                "members": [
                    {"id": "user1", "name": "Alice"},
                    {"id": "user2", "name": "Bob"},
                ]
            }
        )

        client = PlatformClient(proxy)
        result = await client.get_members("group-1")

        proxy.call.assert_called_once_with(
            "platform.get_members",
            {"session": "group-1"},
        )
        assert len(result) == 2
        assert result[0]["name"] == "Alice"

    @pytest.mark.asyncio
    async def test_get_members_returns_empty_list(self):
        """get_members() should return empty list when no members."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={})

        client = PlatformClient(proxy)
        result = await client.get_members("empty-group")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_members_returns_empty_list_for_malformed_payload(self):
        """get_members() should ignore malformed non-list payloads."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"members": "bad"})

        client = PlatformClient(proxy)
        result = await client.get_members("group-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_members_with_private_session(self):
        """get_members() should work with private session."""
        proxy = AsyncMock(spec=CapabilityProxy)
        proxy.call = AsyncMock(return_value={"members": [{"id": "single_user"}]})

        client = PlatformClient(proxy)
        await client.get_members("private-123")

        call_args = proxy.call.call_args[0][1]
        assert call_args["session"] == "private-123"
