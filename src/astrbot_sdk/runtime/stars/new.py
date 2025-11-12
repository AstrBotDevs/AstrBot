from __future__ import annotations

import asyncio
import os
import inspect
from typing import Any, AsyncGenerator

from loguru import logger

from ...api.event.astr_message_event import AstrMessageEvent, AstrMessageEventModel
from ...api.star.star import StarMetadata
from ..stars.registry import EventType, StarHandlerMetadata
from ..rpc.jsonrpc import (
    JSONRPCErrorData,
    JSONRPCErrorResponse,
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
)
from ..types import CallHandlerRequest, HandshakeRequest
from ..rpc.client import JSONRPCClient
from ..rpc.client.stdio import StdioClient
from ..rpc.client.websocket import WebSocketClient
from ..rpc.request_helper import RPCRequestHelper
from .virtual import VirtualStar


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
                # Plugin is calling a method on the core
                asyncio.create_task(self._handle_plugin_request(message))

    async def _handle_plugin_request(self, request: JSONRPCRequest) -> None:
        """Handle a JSON-RPC request from the plugin (plugin calling core methods).

        Args:
            request: The JSON-RPC request from the plugin
        """
        result: Any = None
        try:
            # Handle core methods that plugins might call
            method = request.method
            params = request.params

            if method == "call_context_function":
                ctx = self._context
                func_full_name = params.get("name", "")
                args = params.get("args", {})
                logger.debug(
                    f"plugin called call_context_function: {func_full_name} with args: {args}"
                )

                # Get the registered function from context
                func = ctx.get_registered_function(func_full_name)
                if func is None:
                    raise ValueError(f"Function not found: {func_full_name}")

                # Call the function
                import inspect

                if inspect.iscoroutinefunction(func):
                    result = await func(**args)
                else:
                    result = func(**args)

                logger.debug(f"call_context_function result: {result}")
            else:
                raise ValueError(f"Unknown method: {method}")

            # Send success response
            response = JSONRPCSuccessResponse(
                jsonrpc="2.0",
                id=request.id,
                result={
                    "data": result,
                },
            )
            await self._client.send_message(response)

        except Exception as e:
            logger.error(f"Error handling plugin request: {e}")
            # Send error response
            error_response = JSONRPCErrorResponse(
                jsonrpc="2.0",
                id=request.id,
                error=JSONRPCErrorData(
                    code=-32603,
                    message=str(e),
                ),
            )
            await self._client.send_message(error_response)

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
        logger.info("Performing handshake with plugin...")

        response = await self._rpc_helper.call_rpc(
            self._client,
            HandshakeRequest(
                jsonrpc="2.0",
                id=self._rpc_helper._generate_request_id(),
                method="handshake",
            ),
        )

        if not isinstance(response, JSONRPCSuccessResponse):
            raise RuntimeError("Handshake failed: Invalid response from plugin")

        result = response.result

        if isinstance(result, dict):
            # Parse metadata
            for star_name, star_info in result.items():
                handlers_data = star_info.pop("handlers", None)
                metadata = StarMetadata(**star_info)
                self._metadata[star_name] = metadata

                # Get handlers
                self._handlers = []

                for handler_data in handlers_data:
                    handler_meta = StarHandlerMetadata(
                        event_type=EventType(handler_data["event_type"]),
                        handler_full_name=handler_data["handler_full_name"],
                        handler_name=handler_data["handler_name"],
                        handler_module_path=handler_data["handler_module_path"],
                        handler=self._create_handler_proxy(
                            handler_data["handler_full_name"]
                        ),
                        event_filters=[],
                        desc=handler_data.get("desc", ""),
                        extras_configs=handler_data.get("extras_configs", {}),
                    )
                    self._handlers.append(handler_meta)

            logger.info(
                f"Handshake complete: {len(self._metadata)} stars loaded, {self._metadata.keys()}, {len(self._handlers)} handlers registered."
            )
            logger.info(f"Registered {len(self._handlers)} handlers")

            return self._metadata
        raise RuntimeError("Handshake failed: Invalid response from plugin")

    def _create_handler_proxy(self, handler_full_name: str):
        """Create a proxy function that calls the handler via RPC.

        Args:
            handler_full_name: The full name of the handler

        Returns:
            An async function that proxies calls to the remote handler.
            The function may return a direct result or an async generator for streaming.
        """

        async def handler_proxy(event: AstrMessageEvent, **kwargs):
            """Proxy function for remote handler invocation.

            Returns either a direct result or an async generator for streaming handlers.
            """
            request_id = self._rpc_helper._generate_request_id()
            request = CallHandlerRequest(
                jsonrpc="2.0",
                id=request_id,
                method="call_handler",
                params=CallHandlerRequest.Params(
                    handler_full_name=handler_full_name,
                    event=AstrMessageEventModel.from_event(event),
                    args=kwargs,
                ),
            )
            queue = await self._rpc_helper.call_rpc_streaming(self._client, request)

            try:
                while True:
                    item = await asyncio.wait_for(queue.get(), timeout=30.0)
                    if isinstance(item, dict) and item.get("_stream_end"):
                        break
                    if isinstance(item, dict) and item.get("_error"):
                        raise RuntimeError(item.get("message", "Unknown error"))
                    yield self._deserialize_result(item)

            except asyncio.TimeoutError:
                raise RuntimeError(f"RPC call to {handler_full_name} timed out")

        return handler_proxy

    def _deserialize_result(self, result: Any) -> Any:
        """Deserialize result from JSON-RPC response.

        Args:
            result: The result from the plugin

        Returns:
            Deserialized result object
        """
        # For now, return as-is
        # In practice, we might want to reconstruct MessageEventResult etc.
        return result

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
