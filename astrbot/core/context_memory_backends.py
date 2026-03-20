"""Compatibility re-exports for experimental context-memory backend hooks.

The protocol definitions and global hook state live in
`context_memory_experimental_backends.py` to keep experimental extension points
explicitly isolated from stable context-memory config logic.
"""

from astrbot.core.context_memory_experimental_backends import (
    ContextMemoryEvolutionBackend,
    ContextMemoryMigrationAdapter,
    ExperimentalContextMemoryBackends,
    VectorLongTermMemoryRetriever,
    configure_context_memory_backends,
    get_context_memory_evolution_backend,
    get_context_memory_migration_adapter,
    get_experimental_context_memory_backends,
    set_context_memory_evolution_backend,
    set_context_memory_migration_adapter,
)

__all__ = [
    "VectorLongTermMemoryRetriever",
    "ContextMemoryEvolutionBackend",
    "ContextMemoryMigrationAdapter",
    "ExperimentalContextMemoryBackends",
    "configure_context_memory_backends",
    "get_experimental_context_memory_backends",
    "set_context_memory_evolution_backend",
    "get_context_memory_evolution_backend",
    "set_context_memory_migration_adapter",
    "get_context_memory_migration_adapter",
]
