"""
Echo MCP Server - Simple MCP server for testing.

This server responds to MCP protocol requests over stdio:
- initialize: Initialize the connection
- tools/list: List available tools
- tools/call: Call a tool (echoes back the call)
"""

from __future__ import annotations

import json
import sys


def write_response(response: dict) -> None:
    """Write a JSON-RPC response to stdout."""
    content = json.dumps(response)
    headers = f"Content-Length: {len(content)}\r\n\r\n"
    sys.stdout.write(headers + content)
    sys.stdout.flush()


def read_message() -> dict | None:
    """Read a single JSON-RPC message from stdin using MCP stdio protocol."""
    # Read headers until we get \r\n\r\n
    header_bytes = b""
    while True:
        ch = sys.stdin.buffer.read(1)
        if not ch:
            return None
        header_bytes += ch
        if header_bytes.endswith(b"\r\n\r\n"):
            break

    # Parse Content-Length from headers
    header_text = header_bytes.decode("utf-8")
    content_length = 0
    for line in header_text.split("\r\n"):
        if line.startswith("Content-Length:"):
            content_length = int(line.split(":")[1].strip())
            break

    if content_length == 0:
        return None

    # Read the content body
    content = sys.stdin.buffer.read(content_length)
    if not content:
        return None

    return json.loads(content.decode("utf-8"))


def main() -> None:
    """Main loop - read requests from stdin and respond."""
    while True:
        try:
            request = read_message()
            if request is None:
                break

            method = request.get("method", "")
            req_id = request.get("id")

            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {
                            "name": "echo-mcp-server",
                            "version": "1.0.0"
                        }
                    }
                }
                write_response(response)

            elif method == "tools/list":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "tools": [
                            {
                                "name": "echo",
                                "description": "Echo back the input",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "message": {"type": "string"}
                                    }
                                }
                            },
                            {
                                "name": "add",
                                "description": "Add two numbers",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {
                                        "a": {"type": "number"},
                                        "b": {"type": "number"}
                                    }
                                }
                            }
                        ]
                    }
                }
                write_response(response)

            elif method == "tools/call":
                params = request.get("params", {})
                tool_name = params.get("name", "")
                arguments = params.get("arguments", {})

                if tool_name == "echo":
                    result = {"echoed": arguments.get("message", "")}
                elif tool_name == "add":
                    a = arguments.get("a", 0)
                    b = arguments.get("b", 0)
                    result = {"sum": a + b}
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result)}]
                    }
                }
                write_response(response)

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)}
            }
            write_response(error_response)


if __name__ == "__main__":
    main()
