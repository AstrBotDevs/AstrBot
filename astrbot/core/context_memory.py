from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from astrbot.core.config.default import CONTEXT_MEMORY_DEFAULTS
from astrbot.core.context_memory_backends import (
    ContextMemoryEvolutionBackend,
    ContextMemoryMigrationAdapter,
    VectorLongTermMemoryRetriever,
    get_context_memory_evolution_backend,
    get_context_memory_migration_adapter,
    set_context_memory_evolution_backend,
    set_context_memory_migration_adapter,
)
from astrbot.core.utils.config_normalization import to_bool, to_int


def _clone_context_memory_defaults() -> dict[str, Any]:
    defaults = dict(CONTEXT_MEMORY_DEFAULTS)
    pinned = defaults.get("pinned_memories")
    defaults["pinned_memories"] = list(pinned) if isinstance(pinned, list) else []
    return defaults


DEFAULT_CONTEXT_MEMORY_SETTINGS: dict[str, Any] = _clone_context_memory_defaults()

__all__ = [
    "ContextMemoryConfig",
    "DEFAULT_CONTEXT_MEMORY_SETTINGS",
    "normalize_context_memory_settings",
    "load_context_memory_config",
    "ensure_context_memory_settings",
    "build_pinned_memory_system_block",
    "VectorLongTermMemoryRetriever",
    "ContextMemoryEvolutionBackend",
    "ContextMemoryMigrationAdapter",
    "set_context_memory_evolution_backend",
    "get_context_memory_evolution_backend",
    "set_context_memory_migration_adapter",
    "get_context_memory_migration_adapter",
]


@dataclass(frozen=True)
class ContextMemoryConfig:
    enabled: bool = False
    inject_pinned_memory: bool = True
    pinned_memories: list[str] = field(default_factory=list)
    pinned_max_items: int = 8
    pinned_max_chars_per_item: int = 400
    retrieval_enabled: bool = False
    retrieval_backend: str = ""
    retrieval_provider_id: str = ""
    retrieval_top_k: int = 5


def normalize_context_memory_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(DEFAULT_CONTEXT_MEMORY_SETTINGS)
    # Always initialize pinned_memories explicitly to avoid sharing mutable defaults.
    normalized["pinned_memories"] = []
    if not isinstance(raw, dict):
        return normalized

    normalized["enabled"] = to_bool(
        raw.get("enabled"),
        bool(DEFAULT_CONTEXT_MEMORY_SETTINGS["enabled"]),
    )
    normalized["inject_pinned_memory"] = to_bool(
        raw.get("inject_pinned_memory"),
        bool(DEFAULT_CONTEXT_MEMORY_SETTINGS["inject_pinned_memory"]),
    )
    normalized["pinned_max_items"] = to_int(
        raw.get("pinned_max_items"),
        int(DEFAULT_CONTEXT_MEMORY_SETTINGS["pinned_max_items"]),
        1,
    )
    normalized["pinned_max_chars_per_item"] = to_int(
        raw.get("pinned_max_chars_per_item"),
        int(DEFAULT_CONTEXT_MEMORY_SETTINGS["pinned_max_chars_per_item"]),
        1,
    )
    normalized["retrieval_enabled"] = to_bool(
        raw.get("retrieval_enabled"),
        bool(DEFAULT_CONTEXT_MEMORY_SETTINGS["retrieval_enabled"]),
    )
    normalized["retrieval_backend"] = str(raw.get("retrieval_backend", "") or "").strip()
    normalized["retrieval_provider_id"] = str(
        raw.get("retrieval_provider_id", "") or ""
    ).strip()
    normalized["retrieval_top_k"] = to_int(
        raw.get("retrieval_top_k"),
        int(DEFAULT_CONTEXT_MEMORY_SETTINGS["retrieval_top_k"]),
        1,
    )

    pinned_max_items = int(normalized["pinned_max_items"])
    pinned_max_chars = int(normalized["pinned_max_chars_per_item"])
    pinned_raw = raw.get("pinned_memories", [])
    pinned_memories: list[str] = []
    if isinstance(pinned_raw, list):
        for item in pinned_raw:
            text = str(item or "").strip()
            if not text:
                continue
            if len(text) > pinned_max_chars:
                text = text[:pinned_max_chars]
            pinned_memories.append(text)
            if len(pinned_memories) >= pinned_max_items:
                break
    normalized["pinned_memories"] = pinned_memories

    return normalized


def load_context_memory_config(provider_settings: dict[str, Any] | None) -> ContextMemoryConfig:
    raw = None
    if isinstance(provider_settings, dict):
        raw = provider_settings.get("context_memory")
    normalized = normalize_context_memory_settings(raw if isinstance(raw, dict) else None)
    return ContextMemoryConfig(
        enabled=bool(normalized["enabled"]),
        inject_pinned_memory=bool(normalized["inject_pinned_memory"]),
        pinned_memories=list(normalized["pinned_memories"]),
        pinned_max_items=int(normalized["pinned_max_items"]),
        pinned_max_chars_per_item=int(normalized["pinned_max_chars_per_item"]),
        retrieval_enabled=bool(normalized["retrieval_enabled"]),
        retrieval_backend=str(normalized["retrieval_backend"]),
        retrieval_provider_id=str(normalized["retrieval_provider_id"]),
        retrieval_top_k=int(normalized["retrieval_top_k"]),
    )


def ensure_context_memory_settings(provider_settings: dict[str, Any]) -> dict[str, Any]:
    """Normalize and persist context_memory subtree in provider_settings."""
    normalized = normalize_context_memory_settings(provider_settings.get("context_memory"))
    provider_settings["context_memory"] = normalized
    return normalized


def build_pinned_memory_system_block(config: ContextMemoryConfig) -> str:
    """Build system-prompt block for manually pinned top-level memories."""
    if not config.enabled or not config.inject_pinned_memory:
        return ""
    if not config.pinned_memories:
        return ""

    lines = [
        "<top_level_memory>",
        "The following high-priority memory is manually configured and should be respected when relevant:",
    ]
    for idx, memory in enumerate(config.pinned_memories, start=1):
        lines.append(f"{idx}. {memory}")
    lines.append("</top_level_memory>")
    return "\n".join(lines)
