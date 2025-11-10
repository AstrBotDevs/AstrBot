from __future__ import annotations

import asyncio
import json
import sys
from typing import IO, Any

from loguru import logger

from ..jsonrpc import (
    JSONRPCErrorResponse,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from .base import JSONRPCServer


class StdioServer(JSONRPCServer):
    """JSON-RPC server using standard input/output for communication.

    This runs in the plugin process and communicates with AstrBot via stdio.
    """

    def __init__(
        self,
        stdin: IO[Any] | None = None,
        stdout: IO[Any] | None = None,
    ) -> None:
        """Initialize the STDIO server.

        Args:
            stdin: Input stream to read from (defaults to sys.stdin)
            stdout: Output stream to write to (defaults to sys.stdout)
        """
        super().__init__()
        self._stdin = stdin or sys.stdin
        self._stdout = stdout or sys.stdout
        self._read_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the server and begin reading from stdin."""
        if self._running:
            logger.warning("StdioServer is already running")
            return

        self._running = True
        self._read_task = asyncio.create_task(self._read_loop())
        logger.info("StdioServer started")

    async def stop(self) -> None:
        """Stop the server and cleanup resources."""
        if not self._running:
            return

        self._running = False

        # Cancel read task
        if self._read_task:
            self._read_task.cancel()
            try:
                await self._read_task
            except asyncio.CancelledError:
                pass
            self._read_task = None

        logger.info("StdioServer stopped")

    async def send_message(self, message: JSONRPCMessage) -> None:
        """Send a JSON-RPC message to stdout.

        Args:
            message: The JSON-RPC message to send
        """
        async with self._write_lock:
            try:
                json_str = message.model_dump_json(exclude_none=True)
                await asyncio.get_event_loop().run_in_executor(
                    None, self._write_line, json_str
                )
            except Exception as e:
                logger.error(f"Failed to send message: {e}")
                raise

    def _write_line(self, line: str) -> None:
        """Write a line to stdout (synchronous helper)."""
        self._stdout.write(line + "\n")
        self._stdout.flush()

    async def _read_loop(self) -> None:
        """Main loop to read messages from stdin."""
        logger.debug("Started reading from stdin")
        loop = asyncio.get_event_loop()

        try:
            while self._running:
                # Read line from stdin in executor to avoid blocking
                line = await loop.run_in_executor(None, self._stdin.readline)

                if not line:
                    # EOF reached
                    logger.info("EOF reached on stdin")
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    # Parse JSON-RPC message
                    message = self._parse_message(line)
                    await self._handle_message(message)
                except Exception as e:
                    logger.error(f"Failed to parse message: {e}, raw line: {line}")

        except asyncio.CancelledError:
            logger.debug("Read loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Error in read loop: {e}")
        finally:
            logger.debug("Stopped reading from stdin")

    def _parse_message(self, line: str) -> JSONRPCMessage:
        """Parse a JSON-RPC message from a string.

        Args:
            line: JSON string to parse

        Returns:
            Parsed JSONRPCMessage (Request, SuccessResponse, or ErrorResponse)
        """
        data = json.loads(line)

        # Determine message type based on presence of fields
        if "method" in data:
            return JSONRPCRequest.model_validate(data)
        elif "error" in data:
            return JSONRPCErrorResponse.model_validate(data)
        elif "result" in data:
            return JSONRPCSuccessResponse.model_validate(data)
        else:
            raise ValueError(f"Invalid JSON-RPC message: {data}")
