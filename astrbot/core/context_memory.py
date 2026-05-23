from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from astrbot.core.config.default import CONTEXT_MEMORY_DEFAULTS
from astrbot.core.utils.config_normalization import to_bool, to_int

__all__ = [
    "ContextMemoryConfig",
    "normalize_context_memory_settings",
    "load_context_memory_config",
    "ensure_context_memory_settings",
    "build_pinned_memory_system_block",
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

    @classmethod
    def from_settings(
        cls,
        provider_settings: dict[str, Any] | None,
    ) -> ContextMemoryConfig:
        raw = None
        if isinstance(provider_settings, dict):
            raw = provider_settings.get("context_memory")
        return cls.from_raw(raw if isinstance(raw, dict) else None)

    @classmethod
    def from_raw(cls, raw: dict[str, Any] | None) -> ContextMemoryConfig:
        defaults = CONTEXT_MEMORY_DEFAULTS
        data = raw if isinstance(raw, dict) else {}

        enabled = to_bool(data.get("enabled"), bool(defaults["enabled"]))
        inject_pinned_memory = to_bool(
            data.get("inject_pinned_memory"),
            bool(defaults["inject_pinned_memory"]),
        )
        pinned_max_items = to_int(
            data.get("pinned_max_items"),
            int(defaults["pinned_max_items"]),
            1,
        )
        pinned_max_chars_per_item = to_int(
            data.get("pinned_max_chars_per_item"),
            int(defaults["pinned_max_chars_per_item"]),
            1,
        )
        retrieval_enabled = to_bool(
            data.get("retrieval_enabled"),
            bool(defaults["retrieval_enabled"]),
        )
        retrieval_backend = str(data.get("retrieval_backend", "") or "").strip()
        retrieval_provider_id = str(data.get("retrieval_provider_id", "") or "").strip()
        retrieval_top_k = to_int(
            data.get("retrieval_top_k"),
            int(defaults["retrieval_top_k"]),
            1,
        )

        pinned_raw = data.get("pinned_memories", [])
        pinned_memories: list[str] = []
        if isinstance(pinned_raw, list):
            for item in pinned_raw:
                text = str(item or "").strip()
                if not text:
                    continue
                if len(text) > pinned_max_chars_per_item:
                    text = text[:pinned_max_chars_per_item]
                pinned_memories.append(text)
                if len(pinned_memories) >= pinned_max_items:
                    break

        return cls(
            enabled=enabled,
            inject_pinned_memory=inject_pinned_memory,
            pinned_memories=pinned_memories,
            pinned_max_items=pinned_max_items,
            pinned_max_chars_per_item=pinned_max_chars_per_item,
            retrieval_enabled=retrieval_enabled,
            retrieval_backend=retrieval_backend,
            retrieval_provider_id=retrieval_provider_id,
            retrieval_top_k=retrieval_top_k,
        )

    def to_settings_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "inject_pinned_memory": self.inject_pinned_memory,
            "pinned_memories": list(self.pinned_memories),
            "pinned_max_items": self.pinned_max_items,
            "pinned_max_chars_per_item": self.pinned_max_chars_per_item,
            "retrieval_enabled": self.retrieval_enabled,
            "retrieval_backend": self.retrieval_backend,
            "retrieval_provider_id": self.retrieval_provider_id,
            "retrieval_top_k": self.retrieval_top_k,
        }


def normalize_context_memory_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    return ContextMemoryConfig.from_raw(
        raw if isinstance(raw, dict) else None
    ).to_settings_dict()


def load_context_memory_config(
    provider_settings: dict[str, Any] | None,
) -> ContextMemoryConfig:
    return ContextMemoryConfig.from_settings(provider_settings)


def ensure_context_memory_settings(provider_settings: dict[str, Any]) -> dict[str, Any]:
    """Normalize and persist context_memory subtree in provider_settings."""
    normalized = ContextMemoryConfig.from_settings(provider_settings).to_settings_dict()
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
