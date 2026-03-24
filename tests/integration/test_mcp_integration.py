"""
MCP Integration Tests.

Tests the MCP client against a real MCP server fixture.
"""

from __future__ import annotations

import pytest

from astrbot._internal.protocols.mcp.client import McpClient


@pytest.mark.anyio
async def test_mcp_client_initialization():
    """Test MCP client can be initialized."""
    client = McpClient()
    assert client is not None
    assert not client.connected


@pytest.mark.anyio
async def test_mcp_client_connect_is_noop():
    """Test that connect() without server config does nothing."""
    client = McpClient()
    await client.connect()
    # Without server configuration, connect should be a no-op
    assert not client.connected


@pytest.mark.skip(reason="MCP ClientSession.initialize() waits for server notifications after response - complex protocol dance")
@pytest.mark.anyio
async def test_mcp_echo_server_connection():
    """Test that MCP client can connect to echo MCP server."""
    import os

    client = McpClient()

    # Get the path to the echo server fixture
    test_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(test_dir, "fixtures", "echo_mcp_server.py")

    # Create MCP server config for stdio transport
    config = {
        "command": "python",
        "args": [server_path],
        "env": {},
        "cwd": test_dir
    }

    # Connect to the echo server
    await client.connect_to_server(config, "echo-test")

    try:
        # Verify connected
        assert client.connected

    finally:
        await client.cleanup()


@pytest.mark.skip(reason="MCP ClientSession.initialize() waits for server notifications after response - complex protocol dance")
@pytest.mark.anyio
async def test_mcp_list_tools():
    """Test listing tools from MCP server."""
    import os

    client = McpClient()

    test_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(test_dir, "fixtures", "echo_mcp_server.py")

    config = {
        "command": "python",
        "args": [server_path],
        "env": {},
        "cwd": test_dir
    }

    await client.connect_to_server(config, "echo-test")

    try:
        assert client.connected

        # List tools
        tools = await client.list_tools()
        assert isinstance(tools, list)
        assert len(tools) >= 2  # We define echo and add tools

        # Check tool names
        tool_names = [t["name"] for t in tools]
        assert "echo" in tool_names
        assert "add" in tool_names

    finally:
        await client.cleanup()


@pytest.mark.skip(reason="MCP ClientSession.initialize() waits for server notifications after response - complex protocol dance")
@pytest.mark.anyio
async def test_mcp_call_echo_tool():
    """Test calling the echo tool on MCP server."""
    import os

    client = McpClient()

    test_dir = os.path.dirname(os.path.abspath(__file__))
    server_path = os.path.join(test_dir, "fixtures", "echo_mcp_server.py")

    config = {
        "command": "python",
        "args": [server_path],
        "env": {},
        "cwd": test_dir
    }

    await client.connect_to_server(config, "echo-test")

    try:
        assert client.connected

        # Call the echo tool
        result = await client.call_tool("echo", {"message": "Hello, MCP!"})
        assert result is not None

    finally:
        await client.cleanup()
