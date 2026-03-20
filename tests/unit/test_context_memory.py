from __future__ import annotations

from astrbot.core.config.default import CONTEXT_MEMORY_DEFAULTS
from astrbot.core.context_memory import (
    DEFAULT_CONTEXT_MEMORY_SETTINGS,
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


def test_context_memory_defaults_follow_single_source() -> None:
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["enabled"] == CONTEXT_MEMORY_DEFAULTS["enabled"]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["inject_pinned_memory"] == CONTEXT_MEMORY_DEFAULTS[
        "inject_pinned_memory"
    ]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["pinned_max_items"] == CONTEXT_MEMORY_DEFAULTS[
        "pinned_max_items"
    ]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS[
        "pinned_max_chars_per_item"
    ] == CONTEXT_MEMORY_DEFAULTS["pinned_max_chars_per_item"]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["retrieval_enabled"] == CONTEXT_MEMORY_DEFAULTS[
        "retrieval_enabled"
    ]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["retrieval_backend"] == CONTEXT_MEMORY_DEFAULTS[
        "retrieval_backend"
    ]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS[
        "retrieval_provider_id"
    ] == CONTEXT_MEMORY_DEFAULTS["retrieval_provider_id"]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["retrieval_top_k"] == CONTEXT_MEMORY_DEFAULTS[
        "retrieval_top_k"
    ]
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["pinned_memories"] == []
    assert DEFAULT_CONTEXT_MEMORY_SETTINGS["pinned_memories"] is not CONTEXT_MEMORY_DEFAULTS[
        "pinned_memories"
    ]
