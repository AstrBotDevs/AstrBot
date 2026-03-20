from __future__ import annotations

from astrbot.core.config.default import CONTEXT_MEMORY_DEFAULTS
from astrbot.core.context_memory import (
    ContextMemoryConfig,
    normalize_context_memory_settings,
)
from astrbot.core.context_memory_experimental_backends import (
    ContextMemoryBackend,
)


def test_normalize_context_memory_settings_initializes_fresh_pinned_memories() -> None:
    first = normalize_context_memory_settings(None)
    second = normalize_context_memory_settings(None)

    first["pinned_memories"].append("A")

    assert first["pinned_memories"] == ["A"]
    assert second["pinned_memories"] == []


def test_context_memory_unified_backend_protocol_shape() -> None:
    class _Backend:
        async def evolve(
            self,
            *,
            unified_msg_origin: str,
            turns: list[str],
            metadata=None,
        ) -> dict:
            return {"ok": True}

        async def retrieve(
            self,
            *,
            unified_msg_origin: str,
            query: str,
            top_k: int,
        ) -> list[str]:
            return []

        async def export_session(self, *, unified_msg_origin: str) -> dict:
            return {}

        async def import_session(
            self,
            *,
            unified_msg_origin: str,
            payload: dict,
        ) -> None:
            return None

    assert isinstance(_Backend(), ContextMemoryBackend)


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
