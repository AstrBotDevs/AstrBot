from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class VectorLongTermMemoryRetriever(Protocol):
    """Reserved protocol for future vector-DB long-term memory retrieval."""

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
    """Reserved protocol for MemEvolve-style memory evolution backend integration."""

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
    """Reserved protocol for future context-memory schema/store migration."""

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


_context_memory_evolution_backend: ContextMemoryEvolutionBackend | None = None
_context_memory_migration_adapter: ContextMemoryMigrationAdapter | None = None


def set_context_memory_evolution_backend(
    backend: ContextMemoryEvolutionBackend | None,
) -> None:
    global _context_memory_evolution_backend
    _context_memory_evolution_backend = backend


def get_context_memory_evolution_backend() -> ContextMemoryEvolutionBackend | None:
    return _context_memory_evolution_backend


def set_context_memory_migration_adapter(
    adapter: ContextMemoryMigrationAdapter | None,
) -> None:
    global _context_memory_migration_adapter
    _context_memory_migration_adapter = adapter


def get_context_memory_migration_adapter() -> ContextMemoryMigrationAdapter | None:
    return _context_memory_migration_adapter

