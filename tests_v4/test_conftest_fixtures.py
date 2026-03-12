"""
Pytest-based tests for transport and peer communication.

These tests demonstrate the pytest fixtures defined in conftest.py.
"""

from __future__ import annotations

import asyncio

import pytest

from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.protocol.descriptors import CapabilityDescriptor
from astrbot_sdk.protocol.messages import (
    EventMessage,
    PeerInfo,
    ResultMessage,
)
from astrbot_sdk.runtime.capability_router import CapabilityRouter
from astrbot_sdk.runtime.peer import Peer


class TestTransportPair:
    """Tests for MemoryTransport fixture."""

    async def test_transport_pair_is_connected(self, transport_pair):
        """Transport pair should be bidirectionally connected."""
        left, right = transport_pair
        assert left.partner is right
        assert right.partner is left

    async def test_transport_can_send_message(self, transport_pair):
        """Messages sent through transport should be received by partner."""
        left, right = transport_pair
        received = []

        async def handler(payload):
            received.append(payload)

        right.set_message_handler(handler)
        await left.start()
        await right.start()

        await left.send("test message")

        assert len(received) == 1
        assert received[0] == "test message"


class TestPeerConnection:
    """Tests for peer-to-peer communication using fixtures."""

    async def test_plugin_can_initialize(self, core_peer, plugin_peer):
        """Plugin should be able to initialize with core."""
        await plugin_peer.initialize([])

        assert plugin_peer.remote_peer is not None
        assert plugin_peer.remote_peer.name == "core"

    async def test_plugin_can_invoke_capability(self, core_peer, plugin_peer):
        """Plugin should be able to invoke llm.chat capability."""
        await plugin_peer.initialize([])

        result = await plugin_peer.invoke("llm.chat", {"prompt": "hello"})
        assert result["text"] == "Echo: hello"

    async def test_plugin_can_stream_capability(self, core_peer, plugin_peer):
        """Plugin should be able to stream llm.stream_chat capability."""
        await plugin_peer.initialize([])

        stream = await plugin_peer.invoke_stream("llm.stream_chat", {"prompt": "hi"})
        chunks = [event.data["text"] async for event in stream]
        assert "".join(chunks) == "Echo: hi"


class TestProtocolErrors:
    """Tests for protocol error handling."""

    async def test_stream_false_receiving_event_is_error(self, transport_pair):
        """stream=false receiving event should raise protocol error."""
        left, right = transport_pair

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await left.start()
        await plugin.start()

        task = asyncio.create_task(
            plugin.invoke("llm.chat", {"prompt": "bad"}, request_id="req-1")
        )
        await asyncio.sleep(0)
        await left.send(EventMessage(id="req-1", phase="started").model_dump_json())

        with pytest.raises(AstrBotError) as exc_info:
            await task
        assert exc_info.value.code == "protocol_error"

        await plugin.stop()
        await left.stop()

    async def test_stream_true_receiving_result_is_error(self, transport_pair):
        """stream=true receiving result should raise protocol error."""

        left, right = transport_pair

        plugin = Peer(
            transport=right,
            peer_info=PeerInfo(name="plugin", role="plugin", version="v4"),
        )

        await left.start()
        await plugin.start()

        stream = await plugin.invoke_stream(
            "llm.stream_chat", {"prompt": "bad"}, request_id="stream-1"
        )
        await left.send(
            ResultMessage(id="stream-1", success=True, output={}).model_dump_json()
        )

        with pytest.raises(AstrBotError) as exc_info:
            async for _ in stream:
                pass
        assert exc_info.value.code == "protocol_error"

        await plugin.stop()
        await left.stop()


class TestCapabilityRouter:
    """Tests for CapabilityRouter."""

    def test_capability_name_validation(self):
        """Capability names must follow namespace.method format."""
        router = CapabilityRouter()

        invalid_names = ["llm", "llm.chat.extra", "LLM.chat", "llm.Chat"]
        for name in invalid_names:
            with pytest.raises(ValueError) as exc_info:
                router.register(CapabilityDescriptor(name=name, description="invalid"))
            assert name in str(exc_info.value)

    def test_reserved_namespaces_rejected_for_exposed(self):
        """Reserved namespaces should be rejected for exposed registrations."""
        router = CapabilityRouter()

        reserved_names = ["handler.demo", "system.health", "internal.trace"]
        for name in reserved_names:
            with pytest.raises(ValueError) as exc_info:
                router.register(CapabilityDescriptor(name=name, description="reserved"))
            assert name in str(exc_info.value)

    def test_reserved_namespaces_allowed_for_hidden(self):
        """Reserved namespaces should be allowed for hidden registrations."""
        router = CapabilityRouter()
        router.register(
            CapabilityDescriptor(name="system.health", description="internal only"),
            exposed=False,
        )

        descriptors = router.descriptors()
        assert "system.health" not in [d.name for d in descriptors]
