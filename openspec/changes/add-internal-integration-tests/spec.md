# Internal Integration Tests Specification

## Overview

Internal integration tests validate the MCP (Model Context Protocol) and ACP (AstrBot Communication Protocol) client implementations against real server fixtures. Tests use subprocess-based fixtures to simulate actual protocol communication.

## Test Structure

```
tests/
├── integration/
│   ├── fixtures/
│   │   ├── echo_mcp_server.py   # MCP stdio-based echo server
│   │   └── echo_acp_server.py   # ACP TCP/Unix socket echo server
│   ├── test_mcp_integration.py   # MCP client integration tests
│   └── test_acp_integration.py  # ACP client integration tests
```

## MCP Integration Tests

### Echo MCP Server Fixture

**Location:** `tests/integration/fixtures/echo_mcp_server.py`

A stdio-based MCP server implementing the JSON-RPC 2.0 protocol over stdio with proper `Content-Length` header framing.

**Supported Methods:**
- `initialize`: Returns protocol version `2024-11-05` and server info
- `tools/list`: Returns two tools: `echo` and `add`
- `tools/call`: Echoes back tool name and arguments

**Protocol Details:**
- Reads JSON-RPC requests from stdin using `Content-Length` headers
- Writes JSON-RPC responses to stdout with `Content-Length` headers
- Terminates on EOF or invalid input

### MCP Client Tests

**Location:** `tests/integration/test_mcp_integration.py`

| Test | Status | Description |
|------|--------|-------------|
| `test_mcp_client_initialization` | Pass | Verifies `McpClient()` instantiates correctly |
| `test_mcp_client_connect_is_noop` | Pass | Verifies `connect()` without config is a no-op |
| `test_mcp_echo_server_connection` | Skip | MCP protocol handshake requires server notifications after initialize response |
| `test_mcp_list_tools` | Skip | Same protocol complexity reason |
| `test_mcp_call_echo_tool` | Skip | Same protocol complexity reason |

**Skip Reason:** `McpClient` uses `ClientSession.initialize()` which waits for server notifications after sending the initialize response. The echo server fixture sends the response but does not send the required notifications, causing the client to hang.

## ACP Integration Tests

### Echo ACP Server Fixture

**Location:** `tests/integration/fixtures/echo_acp_server.py`

A TCP/Unix socket-based ACP server implementing JSON-RPC 2.0 over stream transport.

**Supported Methods:**
- `initialize`: Returns protocol version `1.0`
- `echo`: Echoes back params
- `{server_name}/{tool_name}`: Generic tool handling format

**Protocol Details:**
- Uses newline-delimited JSON with `content-length` header
- Runs on Unix socket at `/tmp/test_acp_echo.sock`
- Async handler using `asyncio.StreamReader`/`StreamWriter`

### ACP Client Tests

**Location:** `tests/integration/test_acp_integration.py`

**Class:** `TestAstrbotAcpClient`

| Test | Status | Description |
|------|--------|-------------|
| `test_acp_client_initial_state` | Pass | Verifies client starts disconnected |
| `test_acp_client_connect_to_tcp_server` | Pass | Verifies TCP connection to echo server |
| `test_acp_client_connect_to_unix_socket` | Pass | Verifies Unix socket connection |

**Test Approach:**
- Inline echo server using `asyncio.start_server` (TCP) or `loop.create_unix_server`
- Dynamically assigns available port via `port=0`
- Verifies `connected` state and non-null reader/writer after connection
- Properly cleans up server/client in finally block

## Running Tests

```bash
# Run all integration tests
uv run pytest tests/integration/ -v

# Run MCP integration tests only
uv run pytest tests/integration/test_mcp_integration.py -v

# Run ACP integration tests only
uv run pytest tests/integration/test_acp_integration.py -v
```

## Test Results Summary

| Protocol | Tests | Passed | Skipped |
|----------|-------|--------|---------|
| MCP | 5 | 2 | 3 |
| ACP | 3 | 3 | 0 |
| **Total** | **8** | **5** | **3** |

## Implementation Notes

1. **MCP Protocol Complexity:** The MCP protocol requires a specific handshake sequence where servers send notifications (not responses) after `initialize`. This is not yet supported by the echo fixture.

2. **ACP Simplicity:** ACP uses simpler request/response semantics over asyncio streams, making it easier to test.

3. **Fixture Lifespan:** Echo server fixtures are created per-test to ensure isolation.

4. **Resource Cleanup:** All tests use try/finally patterns to ensure proper cleanup of server processes and socket files.
