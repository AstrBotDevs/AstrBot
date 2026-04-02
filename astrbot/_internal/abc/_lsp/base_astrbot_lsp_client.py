"""
LSP (Language Server Protocol) client.

Transport: stdio subprocess
Messages:  JSON-RPC 2.0 with Content-Length header
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass


class LspMessage:
    """JSON-RPC 2.0 message."""

    jsonrpc: str = "2.0"
    id: int | str | None = None
    method: str | None = None
    params: dict[str, Any] | None = None
    result: Any = None
    error: dict[str, Any] | None = None


class LspRequest(LspMessage):
    """Outgoing request."""

    def __init__(self, method: str, params: dict[str, Any] | None = None) -> None:
        self.id = id(self)
        self.method = method
        self.params = params


class LspResponse(LspMessage):
    """Incoming response."""


class LspNotification(LspMessage):
    """Incoming notification (no id)."""


class BaseAstrbotLspClient(ABC):
    """
    LSP client: connects to LSP servers via stdio subprocess.

    Subclass must implement:
    - connect() -> None
    - connect_to_server(command, workspace_uri) -> None
    - send_request(method, params) -> dict
    - send_notification(method, params) -> None
    - shutdown() -> None
    """

    @property
    @abstractmethod
    def connected(self) -> bool:
        """True if connected to an LSP server."""
        ...

    @abstractmethod
    async def connect(self) -> None:
        self._connected = False
        ...

    @abstractmethod
    async def connect_to_server(
        self,
        command: list[str],
        workspace_uri: str,
    ) -> None:
        """
        Start LSP server subprocess and complete handshake.

        Steps:
        1. Spawn subprocess with stdin/stdout pipes
        2. Send initialize request
        3. Wait for response
        4. Send initialized notification
        """
        ...

    @abstractmethod
    async def send_request(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """
        Send JSON-RPC request and return result.

        Raises:
            RuntimeError: not connected
            Exception: server returned error
        """
        ...

    @abstractmethod
    async def send_notification(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> None:
        """
        Send JSON-RPC notification (no response expected).
        """
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Send shutdown, terminate subprocess, cleanup."""
        ...
