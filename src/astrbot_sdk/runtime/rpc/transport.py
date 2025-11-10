from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Awaitable

from .jsonrpc import JSONRPCMessage

MessageHandler = Callable[[JSONRPCMessage], Awaitable[None]]


class JSONRPCTransport(ABC):
    """Base class for JSON-RPC transport layers."""

    def __init__(self) -> None:
        self._handler: MessageHandler | None = None
        self._running = False

    def set_message_handler(self, handler: MessageHandler) -> None:
        """Set the handler to be called when a message is received.

        Args:
            handler: Callback function that receives a JSONRPCMessage
        """
        self._message_handler = handler

    @abstractmethod
    async def start(self) -> None:
        """Start the transport layer."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the transport layer and cleanup resources."""
        pass

    @abstractmethod
    async def send_message(self, message: JSONRPCMessage) -> None:
        """Send a JSON-RPC message.

        Args:
            message: The JSON-RPC message to send
        """
        pass

    async def _handle_message(self, message: JSONRPCMessage) -> None:
        """Internal method to dispatch received messages to the handler."""
        if self._message_handler:
            await self._message_handler(message)
