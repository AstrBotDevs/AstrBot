"""
ABP (AstrBot Protocol) client - in-process star communication.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseAstrbotAbpClient(ABC):
    """
    ABP client: in-process star (plugin) communication.

    Stars register themselves; client delegates calls to registered instances.

    Subclass must implement:
    - connect() -> None
    - register_star(name, instance) -> None
    - unregister_star(name) -> None
    - call_star_tool(star, tool, args) -> Any
    - shutdown() -> None
    """

    @property
    @abstractmethod
    def connected(self) -> bool: ...

    @abstractmethod
    async def connect(self) -> None:
        """Lightweight: just sets connected=True."""
        ...

    @abstractmethod
    def register_star(self, star_name: str, star_instance: Any) -> None:
        """Add star to internal registry."""
        ...

    @abstractmethod
    def unregister_star(self, star_name: str) -> None:
        """Remove star from registry (idempotent)."""
        ...

    @abstractmethod
    async def call_star_tool(
        self,
        star_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Delegate to star_instance.call_tool(tool_name, arguments)."""
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        """Set connected=False, cancel pending requests."""
        ...
