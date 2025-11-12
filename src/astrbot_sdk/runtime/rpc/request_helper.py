import asyncio
from typing import Any
from loguru import logger
from .jsonrpc import (
    JSONRPCMessage,
    JSONRPCRequest,
    JSONRPCSuccessResponse,
    JSONRPCErrorResponse,
)
from .transport import JSONRPCTransport
from ..types import (
    HandlerStreamStartNotification,
    HandlerStreamUpdateNotification,
    HandlerStreamEndNotification,
)


class RPCRequestHelper:
    """Manages RPC communication state and pending requests.

    Supports both single-response and streaming (multi-response) RPC patterns:
    - Single response: Uses asyncio.Future
    - Streaming: Uses asyncio.Queue for multiple responses
    """

    def __init__(self):
        self._request_id_counter = 0
        self.pending_requests: dict[
            str, asyncio.Future[JSONRPCMessage] | asyncio.Queue[Any]
        ] = {}

    def _generate_request_id(self) -> str:
        """Generate a unique request ID."""
        self._request_id_counter += 1
        return str(self._request_id_counter)

    async def call_rpc(
        self, transport_impl: JSONRPCTransport, message: JSONRPCMessage
    ) -> JSONRPCMessage | None:
        """Send RPC request and wait for a single response.

        Args:
            transport_impl: The transport to send the message through
            message: The JSON-RPC request message

        Returns:
            The JSON-RPC response message, or None if no response expected
        """
        if message.id is None:
            await transport_impl.send_message(message)
            return None

        future: asyncio.Future[JSONRPCMessage] = (
            asyncio.get_event_loop().create_future()
        )
        self.pending_requests[message.id] = future
        await transport_impl.send_message(message)
        result = await future
        return result

    async def call_rpc_streaming(
        self, transport_impl: JSONRPCTransport, message: JSONRPCMessage
    ) -> asyncio.Queue[Any]:
        """Send RPC request and expect multiple streaming responses.

        The responses will be delivered via notifications with methods:
        - handler_stream_start: Stream started
        - handler_stream_update: New data available
        - handler_stream_end: Stream completed

        Args:
            transport_impl: The transport to send the message through
            message: The JSON-RPC request message

        Returns:
            An asyncio.Queue that will receive streamed results
        """
        if message.id is None:
            raise ValueError("Streaming RPC calls require a request ID")

        queue: asyncio.Queue[Any] = asyncio.Queue()
        self.pending_requests[message.id] = queue

        await transport_impl.send_message(message)
        return queue

    def resolve_pending_request(
        self, message: JSONRPCSuccessResponse | JSONRPCErrorResponse
    ):
        """Resolve a pending request with a response.

        For single-response requests (Future), sets the result/exception.
        For streaming requests (Queue), logs completion/error but queue is managed separately.

        Args:
            message: The JSON-RPC response message
        """
        if message.id not in self.pending_requests:
            logger.warning(f"Received response for unknown request ID: {message.id}")
            return

        pending = self.pending_requests[message.id]

        if isinstance(pending, asyncio.Future):
            # Single response mode
            self.pending_requests.pop(message.id)
            if not pending.done():
                if isinstance(message, JSONRPCSuccessResponse):
                    pending.set_result(message)
                else:
                    pending.set_exception(
                        RuntimeError(
                            f"RPC Error {message.error.code}: {message.error.message}"
                        )
                    )
        elif isinstance(pending, asyncio.Queue):
            # Streaming mode - final response received
            if isinstance(message, JSONRPCSuccessResponse):
                logger.debug(f"Streaming request {message.id} completed successfully")
            else:
                logger.error(
                    f"Streaming request {message.id} failed: {message.error.message}"
                )
                # Put error marker in queue
                asyncio.create_task(
                    pending.put({"_error": True, "message": message.error.message})
                )

    async def handle_stream_notification(self, notification: JSONRPCRequest) -> None:
        """Handle incoming streaming notifications.

        Processes handler_stream_start/update/end notifications and updates
        the corresponding queue.

        Args:
            notification: The streaming notification message

        Raises:
            ValueError: If the notification method is not a valid stream notification
        """
        # Validate notification method
        if notification.method not in [
            "handler_stream_start",
            "handler_stream_update",
            "handler_stream_end",
        ]:
            raise ValueError(
                f"Invalid stream notification method: {notification.method}"
            )

        # Extract common parameters
        params = notification.params
        request_id = params.get("id")

        if not request_id or request_id not in self.pending_requests:
            logger.warning(
                f"Received stream notification for unknown request ID: {request_id}"
            )
            return

        pending = self.pending_requests.get(request_id)
        if not isinstance(pending, asyncio.Queue):
            logger.warning(f"Request {request_id} is not a streaming request")
            return

        if notification.method == "handler_stream_start":
            try:
                typed_notification = HandlerStreamStartNotification.model_validate(
                    notification.model_dump()
                )
                logger.debug(
                    f"Stream started for handler {typed_notification.params.handler_full_name}"
                )
            except Exception as e:
                logger.error(f"Invalid handler_stream_start notification: {e}")
            # Optionally put a start marker in the queue if needed
            # await pending.put({"_stream_start": True})

        elif notification.method == "handler_stream_update":
            try:
                typed_notification = HandlerStreamUpdateNotification.model_validate(
                    notification.model_dump()
                )
                # Put the streamed data into the queue
                data = typed_notification.params.data
                logger.debug(f"Stream update for request {request_id}: {data}")
                if data is not None:
                    await pending.put(data)
            except Exception as e:
                logger.error(f"Invalid handler_stream_update notification: {e}")

        elif notification.method == "handler_stream_end":
            try:
                typed_notification = HandlerStreamEndNotification.model_validate(
                    notification.model_dump()
                )
                logger.debug(
                    f"Stream ended for handler {typed_notification.params.handler_full_name}"
                )
                # Put a sentinel value to indicate stream end
                await pending.put({"_stream_end": True})
                # Clean up the pending request after a short delay
                asyncio.create_task(self._cleanup_stream_request(request_id))
            except Exception as e:
                logger.error(f"Invalid handler_stream_end notification: {e}")

    async def _cleanup_stream_request(
        self, request_id: str, delay: float = 1.0
    ) -> None:
        """Clean up a streaming request after a delay.

        Args:
            request_id: The request ID to clean up
            delay: Delay before cleanup in seconds
        """
        await asyncio.sleep(delay)
        if request_id in self.pending_requests:
            self.pending_requests.pop(request_id)
            logger.debug(f"Cleaned up streaming request {request_id}")
