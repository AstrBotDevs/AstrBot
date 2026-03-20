# ruff: noqa: E402
from __future__ import annotations

import sqlite3
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest


def _install_optional_dependency_stubs() -> None:
    def install(name: str, attrs: dict[str, object]) -> None:
        if name in sys.modules:
            return
        module = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(module, key, value)
        sys.modules[name] = module

    install(
        "faiss",
        {
            "read_index": lambda *args, **kwargs: None,
            "write_index": lambda *args, **kwargs: None,
            "IndexFlatL2": type("IndexFlatL2", (), {}),
            "IndexIDMap": type("IndexIDMap", (), {}),
            "normalize_L2": lambda *args, **kwargs: None,
        },
    )
    install("pypdf", {"PdfReader": type("PdfReader", (), {})})
    install(
        "jieba",
        {
            "cut": lambda text, *args, **kwargs: text.split(),
            "lcut": lambda text, *args, **kwargs: text.split(),
        },
    )
    install("rank_bm25", {"BM25Okapi": type("BM25Okapi", (), {})})


_install_optional_dependency_stubs()

from astrbot.core.sdk_bridge.capability_bridge import CoreCapabilityBridge


class _FakePluginBridge:
    def __init__(self) -> None:
        self.configs = {"ai_girlfriend": {"enable_morning": True}}

    def resolve_request_plugin_id(self, _request_id: str) -> str:
        return "ai_girlfriend"

    def get_plugin_config(self, plugin_id: str) -> dict[str, object] | None:
        return self.configs.get(plugin_id)

    def get_plugin_metadata(self, plugin_id: str) -> dict[str, object] | None:
        return {"name": plugin_id}

    def list_plugin_metadata(self) -> list[dict[str, object]]:
        return [{"name": "ai_girlfriend"}]

    def resolve_request_session(self, _request_id: str):
        return SimpleNamespace(event=SimpleNamespace(unified_msg_origin="umo:test"))


class _FakeStarContext:
    def get_all_stars(self):
        return []


class _FakeMemorySp:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], object] = {}

    async def get_async(self, scope, scope_id, key, default=None):
        return self.store.get((scope, scope_id, key), default)

    async def put_async(self, scope, scope_id, key, value):
        self.store[(scope, scope_id, key)] = value

    async def remove_async(self, scope, scope_id, key):
        self.store.pop((scope, scope_id, key), None)

    async def range_get_async(self, scope, scope_id=None, key=None):
        items = []
        for item_scope, item_scope_id, item_key in self.store:
            if item_scope != scope:
                continue
            if scope_id is not None and item_scope_id != scope_id:
                continue
            if key is not None and item_key != key:
                continue
            items.append(SimpleNamespace(key=item_key))
        return items


class _FakeEmbeddingProvider:
    def __init__(self, provider_id: str = "embedding-main") -> None:
        self.provider_id = provider_id

    def meta(self):
        return SimpleNamespace(id=self.provider_id)

    @staticmethod
    def _vector_for_text(text: str) -> list[float]:
        normalized = str(text).casefold()
        if "banana" in normalized or "mango" in normalized:
            return [1.0, 0.0]
        if "ocean" in normalized or "blue" in normalized:
            return [0.0, 1.0]
        return [0.5, 0.5]

    async def get_embedding(self, text: str) -> list[float]:
        return self._vector_for_text(text)

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        return [self._vector_for_text(text) for text in texts]

    def get_dim(self) -> int:
        return 2


class _FakeMemoryStarContext(_FakeStarContext):
    def __init__(
        self, embedding_provider: _FakeEmbeddingProvider | None = None
    ) -> None:
        self.embedding_provider = embedding_provider
        self._providers_by_id: dict[str, object] = {}
        if embedding_provider is not None:
            self._providers_by_id[embedding_provider.provider_id] = embedding_provider

    def get_provider_by_id(self, provider_id: str):
        return self._providers_by_id.get(provider_id)

    def get_all_embedding_providers(self):
        if self.embedding_provider is None:
            return []
        return [self.embedding_provider]


class _FakeCancelToken:
    def raise_if_cancelled(self) -> None:
        return None


@pytest.mark.unit
def test_core_capability_bridge_keeps_runtime_router_methods() -> None:
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(),
        plugin_bridge=_FakePluginBridge(),
    )

    assert CoreCapabilityBridge.register.__qualname__ == "CapabilityRouter.register"
    assert len(bridge._registrations) > 0
    assert "metadata.get_plugin_config" in bridge._registrations


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_capability_bridge_serves_registered_plugin_config() -> None:
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(),
        plugin_bridge=_FakePluginBridge(),
    )

    payload = {"name": "ai_girlfriend"}
    result = await bridge.execute(
        "metadata.get_plugin_config",
        payload,
        stream=False,
        cancel_token=_FakeCancelToken(),
        request_id="req-1",
    )

    assert result == {"config": {"enable_morning": True}}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_memory_search_uses_hybrid_ranking_and_runtime_stats(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding_provider = _FakeEmbeddingProvider()
    plugin_bridge = _FakePluginBridge()
    bridge = CoreCapabilityBridge(
        star_context=_FakeMemoryStarContext(embedding_provider),
        plugin_bridge=plugin_bridge,
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_provider_types",
        lambda: (object, object, _FakeEmbeddingProvider, object),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.provider._get_runtime_provider_types",
        lambda: (object, object, _FakeEmbeddingProvider, object),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic.get_astrbot_plugin_data_path",
        lambda: str(tmp_path / "plugin_data"),
    )

    await bridge._memory_save(
        "req-1",
        {"key": "fruit-note", "value": {"content": "banana smoothie with mango"}},
        None,
    )
    await bridge._memory_save(
        "req-1",
        {"key": "ocean-note", "value": {"content": "blue ocean memory"}},
        None,
    )

    result = await bridge._memory_search(
        "req-1",
        {"query": "banana smoothie", "limit": 1},
        None,
    )

    assert result["items"] == [
        {
            "key": "fruit-note",
            "value": {"content": "banana smoothie with mango"},
            "score": 1.0,
            "match_type": "hybrid",
        }
    ]

    stats = await bridge._memory_stats("req-1", {}, None)
    assert stats["total_items"] == 2
    assert stats["indexed_items"] == 2
    assert stats["embedded_items"] == 2
    assert stats["dirty_items"] == 0
    assert stats["plugin_id"] == "ai_girlfriend"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_memory_sidecars_are_scoped_per_plugin(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding_provider = _FakeEmbeddingProvider()

    class _RoutingPluginBridge(_FakePluginBridge):
        def resolve_request_plugin_id(self, request_id: str) -> str:
            if request_id == "req-a":
                return "plugin-a"
            if request_id == "req-b":
                return "plugin-b"
            return super().resolve_request_plugin_id(request_id)

    bridge = CoreCapabilityBridge(
        star_context=_FakeMemoryStarContext(embedding_provider),
        plugin_bridge=_RoutingPluginBridge(),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_provider_types",
        lambda: (object, object, _FakeEmbeddingProvider, object),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.provider._get_runtime_provider_types",
        lambda: (object, object, _FakeEmbeddingProvider, object),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic.get_astrbot_plugin_data_path",
        lambda: str(tmp_path / "plugin_data"),
    )

    await bridge._memory_save(
        "req-a",
        {"key": "alpha-note", "value": {"content": "banana memory"}},
        None,
    )
    await bridge._memory_save(
        "req-b",
        {"key": "beta-note", "value": {"content": "blue ocean memory"}},
        None,
    )

    await bridge._memory_search("req-a", {"query": "banana"}, None)

    stats_a = await bridge._memory_stats("req-a", {}, None)
    stats_b = await bridge._memory_stats("req-b", {}, None)

    assert stats_a["indexed_items"] == 1
    assert stats_a["embedded_items"] == 1
    assert stats_a["dirty_items"] == 0
    assert stats_b["indexed_items"] == 1
    assert stats_b["embedded_items"] == 0
    assert stats_b["dirty_items"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_memory_ttl_restores_expiration_after_sidecar_reset(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bridge = CoreCapabilityBridge(
        star_context=_FakeMemoryStarContext(),
        plugin_bridge=_FakePluginBridge(),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic.get_astrbot_plugin_data_path",
        lambda: str(tmp_path / "plugin_data"),
    )

    await bridge._memory_save_with_ttl(
        "req-1",
        {
            "key": "temp-note",
            "value": {"content": "temporary note"},
            "ttl_seconds": 60,
        },
        None,
    )

    backend = bridge._memory_backend_for_plugin("ai_girlfriend")
    assert backend._db_path.exists() is True  # noqa: SLF001
    with sqlite3.connect(backend._db_path) as conn:  # noqa: SLF001
        row = conn.execute(
            """
            SELECT expires_at
            FROM memory_records
            WHERE namespace = ? AND key = ?
            """,
            ("", "temp-note"),
        ).fetchone()
        assert row is not None
        assert row[0] is not None

    bridge._memory_backends_by_plugin = {}
    bridge._memory_index_by_plugin = {}
    bridge._memory_dirty_keys_by_plugin = {}
    bridge._memory_expires_at_by_plugin = {}
    expired_at = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    with sqlite3.connect(backend._db_path) as conn:  # noqa: SLF001
        conn.execute(
            """
            UPDATE memory_records
            SET expires_at = ?
            WHERE namespace = ? AND key = ?
            """,
            (expired_at, "", "temp-note"),
        )
        conn.commit()

    result = await bridge._memory_get("req-1", {"key": "temp-note"}, None)

    assert result == {"value": None}
