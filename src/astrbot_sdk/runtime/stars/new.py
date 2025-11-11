from __future__ import annotations

import asyncio
import os
from typing import Any

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
from .virtual import VirtualStar


class NewStar(VirtualStar):
    """NewStar implementation for isolated plugin runtime.

    NewStar runs plugins in separate processes and communicates via JSON-RPC.
    This provides better isolation, security, and compatibility.
    """

    def __init__(
        self,
        client: JSONRPCClient,
        context: Any = None,
    ) -> None:
        """Initialize a NewStar instance.

        Args:
            client: JSON-RPC client for communication
            context: Context instance for managing managers and their functions
        """
        # Import here to avoid circular dependency
        from ..api.context import Context

        # Initialize context
        if context is None:
            context = Context.default_context()

        super().__init__(context)

        self._client = client
        self._metadata: dict[str, StarMetadata] = {}
        self._handlers: list[StarHandlerMetadata] = []
        self._request_id_counter = 0
        self._pending_requests: dict[
            str, asyncio.Future[dict] | asyncio.Queue[dict]
        ] = {}
        self._active = False

        # Set up message handler
        self._client.set_message_handler(self._handle_message)

    def _generate_request_id(self) -> str:
        """Generate a unique request ID."""
        self._request_id_counter += 1
        return f"req-{self._request_id_counter}"

    async def _handle_message(self, message: JSONRPCMessage) -> None:
        """Handle incoming JSON-RPC messages from the plugin.

        Args:
            message: The received JSON-RPC message
        """
        if isinstance(message, JSONRPCSuccessResponse) or isinstance(
            message,
            JSONRPCErrorResponse,
        ):
            # This is a response to one of our requests
            request_id = message.id
            if request_id and request_id in self._pending_requests:
                pending = self._pending_requests[request_id]

                # Check if it's a Future or Queue
                if isinstance(pending, asyncio.Future):
                    self._pending_requests.pop(request_id)
                    if isinstance(message, JSONRPCSuccessResponse):
                        if not pending.done():
                            pending.set_result(message.result)
                    else:
                        if not pending.done():
                            pending.set_exception(
                                RuntimeError(
                                    f"RPC Error {message.error.code}: {message.error.message}",
                                ),
                            )
                elif isinstance(pending, asyncio.Queue):
                    if isinstance(message, JSONRPCSuccessResponse):
                        logger.debug(
                            f"Streaming handler {request_id} completed successfully"
                        )
                    else:
                        logger.error(
                            f"Streaming handler {request_id} failed: {message.error.message}"
                        )
                        # Put error marker in queue
                        await pending.put(
                            {"_error": True, "message": message.error.message}
                        )
            else:
                logger.warning(
                    f"Received response for unknown request ID: {request_id}"
                )

        elif isinstance(message, JSONRPCRequest):
            # Handle notifications from plugin (streaming events or method calls)
            if message.method in [
                "handler_stream_start",
                "handler_stream_update",
                "handler_stream_end",
            ]:
                await self._handle_stream_notification(message)
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

    async def _handle_stream_notification(self, notification: JSONRPCRequest) -> None:
        """Handle streaming notifications from the plugin.

        Args:
            notification: The streaming notification (handler_stream_start/update/end)
        """
        params = notification.params
        request_id = params.get("id")

        if not request_id or request_id not in self._pending_requests:
            logger.warning(
                f"Received stream notification for unknown request ID: {request_id}"
            )
            return

        pending = self._pending_requests.get(request_id)
        if not isinstance(pending, asyncio.Queue):
            logger.warning(f"Request {request_id} is not a streaming request")
            return

        if notification.method == "handler_stream_start":
            logger.debug(
                f"Stream started for handler {params.get('handler_full_name')}"
            )
            # Optionally put a start marker in the queue
            # await pending.put({"_stream_start": True})

        elif notification.method == "handler_stream_update":
            # Put the streamed data into the queue
            data = params.get("data")
            logger.debug(f"Stream update for request {request_id}: {data}")
            if data is not None:
                await pending.put(data)

        elif notification.method == "handler_stream_end":
            # Mark the end of the stream
            logger.debug(f"Stream ended for handler {params.get('handler_full_name')}")
            # Put a sentinel value to indicate stream end
            await pending.put({"_stream_end": True})
            # Clean up the pending request after a short delay to allow queue to be processed
            asyncio.create_task(self._cleanup_stream_request(request_id))

    async def _cleanup_stream_request(
        self, request_id: str, delay: float = 1.0
    ) -> None:
        """Clean up a streaming request after a delay.

        Args:
            request_id: The request ID to clean up
            delay: Delay before cleanup in seconds
        """
        await asyncio.sleep(delay)
        if request_id in self._pending_requests:
            self._pending_requests.pop(request_id)
            logger.debug(f"Cleaned up streaming request {request_id}")

    async def _call_rpc(self, request: JSONRPCRequest) -> dict:
        """Call a JSON-RPC method on the plugin and wait for response.

        Args:
            request: The JSON-RPC request to send

        Returns:
            The result from the plugin

        Raises:
            RuntimeError: If the RPC call fails
        """
        # Create a future to wait for the response
        future: asyncio.Future[dict] = asyncio.Future()

        if request.id is not None:
            self._pending_requests[request.id] = future

        try:
            await self._client.send_message(request)
            # Wait for response with timeout
            result = await asyncio.wait_for(future, timeout=30.0)
            return result
        except asyncio.TimeoutError:
            if request.id is not None:
                self._pending_requests.pop(request.id, None)
            raise RuntimeError(f"RPC call to {request.method} timed out")

    async def _call_rpc_streaming(
        self,
        request: JSONRPCRequest,
    ) -> asyncio.Queue[dict]:
        """Call a JSON-RPC method on the plugin that returns a stream of results.

        Args:
            request: The JSON-RPC request to send
        Returns:
            An asyncio.Queue that will receive streamed results
        """
        # Create a queue to receive streamed results
        queue: asyncio.Queue[dict] = asyncio.Queue()

        if request.id is not None:
            self._pending_requests[request.id] = queue

        try:
            await self._client.send_message(request)
            return queue
        except Exception as e:
            if request.id is not None:
                self._pending_requests.pop(request.id, None)
            raise RuntimeError(f"RPC streaming call to {request.method} failed: {e}")

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

        result = await self._call_rpc(
            HandshakeRequest(
                jsonrpc="2.0", id=self._generate_request_id(), method="handshake"
            )
        )

        print(result, result.__class__)

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
            request_id = self._generate_request_id()
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

            # Create a queue for potential streaming response
            queue: asyncio.Queue[dict] = asyncio.Queue()
            self._pending_requests[request_id] = queue

            try:
                # Send the request
                await self._client.send_message(request)

                # Wait for the first response or stream notification
                try:
                    # Set a timeout for the first response
                    first_response = await asyncio.wait_for(queue.get(), timeout=30.0)

                    # Check what type of response we got
                    if isinstance(first_response, dict):
                        # Check for stream end (empty stream case)
                        if first_response.get("_stream_end"):
                            # Empty stream, return None
                            self._pending_requests.pop(request_id, None)
                            return None

                        # Check for error
                        if first_response.get("_error"):
                            self._pending_requests.pop(request_id, None)
                            raise RuntimeError(
                                first_response.get("message", "Unknown error")
                            )

                        # Check if this is streaming data or a final result
                        # We peek at the queue to see if more data is coming
                        # If the queue is empty after a short wait, it's a final result
                        try:
                            # Try to get another item with a very short timeout
                            second_response = await asyncio.wait_for(
                                queue.get(), timeout=0.1
                            )
                            # We got a second item, so this is streaming
                            # Create and return the generator
                            return self._create_stream_generator(
                                queue, first_response, second_response
                            )
                        except asyncio.TimeoutError:
                            # No second item, this might be a final result
                            # But we should check if stream_end arrives shortly
                            try:
                                stream_end = await asyncio.wait_for(
                                    queue.get(), timeout=0.5
                                )
                                if isinstance(stream_end, dict) and stream_end.get(
                                    "_stream_end"
                                ):
                                    # This was a single-item stream
                                    self._pending_requests.pop(request_id, None)
                                    return self._deserialize_result(first_response)
                                else:
                                    # More data arrived, it's streaming
                                    return self._create_stream_generator(
                                        queue, first_response, stream_end
                                    )
                            except asyncio.TimeoutError:
                                # Truly a final result (non-streaming)
                                self._pending_requests.pop(request_id, None)
                                return self._deserialize_result(first_response)
                    else:
                        # Unexpected response type
                        self._pending_requests.pop(request_id, None)
                        return self._deserialize_result(first_response)

                except asyncio.TimeoutError:
                    # Timeout waiting for response
                    self._pending_requests.pop(request_id, None)
                    raise RuntimeError(f"RPC call to {handler_full_name} timed out")

            except Exception:
                # Clean up on error
                self._pending_requests.pop(request_id, None)
                raise

        return handler_proxy

    async def _create_stream_generator(
        self, queue: asyncio.Queue[dict], *initial_items: dict
    ):
        """Create an async generator that yields items from the stream queue.

        Args:
            queue: The queue containing stream items
            initial_items: Initial items that were already retrieved from the queue

        Yields:
            Items from the stream
        """
        # Yield any initial items
        for item in initial_items:
            if not (isinstance(item, dict) and item.get("_stream_end")):
                yield self._deserialize_result(item)

        # Continue yielding items from the queue
        while True:
            try:
                item = await queue.get()

                # Check for end marker
                if isinstance(item, dict) and item.get("_stream_end"):
                    break

                # Check for error marker
                if isinstance(item, dict) and item.get("_error"):
                    raise RuntimeError(item.get("message", "Stream error"))

                # Yield the item
                yield self._deserialize_result(item)

            except asyncio.CancelledError:
                # Generator was cancelled, stop iteration
                logger.debug("Stream generator cancelled")
                break

    def _deserialize_result(self, result: Any) -> Any:
        """Deserialize result from JSON-RPC response.

        Args:
            result: The result from the plugin

        Returns:
            Deserialized result object
        """
        # For now, return as-is
        # In practice, you might want to reconstruct MessageEventResult etc.
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
    ) -> None:
        """Call a specific handler in the plugin.

        Args:
            handler: The handler metadata
            event: The message event
            *args: Additional positional arguments
            **kwargs: Additional keyword arguments

        Returns:
            Result from the handler
        """
        logger.debug(f"Calling handler: {handler.handler_name}")

        # Call the handler proxy
        result = await handler.handler(event, *args, **kwargs)  # type: ignore
        return result

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
