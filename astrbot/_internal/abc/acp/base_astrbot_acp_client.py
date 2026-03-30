"""
ACP (AstrBot Communication Protocol) client.

Transport: TCP | Unix Socket
Messages:  JSON with Content-Length header
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAstrbotAcpClient(ABC):
    """
    ACP client: connects to ACP servers via TCP or Unix socket.

    Subclass must implement:
    - connect() -> None
    - connect_to_server(host, port) -> None
    - connect_to_unix_socket(path) -> None
    - call_tool(server, tool, args) -> Any
    - send_notification(method, params) -> None
    - shutdown() -> None
    """

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def connect_to_server(self, host: str, port: int) -> None:
        """Connect via TCP."""
        ...

    @abstractmethod
    async def connect_to_unix_socket(self, socket_path: str) -> None:
        """Connect via Unix domain socket."""
        ...

    @abstractmethod
    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call tool on server, return result."""
        ...

    @abstractmethod
    async def send_notification(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        """Send one-way notification."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Close connection, cancel pending requests."""
        ...
