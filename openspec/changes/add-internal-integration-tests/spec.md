# Internal Integration Tests Specification

## Overview

Internal integration tests validate the MCP and ACP protocol client implementations against real server fixtures.

## Test Structure

tests/integration/
  - fixtures/
    - echo_mcp_server.py   # Stdio-based MCP echo server
    - echo_acp_server.py   # TCP/Unix socket ACP echo server
  - test_mcp_integration.py  # MCP client integration tests
  - test_acp_integration.py  # ACP client integration tests

## MCP Integration Tests

### Echo MCP Server Fixture
- **Location:** tests/integration/fixtures/echo_mcp_server.py
- **Protocol:** Stdio-based JSON-RPC with Content-Length headers
- **Methods:** initialize, tools/list, tools/call

### MCP Client Tests
| Test | Description | Status |
|------|-------------|--------|
| test_mcp_client_initialization | McpClient instantiation | Passing |
| test_mcp_client_connect_is_noop | connect() without config | Passing |
| test_mcp_echo_server_connection | Connect to echo server | Skipped |
| test_mcp_list_tools | List tools | Skipped |
| test_mcp_call_echo_tool | Call echo tool | Skipped |

**Note:** 3 tests skipped due to MCP ClientSession.initialize() protocol complexity.

## ACP Integration Tests

### Echo ACP Server Fixture
- **Location:** tests/integration/fixtures/echo_acp_server.py
- **Transport:** TCP/Unix socket with Content-Length headers
- **Methods:** initialize, echo, {server}/{tool}

### ACP Client Tests
| Test | Description | Status |
|------|-------------|--------|
| test_acp_client_initial_state | Verify disconnected state | Passing |
| test_acp_client_connect_to_tcp_server | Connect to TCP server | Passing |
| test_acp_client_connect_to_unix_socket | Connect to Unix socket | Passing |

## Running Tests

```bash
uv run pytest tests/integration/ -v
```

## Dependencies
- pytest, pytest-asyncio, anyio