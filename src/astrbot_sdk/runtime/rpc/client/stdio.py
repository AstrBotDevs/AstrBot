from __future__ import annotations

import asyncio
import json
import subprocess
from typing import IO, Any

from loguru import logger

from ..jsonrpc import (
    JSONRPCErrorResponse,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from .base import JSONRPCClient


class StdioClient(JSONRPCClient):
    """JSON-RPC client using standard input/output for communication."""

    def __init__(
        self,
        command: list[str],
        cwd: str | None = None,
    ) -> None:
        """Initialize the STDIO client.

        Args:
            command: Command to start subprocess (e.g., ['python', 'plugin.py'])
            cwd: Working directory for subprocess
        """
        super().__init__()
        self._command = command
        self._cwd = cwd
        self._process: subprocess.Popen | None = None
        self._stdin: IO[Any] | None = None
        self._stdout: IO[Any] | None = None
        self._read_task: asyncio.Task | None = None
        self._write_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the client and launch subprocess."""
        if self._running:
            logger.warning("StdioClient is already running")
            return

        self._running = True

        # Start subprocess
        await self._start_subprocess()

        self._read_task = asyncio.create_task(self._read_loop())
        logger.info("StdioClient started")

    async def _start_subprocess(self) -> None:
        """Start the subprocess and connect to its stdio."""
        logger.info(f"Starting subprocess: {' '.join(self._command)}")

        try:
            self._process = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                text=True,
                bufsize=1,  # Line buffered
            )

            # Use subprocess's stdio
            self._stdin = self._process.stdout  # Read from subprocess stdout
            self._stdout = self._process.stdin  # Write to subprocess stdin

            logger.info(f"Subprocess started with PID {self._process.pid}")

            # Start monitoring stderr
            asyncio.create_task(self._monitor_stderr())

        except Exception as e:
            logger.error(f"Failed to start subprocess: {e}")
            raise

    async def _monitor_stderr(self) -> None:
        """Monitor subprocess stderr and log output."""
        if not self._process or not self._process.stderr:
            return

        loop = asyncio.get_event_loop()

        try:
            while self._running and self._process.poll() is None:
                line = await loop.run_in_executor(None, self._process.stderr.readline)
                if line:
                    logger.debug(f"[Subprocess stderr] {line.strip()}")
                else:
                    break
        except Exception as e:
            logger.error(f"Error monitoring stderr: {e}")

    async def stop(self) -> None:
        """Stop the client and terminate subprocess if running."""
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

        # Terminate subprocess if running
        if self._process:
            logger.info("Terminating subprocess...")
            self._process.terminate()
            try:
                self._process.wait(timeout=5.0)
                logger.info("Subprocess terminated gracefully")
            except subprocess.TimeoutExpired:
                logger.warning("Subprocess did not terminate, killing...")
                self._process.kill()
                self._process.wait()
                logger.info("Subprocess killed")

            self._process = None

        logger.info("StdioClient stopped")

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
        if self._stdout:
            self._stdout.write(line + "\n")
            self._stdout.flush()

    async def _read_loop(self) -> None:
        """Main loop to read messages from stdin."""
        if not self._stdin:
            logger.error("No stdin available for reading")
            return

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
