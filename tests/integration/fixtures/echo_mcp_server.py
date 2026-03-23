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


def main() -> None:
    """Main loop - read requests from stdin and respond."""
    buffer = ""

    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            buffer += line

            # Try to parse messages from buffer
            while True:
                header_end = buffer.find("\r\n\r\n")
                if header_end == -1:
                    break

                header = buffer[:header_end]
                content_length = 0
                for hline in header.split("\r\n"):
                    if hline.startswith("Content-Length:"):
                        content_length = int(hline.split(":")[1].strip())

                if content_length == 0:
                    break

                total_length = header_end + 4 + content_length
                if len(buffer) < total_length:
                    break

                content = buffer[header_end + 4:total_length]
                buffer = buffer[total_length:]

                try:
                    request = json.loads(content)
                except json.JSONDecodeError:
                    continue

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
