"""
LSP (Language Server Protocol) client implementation.

The orchestrator acts as an LSP client, connecting to LSP servers
that provide language intelligence features (completions, diagnostics, etc.).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import anyio
from anyio.abc import ByteReceiveStream, ByteSendStream, Process

from astrbot import logger
from astrbot._internal.abc.lsp.base_astrbot_lsp_client import BaseAstrbotLspClient

log = logger


class AstrbotLspClient(BaseAstrbotLspClient):
    """
    LSP client for communicating with LSP servers.

    Implements the Microsoft Language Server Protocol for connecting to
    external language intelligence services.
    """

    def __init__(self) -> None:
        self._connected = False
        self._reader: ByteReceiveStream | None = None
        self._writer: ByteSendStream | None = None
        self._server_process: Process | None = None
        self._pending_requests: dict[int, Any] = {}
        self._request_id = 0
        self._server_command: list[str] | None = None
        self._reader_task: asyncio.Task | None = None

    @property
    def connected(self) -> bool:
        """True if connected to an LSP server."""
        return self._connected

    async def connect(self) -> None:
        """
        Connect to configured LSP servers.

        LSP servers are typically stdio-based subprocesses. This method
        establishes the communication channel.
        """
        log.debug("LSP client connecting...")
        # TODO: Load LSP server configurations and start subprocesses
        # For now, mark as connected in idle mode
        self._connected = True
        log.info("LSP client initialized.")

    async def connect_to_server(self, command: list[str], workspace_uri: str) -> None:
        """
        Connect to an LSP server subprocess.

        Args:
            command: Command line to start the LSP server (e.g., ["python", "lsp_server.py"])
            workspace_uri: Root URI of the workspace to serve
        """
        log.debug(f"Starting LSP server: {' '.join(command)}")

        self._server_process = await anyio.open_process(
            command,
            stdin=-1,
            stdout=-1,
            stderr=-1,
        )
        self._reader = self._server_process.stdout
        self._writer = self._server_process.stdin
        self._server_command = command
        self._connected = True

        # Start reading responses in background
        self._reader_task = asyncio.create_task(self._read_responses())

        # Send initialize request
        await self.send_request(
            "initialize",
            {
                "processId": None,
                "rootUri": workspace_uri,
                "capabilities": {},
            },
        )

        # Send initialized notification
        await self.send_notification("initialized", {})

        log.info(f"LSP client connected to server: {command[0]}")

    async def send_request(
        self, method: str, params: dict[str, Any] | None = None
    ) -> Any:
        """Send an LSP request and wait for response."""
        if not self._writer:
            raise RuntimeError("LSP client not connected")

        request_id = self._request_id
        self._request_id += 1

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }

        # Use anyio.Event for request/response matching
        response_event: anyio.Event = anyio.Event()
        response_holder: dict[str, Any] = {}

        async def set_response(response: dict[str, Any]) -> None:
            response_holder["response"] = response
            response_event.set()

        self._pending_requests[request_id] = set_response

        content = json.dumps(message)
        headers = f"Content-Length: {len(content)}\r\n\r\n"
        await self._writer.send((headers + content).encode())

        # Wait for response with timeout
        with anyio.move_on_after(30):
            await response_event.wait()

        if "response" in response_holder:
            return response_holder["response"]
        raise TimeoutError(f"LSP request {method} timed out")

    async def send_notification(
        self, method: str, params: dict[str, Any] | None = None
    ) -> None:
        """Send an LSP notification (no response expected)."""
        if not self._writer:
            raise RuntimeError("LSP client not connected")

        message = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
        }

        content = json.dumps(message)
        headers = f"Content-Length: {len(content)}\r\n\r\n"
        await self._writer.send((headers + content).encode())

    async def _read_responses(self) -> None:
        """Background task to read LSP responses."""
        if not self._reader:
            return

        buffer = b""
        try:
            while self._connected:
                try:
                    data = await self._reader.receive()
                    if not data:
                        break
                    buffer += data

                    while True:
                        # Parse Content-Length header
                        header_end = buffer.find(b"\r\n\r\n")
                        if header_end == -1:
                            break

                        header = buffer[:header_end].decode("utf-8")
                        content_length = 0
                        for line in header.split("\r\n"):
                            if line.startswith("Content-Length:"):
                                content_length = int(line.split(":")[1].strip())

                        if content_length == 0:
                            break

                        total_length = header_end + 4 + content_length
                        if len(buffer) < total_length:
                            break

                        content = buffer[header_end + 4 : total_length]
                        buffer = buffer[total_length:]

                        response = json.loads(content.decode("utf-8"))

                        # Handle response vs notification
                        if "id" in response:
                            request_id = response["id"]
                            handler = self._pending_requests.pop(request_id, None)
                            if handler:
                                await handler(response)
                        else:
                            # Notification (e.g., window/logMessage)
                            await self._handle_notification(response)

                except anyio.EndOfStream:
                    break
        except asyncio.CancelledError:
            pass

    async def _handle_notification(self, notification: dict[str, Any]) -> None:
        """Handle incoming LSP notifications."""
        method = notification.get("method", "")
        log.debug(f"LSP notification: {method}")

    async def shutdown(self) -> None:
        """Shutdown the LSP client."""
        self._connected = False

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None

        if self._server_process:
            try:
                await self.send_notification("shutdown", {})
            except Exception:
                pass

            self._server_process.terminate()
            try:
                with anyio.move_on_after(5):
                    await self._server_process.wait()
            except Exception:
                self._server_process.kill()
            self._server_process = None

        self._pending_requests.clear()
        log.info("LSP client shut down.")
