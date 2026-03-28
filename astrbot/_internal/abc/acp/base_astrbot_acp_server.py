"""
ACP (AstrBot Communication Protocol) server.

Transport: TCP listening socket
Messages:  JSON with Content-Length header
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any


class BaseAstrbotAcpServer(ABC):
    """
    ACP server: listens for client connections, exposes tools.

    Subclass must implement:
    - start(host, port) -> None
    - register_tool(name, handler) -> None
    - register_notification_handler(name, handler) -> None
    - broadcast_notification(method, params) -> None
    - shutdown() -> None
    """

    @property
    @abstractmethod
    def running(self) -> bool:
        """True if server is accepting connections."""
        ...

    @abstractmethod
    async def start(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        """Bind and listen. Block until shutdown."""
        ...

    @abstractmethod
    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
    ) -> None:
        """Register async tool handler (receives params dict, returns result)."""
        ...

    @abstractmethod
    def register_notification_handler(
        self,
        name: str,
        handler: Callable[..., Any],
    ) -> None:
        """Register async notification handler (receives params dict)."""
        ...

    @abstractmethod
    async def broadcast_notification(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        """Send notification to all connected clients."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Stop accepting, close all client connections."""
        ...
