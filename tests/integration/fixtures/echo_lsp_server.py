"""
Echo LSP Server - Simple LSP server for testing.

This server responds to LSP protocol requests over stdio with Content-Length headers:
- initialize: Initialize the connection and report capabilities
- initialized: Notification (no response)
- shutdown: Graceful shutdown request
- textDocument/didOpen: Document open notification
- other requests: Echoed back with result
"""

from __future__ import annotations

import json
import sys


def write_message(message: dict) -> None:
    """Write a JSON-RPC message to stdout with Content-Length header."""
    content = json.dumps(message)
    headers = f"Content-Length: {len(content)}\r\n\r\n"
    sys.stdout.write(headers + content)
    sys.stdout.flush()


def read_message() -> dict | None:
    """Read a single JSON-RPC message from stdin using LSP stdio protocol."""
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

            # Handle initialize request
            if method == "initialize":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "capabilities": {
                            "textDocumentSync": 1,
                            "hoverProvider": True,
                            "completionProvider": {"resolveProvider": False},
                        }
                    },
                    "serverInfo": {
                        "name": "echo-lsp-server",
                        "version": "1.0.0",
                    },
                }
                write_message(response)

            # Handle initialized notification (no response needed)
            elif method == "initialized":
                continue

            # Handle shutdown request
            elif method == "shutdown":
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": None,
                }
                write_message(response)

            # Handle textDocument/didOpen notification (no response needed)
            elif method == "textDocument/didOpen":
                continue

            # Echo any other request back with the same id
            elif req_id is not None:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"echoed": True, "method": method},
                }
                write_message(response)

        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            }
            write_message(error_response)


if __name__ == "__main__":
    main()