"""
Tests for clients/_proxy.py - CapabilityProxy implementation.
"""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot_sdk.clients._proxy import CapabilityProxy
from astrbot_sdk.errors import AstrBotError


@dataclass
class MockCapabilityDescriptor:
    """Mock capability descriptor for testing."""

    name: str
    supports_stream: bool | None = None


class MockPeer:
    """Mock peer for testing CapabilityProxy."""

    def __init__(self):
        self.remote_capability_map: dict[str, MockCapabilityDescriptor] = {}
        self.invoke = AsyncMock(return_value={"result": "ok"})
        self.invoke_stream = AsyncMock()


class TestCapabilityProxyInit:
    """Tests for CapabilityProxy initialization."""

    def test_init_with_peer(self):
        """CapabilityProxy should store peer reference."""
        peer = MagicMock()
        proxy = CapabilityProxy(peer)
        assert proxy._peer is peer


class TestCapabilityProxyGetDescriptor:
    """Tests for CapabilityProxy._get_descriptor() method."""

    def test_get_descriptor_returns_descriptor(self):
        """_get_descriptor should return descriptor if found."""
        peer = MagicMock()
        peer.remote_capability_map = {"db.get": MockCapabilityDescriptor(name="db.get")}
        proxy = CapabilityProxy(peer)

        result = proxy._get_descriptor("db.get")
        assert result is not None
        assert result.name == "db.get"

    def test_get_descriptor_returns_none_for_missing(self):
        """_get_descriptor should return None if not found."""
        peer = MagicMock()
        peer.remote_capability_map = {}
        proxy = CapabilityProxy(peer)

        result = proxy._get_descriptor("nonexistent")
        assert result is None

    def test_get_descriptor_with_empty_map(self):
        """_get_descriptor should work with empty capability map."""
        peer = MagicMock()
        peer.remote_capability_map = {}
        proxy = CapabilityProxy(peer)

        result = proxy._get_descriptor("anything")
        assert result is None


class TestCapabilityProxyEnsureAvailable:
    """Tests for CapabilityProxy._ensure_available() method."""

    def test_ensure_available_passes_when_descriptor_exists(self):
        """_ensure_available should pass when descriptor exists."""
        peer = MagicMock()
        peer.remote_capability_map = {
            "test.cap": MockCapabilityDescriptor(name="test.cap")
        }
        proxy = CapabilityProxy(peer)

        # Should not raise
        proxy._ensure_available("test.cap", stream=False)

    def test_ensure_available_raises_capability_not_found(self):
        """_ensure_available should raise capability_not_found when missing."""
        peer = MagicMock()
        peer.remote_capability_map = {
            "other.cap": MockCapabilityDescriptor(name="other.cap")
        }
        proxy = CapabilityProxy(peer)

        with pytest.raises(AstrBotError) as exc_info:
            proxy._ensure_available("missing.cap", stream=False)

        assert exc_info.value.code == "capability_not_found"
        assert "missing.cap" in exc_info.value.message

    def test_ensure_available_passes_when_map_empty(self):
        """_ensure_available should pass (return None) when capability map is empty."""
        peer = MagicMock()
        peer.remote_capability_map = {}
        proxy = CapabilityProxy(peer)

        # Should not raise when map is empty
        proxy._ensure_available("any.cap", stream=False)

    def test_ensure_available_raises_for_stream_not_supported(self):
        """_ensure_available should raise when stream requested but not supported."""
        peer = MagicMock()
        peer.remote_capability_map = {
            "test.cap": MockCapabilityDescriptor(name="test.cap", supports_stream=False)
        }
        proxy = CapabilityProxy(peer)

        with pytest.raises(AstrBotError) as exc_info:
            proxy._ensure_available("test.cap", stream=True)

        assert exc_info.value.code == "invalid_input"
        assert "不支持 stream=true" in exc_info.value.message

    def test_ensure_available_passes_for_stream_supported(self):
        """_ensure_available should pass when stream is supported."""
        peer = MagicMock()
        peer.remote_capability_map = {
            "test.cap": MockCapabilityDescriptor(name="test.cap", supports_stream=True)
        }
        proxy = CapabilityProxy(peer)

        # Should not raise
        proxy._ensure_available("test.cap", stream=True)

    def test_ensure_available_handles_none_supports_stream(self):
        """_ensure_available should treat None supports_stream as not supporting stream."""
        peer = MagicMock()
        peer.remote_capability_map = {
            "test.cap": MockCapabilityDescriptor(name="test.cap", supports_stream=None)
        }
        proxy = CapabilityProxy(peer)

        # Should not raise for non-stream
        proxy._ensure_available("test.cap", stream=False)

        # Should raise for stream=True when supports_stream is None
        with pytest.raises(AstrBotError) as exc_info:
            proxy._ensure_available("test.cap", stream=True)
        assert exc_info.value.code == "invalid_input"


class TestCapabilityProxyCall:
    """Tests for CapabilityProxy.call() method."""

    @pytest.mark.asyncio
    async def test_call_invokes_peer(self):
        """call() should invoke peer with correct parameters."""
        peer = MockPeer()
        peer.remote_capability_map = {"db.get": MockCapabilityDescriptor(name="db.get")}
        proxy = CapabilityProxy(peer)

        result = await proxy.call("db.get", {"key": "test"})

        peer.invoke.assert_called_once_with("db.get", {"key": "test"}, stream=False)
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_call_without_capability_map(self):
        """call() should work when capability map is empty."""
        peer = MockPeer()
        peer.remote_capability_map = {}
        proxy = CapabilityProxy(peer)

        result = await proxy.call("any.cap", {})

        peer.invoke.assert_called_once_with("any.cap", {}, stream=False)
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_call_raises_for_missing_capability(self):
        """call() should raise for missing capability when map is not empty."""
        peer = MockPeer()
        peer.remote_capability_map = {
            "other.cap": MockCapabilityDescriptor(name="other.cap")
        }
        proxy = CapabilityProxy(peer)

        with pytest.raises(AstrBotError) as exc_info:
            await proxy.call("missing.cap", {})

        assert exc_info.value.code == "capability_not_found"


class MockAsyncIterator:
    """Mock async iterator for testing stream responses."""

    def __init__(self, items):
        self._items = list(items)
        self._index = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._index >= len(self._items):
            raise StopAsyncIteration
        item = self._items[self._index]
        self._index += 1
        return item


@dataclass
class MockEvent:
    """Mock stream event for testing."""

    phase: str
    data: dict


class TestCapabilityProxyStream:
    """Tests for CapabilityProxy.stream() method."""

    @pytest.mark.asyncio
    async def test_stream_yields_delta_data(self):
        """stream() should yield data from delta events."""
        peer = MockPeer()

        # invoke_stream is an async method that returns AsyncIterator
        events = [
            MockEvent(phase="delta", data={"text": "chunk1"}),
            MockEvent(phase="delta", data={"text": "chunk2"}),
            MockEvent(phase="complete", data={"done": True}),
        ]
        peer.invoke_stream = AsyncMock(return_value=MockAsyncIterator(events))
        peer.remote_capability_map = {
            "llm.stream": MockCapabilityDescriptor(
                name="llm.stream", supports_stream=True
            )
        }
        proxy = CapabilityProxy(peer)

        chunks = []
        async for data in proxy.stream("llm.stream", {"prompt": "hi"}):
            chunks.append(data)

        assert len(chunks) == 2
        assert chunks[0] == {"text": "chunk1"}
        assert chunks[1] == {"text": "chunk2"}

    @pytest.mark.asyncio
    async def test_stream_filters_non_delta_events(self):
        """stream() should only yield delta events."""
        peer = MockPeer()

        events = [
            MockEvent(phase="start", data={"session": "abc"}),
            MockEvent(phase="delta", data={"text": "hello"}),
            MockEvent(phase="complete", data={}),
            MockEvent(phase="delta", data={"text": "world"}),
        ]
        peer.invoke_stream = AsyncMock(return_value=MockAsyncIterator(events))
        peer.remote_capability_map = {
            "test.stream": MockCapabilityDescriptor(
                name="test.stream", supports_stream=True
            )
        }
        proxy = CapabilityProxy(peer)

        chunks = []
        async for data in proxy.stream("test.stream", {}):
            chunks.append(data)

        # Only delta events should be yielded
        assert len(chunks) == 2
        assert chunks[0] == {"text": "hello"}
        assert chunks[1] == {"text": "world"}

    @pytest.mark.asyncio
    async def test_stream_raises_for_non_streaming_capability(self):
        """stream() should raise when capability doesn't support streaming."""
        peer = MockPeer()
        peer.remote_capability_map = {
            "db.get": MockCapabilityDescriptor(name="db.get", supports_stream=False)
        }
        proxy = CapabilityProxy(peer)

        with pytest.raises(AstrBotError) as exc_info:
            async for _ in proxy.stream("db.get", {}):
                pass

        assert exc_info.value.code == "invalid_input"

    @pytest.mark.asyncio
    async def test_stream_works_without_capability_map(self):
        """stream() should work when capability map is empty."""
        peer = MockPeer()

        events = [MockEvent(phase="delta", data={"text": "ok"})]
        peer.invoke_stream = AsyncMock(return_value=MockAsyncIterator(events))
        peer.remote_capability_map = {}
        proxy = CapabilityProxy(peer)

        chunks = []
        async for data in proxy.stream("any.stream", {}):
            chunks.append(data)

        assert chunks == [{"text": "ok"}]
