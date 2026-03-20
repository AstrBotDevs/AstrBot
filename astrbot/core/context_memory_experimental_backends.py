from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorLongTermMemoryRetriever(Protocol):
    """Experimental protocol for future vector-DB long-term memory retrieval."""

    async def retrieve(
        self,
        *,
        unified_msg_origin: str,
        query: str,
        top_k: int,
    ) -> list[str]:
        """Return ranked memory snippets for prompt assembly."""
        ...


@runtime_checkable
class ContextMemoryEvolutionBackend(Protocol):
    """Experimental protocol for MemEvolve-style memory evolution integration."""

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


@runtime_checkable
class ContextMemoryMigrationAdapter(Protocol):
    """Experimental protocol for future context-memory schema/store migration."""

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


@dataclass
class ExperimentalContextMemoryBackends:
    """Container for optional experimental backends."""

    evolution_backend: ContextMemoryEvolutionBackend | None = None
    migration_adapter: ContextMemoryMigrationAdapter | None = None


def make_experimental_context_memory_backends(
    *,
    evolution_backend: ContextMemoryEvolutionBackend | None = None,
    migration_adapter: ContextMemoryMigrationAdapter | None = None,
) -> ExperimentalContextMemoryBackends:
    """Create an experimental backend bundle without module-level mutable state."""
    return ExperimentalContextMemoryBackends(
        evolution_backend=evolution_backend,
        migration_adapter=migration_adapter,
    )

__all__ = [
    "VectorLongTermMemoryRetriever",
    "ContextMemoryEvolutionBackend",
    "ContextMemoryMigrationAdapter",
    "ExperimentalContextMemoryBackends",
    "make_experimental_context_memory_backends",
]
