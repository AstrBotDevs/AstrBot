from __future__ import annotations

from astrbot.core.config.default import CONTEXT_MEMORY_DEFAULTS
from astrbot.core.context_memory import (
    ContextMemoryConfig,
    normalize_context_memory_settings,
)
from astrbot.core.context_memory_experimental_backends import (
    configure_context_memory_backends,
    get_experimental_context_memory_backends,
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

    configure_context_memory_backends(
        evolution_backend=backend,  # type: ignore[arg-type]
        migration_adapter=adapter,  # type: ignore[arg-type]
    )

    backends = get_experimental_context_memory_backends()
    assert backends.evolution_backend is backend
    assert backends.migration_adapter is adapter

    configure_context_memory_backends(evolution_backend=None, migration_adapter=None)
    assert get_experimental_context_memory_backends().evolution_backend is None
    assert get_experimental_context_memory_backends().migration_adapter is None


def test_context_memory_defaults_follow_single_source() -> None:
    cfg = ContextMemoryConfig.from_raw(None)

    assert cfg.enabled == CONTEXT_MEMORY_DEFAULTS["enabled"]
    assert cfg.inject_pinned_memory == CONTEXT_MEMORY_DEFAULTS["inject_pinned_memory"]
    assert cfg.pinned_max_items == CONTEXT_MEMORY_DEFAULTS["pinned_max_items"]
    assert (
        cfg.pinned_max_chars_per_item
        == CONTEXT_MEMORY_DEFAULTS["pinned_max_chars_per_item"]
    )
    assert cfg.retrieval_enabled == CONTEXT_MEMORY_DEFAULTS["retrieval_enabled"]
    assert cfg.retrieval_backend == CONTEXT_MEMORY_DEFAULTS["retrieval_backend"]
    assert cfg.retrieval_provider_id == CONTEXT_MEMORY_DEFAULTS["retrieval_provider_id"]
    assert cfg.retrieval_top_k == CONTEXT_MEMORY_DEFAULTS["retrieval_top_k"]
    assert cfg.pinned_memories == []
