from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

DEFAULT_CONTEXT_MEMORY_SETTINGS: dict[str, Any] = {
    # Global switch for context-memory related features.
    "enabled": False,
    # Manually maintained top-level memories injected into system prompt.
    "inject_pinned_memory": True,
    "pinned_memories": [],
    "pinned_max_items": 8,
    "pinned_max_chars_per_item": 400,
    # Retrieval enhancement is intentionally reserved for future PRs.
    "retrieval_enabled": False,
    "retrieval_backend": "",
    "retrieval_provider_id": "",
    "retrieval_top_k": 5,
}


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


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    return default


def _to_int(value: Any, default: int, min_value: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = default
    return max(parsed, min_value)


def normalize_context_memory_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    normalized = dict(DEFAULT_CONTEXT_MEMORY_SETTINGS)
    if not isinstance(raw, dict):
        return normalized

    normalized["enabled"] = _to_bool(
        raw.get("enabled"),
        bool(DEFAULT_CONTEXT_MEMORY_SETTINGS["enabled"]),
    )
    normalized["inject_pinned_memory"] = _to_bool(
        raw.get("inject_pinned_memory"),
        bool(DEFAULT_CONTEXT_MEMORY_SETTINGS["inject_pinned_memory"]),
    )
    normalized["pinned_max_items"] = _to_int(
        raw.get("pinned_max_items"),
        int(DEFAULT_CONTEXT_MEMORY_SETTINGS["pinned_max_items"]),
        1,
    )
    normalized["pinned_max_chars_per_item"] = _to_int(
        raw.get("pinned_max_chars_per_item"),
        int(DEFAULT_CONTEXT_MEMORY_SETTINGS["pinned_max_chars_per_item"]),
        1,
    )
    normalized["retrieval_enabled"] = _to_bool(
        raw.get("retrieval_enabled"),
        bool(DEFAULT_CONTEXT_MEMORY_SETTINGS["retrieval_enabled"]),
    )
    normalized["retrieval_backend"] = str(raw.get("retrieval_backend", "") or "").strip()
    normalized["retrieval_provider_id"] = str(
        raw.get("retrieval_provider_id", "") or ""
    ).strip()
    normalized["retrieval_top_k"] = _to_int(
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
