"""MCP client implementation."""

import asyncio
import logging
import os
import sys
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any, cast

from tenacity import (
    before_sleep_log,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from astrbot import logger
from astrbot._internal.abc.mcp.base_astrbot_mcp_client import (
    BaseAstrbotMcpClient,
    McpServerConfig,
    McpToolInfo,
)
from astrbot.core.utils.log_pipe import LogPipe

log = logger

try:
    import anyio

    import mcp
    from mcp.client.sse import sse_client
except (ModuleNotFoundError, ImportError):
    logger.warning(
        "Warning: Missing 'mcp' dependency, MCP services will be unavailable."
    )

try:
    from mcp.client.streamable_http import streamablehttp_client
except (ModuleNotFoundError, ImportError):
    logger.warning(
        "Warning: Missing 'mcp' dependency or MCP library version too old, Streamable HTTP connection unavailable.",
    )


def _prepare_config(config: dict) -> dict:
    """Prepare configuration, handle nested format."""
    if config.get("mcpServers"):
        first_key = next(iter(config["mcpServers"]))
        config = config["mcpServers"][first_key]
    config.pop("active", None)
    return config


def _prepare_stdio_env(config: dict) -> dict:
    """Preserve Windows executable resolution for stdio subprocesses."""
    if sys.platform != "win32":
        return config

    pathext = os.environ.get("PATHEXT")
    if not pathext:
        return config

    prepared = config.copy()
    env = dict(prepared.get("env") or {})
    env.setdefault("PATHEXT", pathext)
    prepared["env"] = env
    return prepared


async def _quick_test_mcp_connection(config: dict) -> tuple[bool, str]:
    """Quick test MCP server connectivity."""
    import aiohttp

    cfg = _prepare_config(config.copy())

    url = cfg["url"]
    headers = cfg.get("headers", {})
    timeout = cfg.get("timeout", 10)

    try:
        if "transport" in cfg:
            transport_type = cfg["transport"]
        elif "type" in cfg:
            transport_type = cfg["type"]
        else:
            raise Exception("MCP connection config missing transport or type field")

        async with aiohttp.ClientSession() as session:
            if transport_type == "streamable_http":
                test_payload = {
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "id": 0,
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "test-client", "version": "1.2.3"},
                    },
                }
                async with session.post(
                    url,
                    headers={
                        **headers,
                        "Content-Type": "application/json",
                        "Accept": "application/json, text/event-stream",
                    },
                    json=test_payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status == 200:
                        return True, ""
                    return False, f"HTTP {response.status}: {response.reason}"
            else:
                async with session.get(
                    url,
                    headers={
                        **headers,
                        "Accept": "application/json, text/event-stream",
                    },
                    timeout=aiohttp.ClientTimeout(total=timeout),
                ) as response:
                    if response.status == 200:
                        return True, ""
                    return False, f"HTTP {response.status}: {response.reason}"

    except asyncio.TimeoutError:
        return False, f"Connection timeout: {timeout} seconds"
    except Exception as e:
        return False, f"{e!s}"


class McpClient(BaseAstrbotMcpClient):
    def __init__(self) -> None:
        # Initialize session and client objects
        self.session: mcp.ClientSession | None = None
        self.exit_stack = AsyncExitStack()
        self._old_exit_stacks: list[AsyncExitStack] = []  # Track old stacks for cleanup

        self.name: str | None = None
        self.active: bool = True
        self.tools: list[mcp.Tool] = []
        self.server_errlogs: list[str] = []
        self.running_event = anyio.Event()
        self.process_pid: int | None = None

        # Store connection config for reconnection
        self._mcp_server_config: McpServerConfig | None = None
        self._server_name: str | None = None
        self._reconnect_lock = anyio.Lock()  # Lock for thread-safe reconnection
        self._reconnecting: bool = False  # For logging and debugging

    async def connect(self) -> None:
        """Initialize the MCP client connection.

        Note: Actual server connections are made via connect_to_server().
        This method prepares the client for use.
        """
        # MCP client is initialized on-demand via connect_to_server
        # This is a no-op stub to satisfy BaseAstrbotMcpClient
        log.debug("MCP client initialized.")

    @property
    def connected(self) -> bool:
        """True if MCP client has an active session."""
        return self.session is not None

    async def list_tools(self) -> list[McpToolInfo]:
        """List all tools from connected MCP servers."""
        if not self.session:
            return []
        result = await self.list_tools_and_save()
        tools = [
            {
                "name": tool.name,
                "description": tool.description or "",
                "inputSchema": tool.inputSchema,
            }
            for tool in result.tools
        ]
        return cast(list[McpToolInfo], tools)

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        read_timeout_seconds: int = 60,
    ) -> Any:
        """Call a tool on the MCP server with reconnection support."""
        return await self.call_tool_with_reconnect(
            tool_name=name,
            arguments=arguments,
            read_timeout_seconds=timedelta(seconds=read_timeout_seconds),
        )

    @staticmethod
    def _extract_stdio_process_pid(streams_context: object) -> int | None:
        """Best-effort extraction for stdio subprocess PID used by lease cleanup.

        TODO(refactor): replace this async-generator frame introspection with a
        stable MCP library hook once the upstream transport exposes process PID.
        """
        generator = getattr(streams_context, "gen", None)
        frame = getattr(generator, "ag_frame", None)
        if frame is None:
            return None
        process = frame.f_locals.get("process")
        pid = getattr(process, "pid", None)
        try:
            return int(pid) if pid is not None else None
        except (TypeError, ValueError):
            return None

    async def connect_to_server(self, config: McpServerConfig, name: str) -> None:
        """Connect to MCP server

        If `url` parameter exists:
            1. When transport is specified as `streamable_http`, use Streamable HTTP connection.
            2. When transport is specified as `sse`, use SSE connection.
            3. If not specified, default to SSE connection to MCP service.

        Args:
            config: Configuration for the MCP server. See https://modelcontextprotocol.io/quickstart/server

        """
        # Store config for reconnection
        self._mcp_server_config = config
        self._server_name = name
        self.process_pid = None

        cfg = _prepare_config(dict(config))

        def logging_callback(
            msg: str | mcp.types.LoggingMessageNotificationParams,
        ) -> None:
            # Handle MCP service error logs
            if isinstance(msg, mcp.types.LoggingMessageNotificationParams):
                if msg.level in ("warning", "error", "critical", "alert", "emergency"):
                    log_msg = f"[{msg.level.upper()}] {msg.data!s}"
                    self.server_errlogs.append(log_msg)

        if "url" in cfg:
            success, error_msg = await _quick_test_mcp_connection(cfg)
            if not success:
                raise Exception(error_msg)

            if "transport" in cfg:
                transport_type = cfg["transport"]
            elif "type" in cfg:
                transport_type = cfg["type"]
            else:
                raise Exception("MCP connection config missing transport or type field")

            if transport_type != "streamable_http":
                # SSE transport method
                self._streams_context = sse_client(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=cfg.get("timeout", 5),
                    sse_read_timeout=cfg.get("sse_read_timeout", 60 * 5),
                )
                streams = await self.exit_stack.enter_async_context(
                    self._streams_context,
                )

                # Create a new client session
                read_timeout = timedelta(seconds=cfg.get("session_read_timeout", 60))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        *streams,
                        read_timeout_seconds=read_timeout,
                        logging_callback=cast(Any, logging_callback),
                    ),
                )
            else:
                timeout = timedelta(seconds=cfg.get("timeout", 30))
                sse_read_timeout = timedelta(
                    seconds=cfg.get("sse_read_timeout", 60 * 5),
                )
                self._streams_context = streamablehttp_client(
                    url=cfg["url"],
                    headers=cfg.get("headers", {}),
                    timeout=timeout,
                    sse_read_timeout=sse_read_timeout,
                    terminate_on_close=cfg.get("terminate_on_close", True),
                )
                read_s, write_s, _ = await self.exit_stack.enter_async_context(
                    self._streams_context,
                )

                # Create a new client session
                read_timeout = timedelta(seconds=cfg.get("session_read_timeout", 60))
                self.session = await self.exit_stack.enter_async_context(
                    mcp.ClientSession(
                        read_stream=read_s,
                        write_stream=write_s,
                        read_timeout_seconds=read_timeout,
                        logging_callback=logging_callback,  # type: ignore
                    ),
                )

        else:
            cfg = _prepare_stdio_env(cfg)
            server_params = mcp.StdioServerParameters(
                **cfg,
            )

            def callback(msg: str | mcp.types.LoggingMessageNotificationParams) -> None:
                # Handle MCP service error logs
                if isinstance(msg, mcp.types.LoggingMessageNotificationParams):
                    if msg.level in (
                        "warning",
                        "error",
                        "critical",
                        "alert",
                        "emergency",
                    ):
                        log_msg = f"[{msg.level.upper()}] {msg.data!s}"
                        self.server_errlogs.append(log_msg)

            stdio_transport = await self.exit_stack.enter_async_context(
                mcp.stdio_client(
                    server_params,
                    errlog=cast(Any, LogPipe(
                        level=logging.INFO,
                        logger=logger,
                        identifier=f"MCPServer-{name}",
                        callback=callback,
                    )),
                ),
            )
            self.process_pid = self._extract_stdio_process_pid(stdio_transport)

            # Create a new client session
            self.session = await self.exit_stack.enter_async_context(
                mcp.ClientSession(*stdio_transport),
            )
        await self.session.initialize()

    async def list_tools_and_save(self) -> mcp.ListToolsResult:
        """List all tools from the server and save them to self.tools"""
        if not self.session:
            raise Exception("MCP Client is not initialized")
        response = await self.session.list_tools()
        self.tools = response.tools
        return response

    async def _reconnect(self) -> None:
        """Reconnect to the MCP server using the stored configuration.

        Uses asyncio.Lock to ensure thread-safe reconnection in concurrent environments.

        Raises:
            Exception: raised when reconnection fails
        """
        async with self._reconnect_lock:
            # Check if already reconnecting (useful for logging)
            if self._reconnecting:
                logger.debug(
                    f"MCP Client {self._server_name} is already reconnecting, skipping"
                )
                return

            if not self._mcp_server_config or not self._server_name:
                raise Exception("Cannot reconnect: missing connection configuration")

            self._reconnecting = True
            try:
                logger.info(
                    f"Attempting to reconnect to MCP server {self._server_name}..."
                )

                # Save old exit_stack for later cleanup (don't close it now to avoid cancel scope issues)
                if self.exit_stack:
                    self._old_exit_stacks.append(self.exit_stack)

                # Mark old session as invalid
                self.session = None

                # Create new exit stack for new connection
                self.exit_stack = AsyncExitStack()

                # Reconnect using stored config
                await self.connect_to_server(self._mcp_server_config, self._server_name)
                await self.list_tools_and_save()

                logger.info(
                    f"Successfully reconnected to MCP server {self._server_name}"
                )
            except Exception as e:
                logger.error(
                    f"Failed to reconnect to MCP server {self._server_name}: {e}"
                )
                raise
            finally:
                self._reconnecting = False

    async def call_tool_with_reconnect(
        self,
        tool_name: str,
        arguments: dict,
        read_timeout_seconds: timedelta,
    ) -> mcp.types.CallToolResult:
        """Call MCP tool with automatic reconnection on failure, max 2 retries.

        Args:
            tool_name: tool name
            arguments: tool arguments
            read_timeout_seconds: read timeout

        Returns:
            MCP tool call result

        Raises:
            ValueError: MCP session is not available
            anyio.ClosedResourceError: raised after reconnection failure
        """

        @retry(
            retry=retry_if_exception_type(anyio.ClosedResourceError),
            stop=stop_after_attempt(2),
            wait=wait_exponential(multiplier=1, min=1, max=3),
            before_sleep=cast(Any, before_sleep_log(logger, logging.WARNING)),
            reraise=True,
        )
        async def _call_with_retry():
            if not self.session:
                raise ValueError("MCP session is not available for MCP function tools.")

            try:
                return await self.session.call_tool(
                    name=tool_name,
                    arguments=arguments,
                    read_timeout_seconds=read_timeout_seconds,
                )
            except anyio.ClosedResourceError:
                logger.warning(
                    f"MCP tool {tool_name} call failed (ClosedResourceError), attempting to reconnect..."
                )
                # Attempt to reconnect
                await self._reconnect()
                # Reraise the exception to trigger tenacity retry
                raise

        return await _call_with_retry()

    async def cleanup(self) -> None:
        """Clean up resources including old exit stacks from reconnections"""
        # Close current exit stack
        try:
            await self.exit_stack.aclose()
        except Exception as e:
            logger.debug(f"Error closing current exit stack: {e}")

        # Don't close old exit stacks as they may be in different task contexts
        # They will be garbage collected naturally
        # Just clear the list to release references
        self._old_exit_stacks.clear()

        # Set running_event first to unblock any waiting tasks
        self.running_event.set()
        self.process_pid = None
