from __future__ import annotations

import asyncio
import os
import inspect
from typing import Any, AsyncGenerator

from loguru import logger

from ...api.event.astr_message_event import AstrMessageEvent
from ...api.star.star import StarMetadata
from .registry import EventType, StarHandlerMetadata
from ..rpc.jsonrpc import (
    JSONRPCErrorResponse,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from ..rpc.client import JSONRPCClient
from ..rpc.client.stdio import StdioClient
from ..rpc.client.websocket import WebSocketClient
from ..rpc.request_helper import RPCRequestHelper
from .virtual import VirtualStar
from .new_star_utils import (
    ClientHandshakeHandler,
    PluginRequestHandler,
    HandlerProxyFactory,
)


class NewStar(VirtualStar):
    """NewStar implementation for isolated plugin runtime.

    NewStar runs plugins in separate processes and communicates via JSON-RPC.
    This provides better isolation, security, and compatibility.
    """

    def __init__(
        self,
        client: JSONRPCClient,
        context: Any,
    ) -> None:
        """Initialize a NewStar instance.

        Args:
            client: JSON-RPC client for communication
            context: Context instance for managing managers and their functions
        """
        super().__init__(context)

        self._client = client
        self._metadata: dict[str, StarMetadata] = {}
        self._handlers: list[StarHandlerMetadata] = []
        self._active = False

        # Use RPCRequestHelper for managing requests
        self._rpc_helper = RPCRequestHelper()

        # Initialize specialized handlers
        self._handshake_handler = ClientHandshakeHandler(self._rpc_helper)
        self._plugin_request_handler = PluginRequestHandler(context)
        self._handler_proxy_factory = HandlerProxyFactory(client, self._rpc_helper)

        # Set up message handler
        self._client.set_message_handler(self._handle_message)

    async def _handle_message(self, message: JSONRPCMessage) -> None:
        """Handle incoming JSON-RPC messages from the plugin.

        Args:
            message: The received JSON-RPC message
        """
        if isinstance(message, JSONRPCSuccessResponse) or isinstance(
            message,
            JSONRPCErrorResponse,
        ):
            # Delegate to RPCRequestHelper
            self._rpc_helper.resolve_pending_request(message)

        elif isinstance(message, JSONRPCRequest):
            # Handle notifications from plugin (streaming events or method calls)
            if message.method in [
                "handler_stream_start",
                "handler_stream_update",
                "handler_stream_end",
            ]:
                await self._rpc_helper.handle_stream_notification(message)
            else:
                # Plugin is calling a method on the core - delegate to PluginRequestHandler
                asyncio.create_task(
                    self._plugin_request_handler.handle_request(message, self._client)
                )

    async def initialize(self) -> None:
        """Start the plugin process and establish connection."""
        # Start the client (which may start a subprocess for STDIO)
        await self._client.start()
        logger.info("Client started and ready for communication")

    async def handshake(self) -> dict[str, StarMetadata]:
        """Perform handshake to retrieve plugin metadata.

        Returns:
            Plugin metadata including name, version, handlers, etc.
        """
        # Delegate to ClientHandshakeHandler
        (
            self._metadata,
            self._handlers,
        ) = await self._handshake_handler.perform_handshake(self._client)

        # Set up handler proxies
        self._handler_proxy_factory.setup_handlers(self._handlers)

        return self._metadata

    def get_triggered_handlers(
        self, event: AstrMessageEvent
    ) -> list[StarHandlerMetadata]:
        """Get the list of handlers that should be triggered for this event.

        Args:
            event: The message event

        Returns:
            List of handler metadata that should handle this event
        """
        # For AdapterMessageEvent, return relevant handlers
        # This is cached locally, no RPC needed
        triggered = []

        for handler in self._handlers:
            if handler.event_type == EventType.AdapterMessageEvent:
                # In practice, you'd check filters here
                triggered.append(handler)

        return triggered

    async def call_handler(
        self,
        handler: StarHandlerMetadata,
        event: AstrMessageEvent,
        *args,
        **kwargs,
    ) -> AsyncGenerator[Any, None]:
        """Call a specific handler in the plugin.

        Args:
            handler: The handler metadata
            event: The message event
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            An async generator yielding results from the handler
        """
        logger.debug(f"Calling handler: {handler.handler_name}")

        # Call the handler proxy
        assert inspect.isasyncgenfunction(handler.handler), (
            "Handler proxy must be an async generator function"
        )
        async for result in handler.handler(event, **kwargs):
            yield result

    async def stop(self) -> None:
        """Stop the NewStar and cleanup resources."""
        await self._client.stop()
        logger.info("NewStar client stopped.")


class NewStdioStar(NewStar):
    """NewStar implementation using STDIO communication.

    This class automatically starts the plugin subprocess and manages its lifecycle.
    """

    def __init__(
        self,
        plugin_dir: str,
        python_executable: str = "python",
        context: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a STDIO-based NewStar.

        Args:
            plugin_dir: Path to the plugin directory
            python_executable: Python executable to use (defaults to 'python')
            context: Context instance for managing managers and their functions
        """
        # Construct the command to start the plugin
        if not os.path.exists(plugin_dir):
            raise FileNotFoundError(f"Plugin directory not found: {plugin_dir}")

        command = [python_executable, "-m", "astrbot_sdk", "run", "--stdio"]

        # Create StdioClient with subprocess management
        client = StdioClient(command=command, cwd=plugin_dir)
        super().__init__(client, context=context)


class NewWebSocketStar(NewStar):
    """NewStar implementation using WebSocket communication.

    Note: WebSocket-based stars do not start the plugin process.
    The plugin should be started externally and connect to the specified WebSocket URL.
    """

    def __init__(
        self,
        url: str,
        heartbeat: float = 30.0,
        reconnect_interval: float = 5.0,
        context: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize a WebSocket-based NewStar.

        Args:
            url: WebSocket server URL that the plugin will connect to
            heartbeat: Heartbeat interval in seconds
            reconnect_interval: Interval between reconnection attempts in seconds
            context: Context instance for managing managers and their functions
        """
        client = WebSocketClient(
            url=url, heartbeat=heartbeat, reconnect_interval=reconnect_interval
        )
        super().__init__(client, context=context)
        self._url = url
        self._heartbeat = heartbeat
        self._reconnect_interval = reconnect_interval
