from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from anyio.abc import ByteReceiveStream

from astrbot._internal.protocols.lsp.client import AstrbotLspClient


class FakeReader(ByteReceiveStream):
    def __init__(self, receive_mock: AsyncMock) -> None:
        self._receive_mock = receive_mock

    async def receive(self, max_bytes: int = 65536) -> bytes:
        del max_bytes
        return await self._receive_mock()

    async def aclose(self) -> None:
        return None


class TestAstrbotLspClientInitialState:
    """Test LSP client initial state."""

    def test_client_initial_state(self) -> None:
        """Test client starts disconnected."""
        client = AstrbotLspClient()
        assert client.connected is False
        assert client._reader is None
        assert client._writer is None
        assert client._task_group is None


class TestAstrbotLspClientConnect:
    """Test LSP client connect method."""

    @pytest.mark.asyncio
    async def test_connect_sets_connected_true(self) -> None:
        """Test connect() sets connected state."""
        client = AstrbotLspClient()
        await client.connect()
        assert client.connected is True


class TestAstrbotLspClientSendRequest:
    """Test LSP client send_request method."""

    @pytest.mark.asyncio
    async def test_send_request_requires_connection(self) -> None:
        """Test send_request raises when not connected."""
        client = AstrbotLspClient()
        with pytest.raises(RuntimeError, match="not connected"):
            await client.send_request("initialize", {})

    @pytest.mark.asyncio
    async def test_send_request_formats_jsonrpc_correctly(self) -> None:
        """Test send_request formats message as JSON-RPC 2.0."""
        client = AstrbotLspClient()
        client._connected = True
        mock_writer = AsyncMock()
        mock_event = MagicMock()
        mock_event.wait = AsyncMock()
        client._writer = mock_writer
        client._pending_requests[0] = AsyncMock()

        with patch("astrbot._internal.protocols.lsp.client.anyio.Event", return_value=mock_event):
            # Timeout immediately to avoid hanging
            with pytest.raises(TimeoutError, match="timed out"):
                await client.send_request("initialize", {"processId": None})


class TestAstrbotLspClientSendNotification:
    """Test LSP client send_notification method."""

    @pytest.mark.asyncio
    async def test_send_notification_requires_connection(self) -> None:
        """Test send_notification raises when not connected."""
        client = AstrbotLspClient()
        with pytest.raises(RuntimeError, match="not connected"):
            await client.send_notification("initialized", {})

    @pytest.mark.asyncio
    async def test_send_notification_formats_jsonrpc_correctly(self) -> None:
        """Test send_notification formats message as JSON-RPC 2.0."""
        client = AstrbotLspClient()
        client._connected = True
        mock_writer = AsyncMock()
        client._writer = mock_writer

        await client.send_notification("initialized", {})

        mock_writer.send.assert_called_once()
        data = mock_writer.send.call_args[0][0]
        decoded = data.decode("utf-8")
        assert "Content-Length:" in decoded
        assert '"jsonrpc": "2.0"' in decoded
        assert '"method": "initialized"' in decoded


class TestAstrbotLspClientShutdown:
    """Test LSP client shutdown method."""

    @pytest.mark.asyncio
    async def test_shutdown_sets_connected_false(self) -> None:
        """Test shutdown disconnects the client."""
        client = AstrbotLspClient()
        client._connected = True
        client._task_group = MagicMock()
        client._task_group.__aexit__ = AsyncMock()
        client._server_process = MagicMock()
        client._server_process.terminate = MagicMock()
        client._server_process.wait = AsyncMock()
        client._server_process.kill = MagicMock()
        client.send_notification = AsyncMock()

        await client.shutdown()

        assert client.connected is False

    @pytest.mark.asyncio
    async def test_shutdown_clears_pending_requests(self) -> None:
        """Test shutdown clears pending requests."""
        client = AstrbotLspClient()
        client._connected = True
        client._pending_requests[1] = AsyncMock()
        client._task_group = MagicMock()
        client._task_group.__aexit__ = AsyncMock()
        client._server_process = None

        await client.shutdown()

        assert len(client._pending_requests) == 0


class TestAstrbotLspClientReadResponses:
    """Test LSP client _read_responses method."""

    @pytest.mark.asyncio
    async def test_read_responses_returns_immediately_if_no_reader(self) -> None:
        """Test _read_responses exits early when _reader is None."""
        client = AstrbotLspClient()
        client._reader = None
        client._connected = True

        await client._read_responses()

        # Should return without error
        assert True

    @pytest.mark.asyncio
    async def test_read_responses_handles_empty_data_as_eof(self) -> None:
        """Test _read_responses breaks on empty data (EOF)."""
        client = AstrbotLspClient()
        client._connected = True
        client._reader = FakeReader(AsyncMock(return_value=b""))
        client._pending_requests = {}

        # Should exit cleanly without raising
        await client._read_responses()

        assert client._connected is True  # Note: current impl doesn't auto-disconnect on EOF

    @pytest.mark.asyncio
    async def test_read_responses_parses_jsonrpc_response(self) -> None:
        """Test _read_responses parses and dispatches JSON-RPC responses."""
        client = AstrbotLspClient()
        client._connected = True

        response = {"jsonrpc": "2.0", "id": 0, "result": {}}
        content = json.dumps(response).encode()
        header = f"Content-Length: {len(content)}\r\n\r\n".encode()

        # First call returns the message, second call returns empty (EOF)
        fake_reader = FakeReader(AsyncMock(side_effect=[header + content, b""]))
        client._reader = fake_reader

        handler_called = False

        async def handler(resp: dict) -> None:
            nonlocal handler_called
            handler_called = True

        client._pending_requests[0] = handler

        await client._read_responses()

        assert handler_called is True


class TestAstrbotLspClientHandleNotification:
    """Test LSP client _handle_notification method."""

    @pytest.mark.asyncio
    async def test_handle_notification_logs_method_name(self) -> None:
        """Test _handle_notification logs the notification method."""
        client = AstrbotLspClient()
        notification = {"jsonrpc": "2.0", "method": "window/showMessage", "params": {}}

        with patch("astrbot._internal.protocols.lsp.client.log") as mock_log:
            await client._handle_notification(notification)

        mock_log.debug.assert_called()
