"""
LSP Integration Tests.

Tests the LSP client against a real LSP server fixture.
"""

from __future__ import annotations

import os
import pytest

from astrbot._internal.protocols.lsp.client import AstrbotLspClient


@pytest.mark.anyio
async def test_lsp_client_initialization():
    """Test LSP client can be initialized."""
    client = AstrbotLspClient()
    assert client is not None
    assert not client.connected


@pytest.mark.anyio
async def test_lsp_client_connect_to_echo_server():
    """Test LSP client can connect to echo LSP server."""
    client = AstrbotLspClient()

    test_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(test_dir, "fixtures", "echo_lsp_server.py")

    await client.connect_to_server(
        command=["python", server_path],
        workspace_uri="file:///tmp",
    )

    try:
        assert client.connected
    finally:
        await client.shutdown()


@pytest.mark.anyio
async def test_lsp_client_send_request():
    """Test LSP client can send a request and receive response."""
    client = AstrbotLspClient()

    test_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(test_dir, "fixtures", "echo_lsp_server.py")

    await client.connect_to_server(
        command=["python", server_path],
        workspace_uri="file:///tmp",
    )

    try:
        assert client.connected

        # Send a custom request - echo server will echo it back
        result = await client.send_request("custom/echo", {"message": "test"})
        assert result is not None

    finally:
        await client.shutdown()


@pytest.mark.anyio
async def test_lsp_client_send_notification():
    """Test LSP client can send a notification (no response)."""
    client = AstrbotLspClient()

    test_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(test_dir, "fixtures", "echo_lsp_server.py")

    await client.connect_to_server(
        command=["python", server_path],
        workspace_uri="file:///tmp",
    )

    try:
        assert client.connected

        # Send a notification (should not raise)
        await client.send_notification("custom/notify", {"data": "test"})

    finally:
        await client.shutdown()


@pytest.mark.anyio
async def test_lsp_client_send_request_not_connected():
    """Test LSP client raises RuntimeError when sending request while not connected."""
    client = AstrbotLspClient()
    with pytest.raises(RuntimeError, match="LSP client not connected"):
        await client.send_request("test", {})


@pytest.mark.anyio
async def test_lsp_client_send_notification_not_connected():
    """Test LSP client raises RuntimeError when sending notification while not connected."""
    client = AstrbotLspClient()
    with pytest.raises(RuntimeError, match="LSP client not connected"):
        await client.send_notification("test", {})