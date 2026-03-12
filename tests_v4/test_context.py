"""
Unit tests for Context module.
"""

from __future__ import annotations

import asyncio

import pytest

from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.protocol.messages import PeerInfo
from astrbot_sdk.runtime.peer import Peer


class TestCancelToken:
    """Tests for CancelToken."""

    def test_initial_state(self):
        """CancelToken should start uncancelled."""
        token = CancelToken()
        assert not token.cancelled

    def test_cancel_sets_state(self):
        """cancel() should set cancelled state."""
        token = CancelToken()
        token.cancel()
        assert token.cancelled

    def test_raise_if_cancelled_raises_when_cancelled(self):
        """raise_if_cancelled() should raise CancelledError when cancelled."""
        token = CancelToken()
        token.cancel()

        with pytest.raises(asyncio.CancelledError):
            token.raise_if_cancelled()

    def test_raise_if_cancelled_no_raise_when_not_cancelled(self):
        """raise_if_cancelled() should not raise when not cancelled."""
        token = CancelToken()
        token.raise_if_cancelled()  # Should not raise

    @pytest.mark.asyncio
    async def test_wait_blocks_until_cancelled(self):
        """wait() should block until cancel() is called."""
        token = CancelToken()

        async def cancel_after_delay():
            await asyncio.sleep(0.01)
            token.cancel()

        task = asyncio.create_task(cancel_after_delay())
        await token.wait()
        assert token.cancelled
        await task


class TestContext:
    """Tests for Context."""

    def test_context_has_platform_facade(self, transport_pair):
        """Context should have platform facade."""
        left, _ = transport_pair

        peer = Peer(
            transport=left,
            peer_info=PeerInfo(name="test", role="plugin", version="v4"),
        )
        ctx = Context(peer=peer, plugin_id="test_plugin")

        assert hasattr(ctx, "platform")
        assert hasattr(ctx.platform, "send")

    def test_context_has_llm_facade(self, transport_pair):
        """Context should have LLM facade."""
        left, _ = transport_pair

        peer = Peer(
            transport=left,
            peer_info=PeerInfo(name="test", role="plugin", version="v4"),
        )
        ctx = Context(peer=peer, plugin_id="test_plugin")

        assert hasattr(ctx, "llm")
        assert hasattr(ctx.llm, "chat")
        assert hasattr(ctx.llm, "stream_chat")

    def test_context_has_db_facade(self, transport_pair):
        """Context should have database facade."""
        left, _ = transport_pair

        peer = Peer(
            transport=left,
            peer_info=PeerInfo(name="test", role="plugin", version="v4"),
        )
        ctx = Context(peer=peer, plugin_id="test_plugin")

        assert hasattr(ctx, "db")
        assert hasattr(ctx.db, "get")
        assert hasattr(ctx.db, "set")
        assert hasattr(ctx.db, "delete")

    def test_context_has_plugin_id(self, transport_pair):
        """Context should store plugin_id."""
        left, _ = transport_pair

        peer = Peer(
            transport=left,
            peer_info=PeerInfo(name="test", role="plugin", version="v4"),
        )
        ctx = Context(peer=peer, plugin_id="my_plugin")

        assert ctx.plugin_id == "my_plugin"

    def test_context_keeps_peer_reference(self, transport_pair):
        """Context should retain the underlying peer for advanced diagnostics."""
        left, _ = transport_pair

        peer = Peer(
            transport=left,
            peer_info=PeerInfo(name="test", role="plugin", version="v4"),
        )
        ctx = Context(peer=peer, plugin_id="my_plugin")

        assert ctx.peer is peer

    def test_context_has_logger(self, transport_pair):
        """Context should have a logger bound with plugin_id."""
        left, _ = transport_pair

        peer = Peer(
            transport=left,
            peer_info=PeerInfo(name="test", role="plugin", version="v4"),
        )
        ctx = Context(peer=peer, plugin_id="test_plugin")

        assert hasattr(ctx, "logger")
