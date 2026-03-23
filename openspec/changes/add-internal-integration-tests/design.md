# Design: Internal Integration Tests

## MCP Integration Test Design

### Mock MCP Server

Create a simple stdio-based MCP server for testing:

```python
# tests/integration/fixtures/echo_mcp_server.py
"""
Simple MCP server that echoes back tool calls.
Used for testing the MCP client.
"""

import json
import sys

async def main():
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        request = json.loads(line)

        # Handle initialize
        if request.get("method") == "initialize":
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"protocolVersion": "2024-11-05", "capabilities": {}}
            }))
            sys.stdout.flush()

        # Handle tool call
        elif request.get("method") == "tools/call":
            params = request.get("params", {})
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"content": [{"type": "text", "text": f"{tool_name}({arguments})"}]}
            }))
            sys.stdout.flush()

        # Handle list tools
        elif request.get("method") == "tools/list":
            print(json.dumps({
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "result": {"tools": [{"name": "echo", "description": "Echo back input"}]}
            }))
            sys.stdout.flush()
```

### MCP Client Integration Test

```python
# tests/integration/test_mcp_integration.py
import pytest
import anyio
from astrbot._internal.protocols.mcp.client import McpClient

@pytest.mark.anyio
async def test_mcp_client_connect_to_echo_server():
    """Test MCP client can connect to a real MCP server."""
    client = McpClient()

    # Start the echo server
    server_process = await anyio.open_process(
        ["python", "tests/integration/fixtures/echo_mcp_server.py"],
        stdin=-1, stdout=-1, stderr=-1
    )

    # Connect client
    await client.connect_to_server(
        command=["python", "tests/integration/fixtures/echo_mcp_server.py"],
        workspace_uri="file:///tmp"
    )

    # List tools
    tools = await client.list_tools()
    assert len(tools) > 0

    # Call tool
    result = await client.call_tool("echo", {"message": "test"})
    assert "echo" in result

    await client.shutdown()
```

## ACP Integration Test Design

Similar pattern - create a mock ACP server and test the ACP client connects and communicates properly.

## Test Fixtures Location

```
tests/
├── integration/
│   ├── fixtures/
│   │   ├── echo_mcp_server.py
│   │   └── echo_acp_server.py
│   ├── test_mcp_integration.py
│   └── test_acp_integration.py
```

## Running Tests

```bash
# Run all integration tests
uv run pytest tests/integration/ -v

# Run MCP integration only
uv run pytest tests/integration/test_mcp_integration.py -v
```
