import asyncio
import inspect
from typing import Any, AsyncGenerator
from loguru import logger

from ...api.event.astr_message_event import AstrMessageEvent, AstrMessageEventModel
from ...api.star.star import StarMetadata
from ..rpc.client import JSONRPCClient
from ..rpc.request_helper import RPCRequestHelper
from ..rpc.jsonrpc import (
    JSONRPCSuccessResponse,
    JSONRPCRequest,
    JSONRPCErrorResponse,
    JSONRPCErrorData,
)
from ..types import CallHandlerRequest, HandshakeRequest
from .registry import StarHandlerMetadata, EventType


class HandlerProxyFactory:
    """Creates proxy functions for remote handler invocation."""

    def __init__(self, client: JSONRPCClient, rpc_helper: RPCRequestHelper):
        """Initialize the handler proxy factory.

        Args:
            client: JSON-RPC client for communication
            rpc_helper: RPC request helper for making RPC calls
        """
        self._client = client
        self._rpc_helper = rpc_helper

    def create_handler_proxy(self, handler_full_name: str):
        """Create a proxy function that calls the handler via RPC.

        Args:
            handler_full_name: The full name of the handler

        Returns:
            An async generator function that proxies calls to the remote handler.
        """

        async def handler_proxy(
            event: AstrMessageEvent, **kwargs
        ) -> AsyncGenerator[Any, None]:
            """Proxy function for remote handler invocation.

            Yields results from the remote handler via streaming.
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

    def setup_handlers(self, handlers: list[StarHandlerMetadata]) -> None:
        """Set up handler proxies for all handlers.

        Args:
            handlers: List of handler metadata to set up
        """
        for handler in handlers:
            handler.handler = self.create_handler_proxy(handler.handler_full_name)
        logger.info(f"Set up {len(handlers)} handler proxies")

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


class ClientHandshakeHandler:
    """Handles the handshake protocol to retrieve plugin metadata."""

    def __init__(self, rpc_helper: RPCRequestHelper):
        """Initialize the handshake handler.

        Args:
            rpc_helper: RPC request helper for making RPC calls
        """
        self._rpc_helper = rpc_helper

    async def perform_handshake(
        self, client: JSONRPCClient
    ) -> tuple[dict[str, StarMetadata], list[StarHandlerMetadata]]:
        """Perform handshake to retrieve plugin metadata.

        Args:
            client: JSON-RPC client for communication

        Returns:
            Tuple of (metadata dict, handlers list)

        Raises:
            RuntimeError: If handshake fails
        """
        logger.info("Performing handshake with plugin...")

        response = await self._rpc_helper.call_rpc(
            client,
            HandshakeRequest(
                jsonrpc="2.0",
                id=self._rpc_helper._generate_request_id(),
                method="handshake",
            ),
        )

        if not isinstance(response, JSONRPCSuccessResponse):
            raise RuntimeError("Handshake failed: Invalid response from plugin")

        result = response.result

        if not isinstance(result, dict):
            raise RuntimeError("Handshake failed: Invalid response from plugin")

        metadata_dict: dict[str, StarMetadata] = {}
        handlers_list: list[StarHandlerMetadata] = []

        # Placeholder handler that will be replaced later
        def _placeholder_handler(*args, **kwargs):
            raise NotImplementedError("Handler proxy not set up yet")

        # Parse metadata
        for star_name, star_info in result.items():
            handlers_data = star_info.pop("handlers", None)
            metadata = StarMetadata(**star_info)
            metadata_dict[star_name] = metadata

            # Parse handlers
            if handlers_data:
                for handler_data in handlers_data:
                    handler_meta = StarHandlerMetadata(
                        event_type=EventType(handler_data["event_type"]),
                        handler_full_name=handler_data["handler_full_name"],
                        handler_name=handler_data["handler_name"],
                        handler_module_path=handler_data["handler_module_path"],
                        handler=_placeholder_handler,  # Will be replaced by HandlerProxyFactory
                        event_filters=[],
                        desc=handler_data.get("desc", ""),
                        extras_configs=handler_data.get("extras_configs", {}),
                    )
                    handlers_list.append(handler_meta)

        logger.info(
            f"Handshake complete: {len(metadata_dict)} stars loaded, "
            f"{metadata_dict.keys()}, {len(handlers_list)} handlers registered."
        )

        return metadata_dict, handlers_list


class PluginRequestHandler:
    """Handles JSON-RPC requests from plugins calling core methods."""

    def __init__(self, context: Any):
        """Initialize the plugin request handler.

        Args:
            context: Context instance for managing managers and their functions
        """
        self._context = context

    async def handle_request(
        self, request: JSONRPCRequest, client: JSONRPCClient
    ) -> None:
        """Handle a JSON-RPC request from the plugin.

        Args:
            request: The JSON-RPC request from the plugin
            client: The client to send response back
        """
        result: Any = None
        try:
            method = request.method
            params = request.params or {}

            if method == "call_context_function":
                result = await self._handle_context_function_call(params)
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
            await client.send_message(response)

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
            await client.send_message(error_response)

    async def _handle_context_function_call(self, params: dict) -> Any:
        """Handle call_context_function requests.

        Args:
            params: Request parameters containing function name and args

        Returns:
            Result from the function call

        Raises:
            ValueError: If function is not found
        """
        func_full_name = params.get("name", "")
        args = params.get("args", {})

        logger.debug(
            f"Plugin called call_context_function: {func_full_name} with args: {args}"
        )

        # Get the registered function from context
        func = self._context.get_registered_function(func_full_name)
        if func is None:
            raise ValueError(f"Function not found: {func_full_name}")

        # Call the function
        if inspect.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = func(**args)

        logger.debug(f"call_context_function result: {result}")
        return result
