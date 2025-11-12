import asyncio
from .jsonrpc import (
    JSONRPCMessage,
    JSONRPCSuccessResponse,
    JSONRPCErrorResponse,
)
from .transport import JSONRPCTransport


class RPCRequestHelper:
    """Manages RPC communication state and pending requests."""

    def __init__(self):
        self._request_id_counter = 0
        self.pending_requests: dict[str, asyncio.Future[JSONRPCMessage]] = {}

    def _generate_request_id(self) -> str:
        self._request_id_counter += 1
        return str(self._request_id_counter)

    async def call_rpc(
        self, transport_impl: JSONRPCTransport, message: JSONRPCMessage
    ) -> JSONRPCMessage | None:
        """Send RPC request and wait for response."""
        if message.id is not None:
            self.pending_requests[message.id] = asyncio.get_event_loop().create_future()
        await transport_impl.send_message(message)
        if message.id is not None:
            return await self.pending_requests[message.id]

    def resolve_pending_request(
        self, message: JSONRPCSuccessResponse | JSONRPCErrorResponse
    ):
        """Resolve a pending request with the response."""
        if message.id in self.pending_requests:
            future = self.pending_requests.pop(message.id)
            if not future.done():
                future.set_result(message)
