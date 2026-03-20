from __future__ import annotations

from astrbot.core.context_memory import (
    get_context_memory_evolution_backend,
    get_context_memory_migration_adapter,
    normalize_context_memory_settings,
    set_context_memory_evolution_backend,
    set_context_memory_migration_adapter,
)


def test_normalize_context_memory_settings_initializes_fresh_pinned_memories() -> None:
    first = normalize_context_memory_settings(None)
    second = normalize_context_memory_settings(None)

    first["pinned_memories"].append("A")

    assert first["pinned_memories"] == ["A"]
    assert second["pinned_memories"] == []


def test_context_memory_reserved_backend_registration() -> None:
    backend = object()
    adapter = object()

    set_context_memory_evolution_backend(backend)  # type: ignore[arg-type]
    set_context_memory_migration_adapter(adapter)  # type: ignore[arg-type]

    assert get_context_memory_evolution_backend() is backend
    assert get_context_memory_migration_adapter() is adapter

    set_context_memory_evolution_backend(None)
    set_context_memory_migration_adapter(None)

    assert get_context_memory_evolution_backend() is None
    assert get_context_memory_migration_adapter() is None
