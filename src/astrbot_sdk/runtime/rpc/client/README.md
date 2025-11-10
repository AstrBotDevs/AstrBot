# JSON-RPC Server Implementation

This directory contains industry-standard implementations of JSON-RPC 2.0 servers for inter-process communication.

## Overview

The implementation follows best practices:

- **Clean separation of concerns**: Servers handle only communication, not business logic
- **Async/await**: Non-blocking I/O for better performance
- **Type safety**: Full type hints with Pydantic models
- **Error handling**: Proper logging and error propagation
- **Resource management**: Clean startup/shutdown lifecycle

## Architecture

### Base Class: `JSONRPCServer`

Abstract base class defining the server interface:

- `set_message_handler(handler)`: Register a callback for incoming messages
- `start()`: Start the server
- `stop()`: Stop the server and cleanup
- `send_message(message)`: Send a JSON-RPC message

### STDIO Server: `StdioServer`

Communicates via standard input/output using line-delimited JSON.

**Features:**

- One JSON-RPC message per line
- Non-blocking async I/O using executors
- Thread-safe write operations with asyncio locks
- Graceful EOF handling

**Use cases:**

- Plugin subprocess communication
- Command-line tools
- Pipeline-based architectures

**Example:**

```python
from astrbot_sdk.runtime.server import StdioServer
from astrbot_sdk.runtime.rpc.jsonrpc import JSONRPCMessage

server = StdioServer()

def handle_message(message: JSONRPCMessage):
    # Process the message
    pass

server.set_message_handler(handle_message)
await server.start()
```

### WebSocket Server: `WebSocketServer`

Communicates via WebSocket connections.

**Features:**

- Single active connection (typical for IPC)
- Heartbeat/ping-pong for connection health
- Support for text and binary messages
- Graceful connection lifecycle management
- Built on aiohttp for production readiness

**Configuration:**

```python
from astrbot_sdk.runtime.server import WebSocketServer

server = WebSocketServer(
    host="127.0.0.1",
    port=8765,
    path="/rpc",
    heartbeat=30.0  # seconds, 0 to disable
)
```

**Use cases:**

- Network-based plugin communication
- Development/debugging (easier to inspect)
- Multiple plugin instances

## Message Format

All servers use JSON-RPC 2.0 format:

**Request:**

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "method": "method_name",
  "params": {"key": "value"}
}
```

**Success Response:**

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "result": {"data": "response"}
}
```

**Error Response:**

```json
{
  "jsonrpc": "2.0",
  "id": "unique-id",
  "error": {
    "code": -32600,
    "message": "Invalid Request",
    "data": null
  }
}
```

## Usage Examples

See the `examples/` directory:

- `server_stdio_example.py`: STDIO server with echo handler
- `server_websocket_example.py`: WebSocket server with echo handler
- `client_stdio_test.py`: Test client for STDIO
- `client_websocket_test.py`: Test client for WebSocket

### Running STDIO Example

Terminal 1 (server):

```bash
python examples/server_stdio_example.py
```

Then type JSON-RPC requests:

```json
{"jsonrpc":"2.0","id":"1","method":"test","params":{"hello":"world"}}
```

Or use the test client:

```bash
python examples/client_stdio_test.py | python examples/server_stdio_example.py
```

### Running WebSocket Example

Terminal 1 (server):

```bash
python examples/server_websocket_example.py
```

Terminal 2 (client):

```bash
python examples/client_websocket_test.py
```

## Design Principles

1. **No business logic**: Servers only handle transport and serialization
2. **Callback-based**: Use `set_message_handler()` for loose coupling
3. **Async-first**: All I/O operations are non-blocking
4. **Production-ready**: Proper error handling, logging, and resource cleanup
5. **Testable**: Easy to mock and test with custom stdin/stdout

## Integration with AstrBot SDK

These servers are designed to be used by the Virtual Plugin Layer (VPL):

```python
# In plugin runtime (subprocess)
from astrbot_sdk.runtime.server import StdioServer

server = StdioServer()
server.set_message_handler(handle_core_requests)
await server.start()

# In AstrBot Core
# Spawn plugin subprocess with stdio transport
# Send JSON-RPC requests to plugin stdin
# Receive JSON-RPC responses from plugin stdout
```

## Thread Safety

- Both servers use `asyncio.Lock` for write operations
- Message handlers are called synchronously but can schedule async tasks
- Servers must run in an asyncio event loop

## Error Handling

- Parse errors are logged but don't crash the server
- Connection errors trigger cleanup and can be recovered
- User code exceptions in message handlers are contained
