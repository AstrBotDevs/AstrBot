"""
LSP Integration Tests.

Tests the LSP client against a real LSP server fixture.
"""

from __future__ import annotations

import sys
from pathlib import Path

import anyio
import pytest
from anyio.lowlevel import checkpoint

from astrbot._internal.protocols.lsp.client import AstrbotLspClient

TEST_DIR = Path(__file__).resolve().parent
SERVER_PATH = TEST_DIR / "fixtures" / "echo_lsp_server.py"
HANGING_SERVER_PATH = TEST_DIR / "fixtures" / "hanging_lsp_server.py"


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

    await client.connect_to_server(
        command=[sys.executable, str(SERVER_PATH)],
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

    await client.connect_to_server(
        command=[sys.executable, str(SERVER_PATH)],
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

    await client.connect_to_server(
        command=[sys.executable, str(SERVER_PATH)],
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


@pytest.mark.anyio
async def test_lsp_client_connect_does_not_corrupt_anyio_cancel_scope():
    """Test connect/shutdown can run inside fail_after scopes without scope corruption."""
    client = AstrbotLspClient()

    with anyio.fail_after(5):
        await client.connect_to_server(
            command=[sys.executable, str(SERVER_PATH)],
            workspace_uri="file:///tmp",
        )

    try:
        assert client.connected
    finally:
        with anyio.fail_after(5):
            await client.shutdown()


@pytest.mark.anyio
async def test_lsp_client_connect_timeout_does_not_corrupt_anyio_cancel_scope():
    """Test timeout-driven cancellation leaves later fail_after scopes usable."""
    client = AstrbotLspClient()

    with pytest.raises(TimeoutError):
        with anyio.fail_after(0.1):
            await client.connect_to_server(
                command=[sys.executable, str(HANGING_SERVER_PATH)],
                workspace_uri="file:///tmp",
            )

    with anyio.fail_after(5):
        await client.shutdown()

    with anyio.fail_after(1):
        await checkpoint()
