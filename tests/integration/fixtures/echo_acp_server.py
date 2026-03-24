"""
Simple ACP server that echoes back tool calls.
Used for testing the ACP client.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any, Callable


class EchoAcpServer:
    """ACP echo server that responds to tool calls."""

    def __init__(self) -> None:
        self._connected = False

    async def handle_request(self, message: dict[str, Any]) -> dict[str, Any]:
        """Handle an ACP request and return response."""
        method = str(message.get("method", ""))
        request_id = message.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"protocolVersion": "1.0", "capabilities": {}},
            }

        elif method == "echo":
            params = message.get("params", {})
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {"content": [{"type": "text", "text": f"echo: {params}"}]},
            }

        elif "/" in method:
            # Handle server_name/tool_name format
            parts = method.split("/")
            server_name = parts[0] if parts else ""
            tool_name = parts[1] if len(parts) > 1 else ""
            params = message.get("params", {})
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {"type": "text", "text": f"{server_name}/{tool_name}({params})"}
                    ]
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    async def handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a client connection."""
        self._connected = True
        buffer = b""
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                buffer += data

                while True:
                    header_end = buffer.find(b"\n")
                    if header_end == -1:
                        break

                    try:
                        header = json.loads(buffer[:header_end].decode("utf-8"))
                    except json.JSONDecodeError:
                        buffer = buffer[header_end + 1 :]
                        continue

                    content_length = header.get("content-length", 0)
                    if content_length == 0 or len(buffer) < header_end + 1 + content_length:
                        break

                    content = buffer[header_end + 1 : header_end + 1 + content_length]
                    buffer = buffer[header_end + 1 + content_length :]

                    try:
                        message = json.loads(content.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue

                    response = await self.handle_request(message)
                    response_content = json.dumps(response)
                    response_header = json.dumps({"content-length": len(response_content)}) + "\n"
                    writer.write((response_header + response_content).encode())
                    await writer.drain()

        except Exception:
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            self._connected = False


async def main() -> None:
    """Run the ACP echo server on a Unix socket."""
    socket_path = "/tmp/test_acp_echo.sock"

    # Remove existing socket file
    if os.path.exists(socket_path):
        os.remove(socket_path)

    server = EchoAcpServer()
    server_handle = await asyncio.start_server(
        server.handle_connection, path=socket_path
    )

    addr = server_handle.sockets[0].getsockname()
    print(f"ACP echo server listening on {addr}", flush=True)

    try:
        async with server_handle:
            await server_handle.serve_forever()
    except KeyboardInterrupt:
        print("ACP echo server shutting down", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
