# Design: LSP Integration Tests

## LSP Echo Server Fixture

Create a simple stdio-based LSP server for testing:

```python
# tests/integration/fixtures/echo_lsp_server.py
"""
Simple LSP server that echoes back requests.
Used for testing the LSP client.
"""

import json
import sys

def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        request = json.loads(line)

        msg_id = request.get("id")
        method = request.get("method")

        # Handle initialize
        if method == "initialize":
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "capabilities": {"textDocumentSync": 1}
                }
            }))
            sys.stdout.flush()

        # Handle initialized notification (no response)
        elif method == "initialized":
            continue

        # Handle shutdown
        elif method == "shutdown":
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": None
            }))
            sys.stdout.flush()

        # Echo any textDocument/didOpen
        elif method == "textDocument/didOpen":
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": None
            }))
            sys.stdout.flush()

        # Echo any request
        elif msg_id is not None:
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {"echo": True}
            }))
            sys.stdout.flush()
```

## LSP Client Integration Tests

```python
# tests/integration/test_lsp_integration.py
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
        workspace_uri="file:///tmp"
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
        workspace_uri="file:///tmp"
    )

    try:
        assert client.connected

        # Send a custom request
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
        workspace_uri="file:///tmp"
    )

    try:
        assert client.connected

        # Send a notification (should not raise)
        await client.send_notification("custom/notify", {"data": "test"})

    finally:
        await client.shutdown()
```

## Test Fixtures Location

```
tests/
├── integration/
│   ├── fixtures/
│   │   ├── echo_lsp_server.py  # New
│   │   ├── echo_mcp_server.py   # Existing
│   │   └── echo_acp_server.py   # Existing
│   ├── test_lsp_integration.py  # New
│   ├── test_mcp_integration.py  # Existing
│   └── test_acp_integration.py  # Existing
```

## Running Tests

```bash
# Run all integration tests
uv run pytest tests/integration/ -v

# Run LSP integration only
uv run pytest tests/integration/test_lsp_integration.py -v
```
