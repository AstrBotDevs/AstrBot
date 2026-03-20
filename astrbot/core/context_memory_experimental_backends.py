from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ContextMemoryBackend(Protocol):
    """Experimental unified protocol for context-memory evolution + migration."""

    async def evolve(
        self,
        *,
        unified_msg_origin: str,
        turns: list[str],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Evolve short-term conversation turns into durable memory artifacts."""
        ...

    async def retrieve(
        self,
        *,
        unified_msg_origin: str,
        query: str,
        top_k: int,
    ) -> list[str]:
        """Retrieve evolved memory snippets for prompt assembly."""
        ...

    async def export_session(
        self,
        *,
        unified_msg_origin: str,
    ) -> dict[str, Any]:
        """Export memory payload for migration or backup."""
        ...

    async def import_session(
        self,
        *,
        unified_msg_origin: str,
        payload: dict[str, Any],
    ) -> None:
        """Import migrated memory payload into target backend."""
        ...


__all__ = [
    "ContextMemoryBackend",
]
