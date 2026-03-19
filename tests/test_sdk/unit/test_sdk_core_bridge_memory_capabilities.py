# ruff: noqa: E402
from __future__ import annotations

import math
import sys
import types
from datetime import datetime, timedelta, timezone
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


class _FakeCancelToken:
    def raise_if_cancelled(self) -> None:
        return None


class _FakePluginBridge:
    def resolve_request_plugin_id(self, request_id: str) -> str:
        return request_id.split(":", maxsplit=1)[0]


class _FakeSp:
    def __init__(self) -> None:
        self.store: dict[tuple[str, str, str], object] = {}

    async def get_async(self, scope, scope_id, key, default=None):
        return self.store.get((scope, scope_id, key), default)

    async def put_async(self, scope, scope_id, key, value):
        self.store[(scope, scope_id, key)] = value

    async def remove_async(self, scope, scope_id, key):
        self.store.pop((scope, scope_id, key), None)

    async def range_get_async(self, scope, scope_id, prefix=None):
        keys = sorted(
            key
            for current_scope, current_scope_id, key in self.store
            if current_scope == scope
            and current_scope_id == scope_id
            and (prefix is None or key.startswith(prefix))
        )
        return [SimpleNamespace(key=key) for key in keys]


def _embedding_vector(text: str, *, rotation: int = 0) -> list[float]:
    weights = {
        "banana": [1.0, 0.0, 0.0, 0.1],
        "smoothie": [0.7, 0.0, 0.0, 0.2],
        "mango": [0.5, 0.0, 0.0, 0.0],
        "ocean": [0.0, 1.0, 0.0, 0.1],
        "blue": [0.0, 0.7, 0.0, 0.0],
        "waves": [0.0, 0.5, 0.0, 0.0],
        "alpha": [0.0, 0.0, 1.0, 0.0],
        "memory": [0.0, 0.0, 0.4, 0.0],
        "temporary": [0.0, 0.0, 0.0, 1.0],
    }
    values = [0.0, 0.0, 0.0, 0.0]
    normalized = str(text).casefold()
    for token, token_weights in weights.items():
        if token in normalized:
            values = [
                current + delta
                for current, delta in zip(values, token_weights, strict=True)
            ]
    if rotation:
        rotation %= len(values)
        values = values[-rotation:] + values[:-rotation]
    norm = math.sqrt(sum(value * value for value in values))
    if norm <= 0:
        return values
    return [value / norm for value in values]


class _FakeEmbeddingProvider:
    def __init__(self, provider_id: str, *, rotation: int = 0) -> None:
        self.provider_id = provider_id
        self.rotation = rotation
        self.single_calls: list[str] = []
        self.batch_calls: list[list[str]] = []

    def meta(self):
        return SimpleNamespace(id=self.provider_id)

    async def get_embedding(self, text: str) -> list[float]:
        self.single_calls.append(text)
        return _embedding_vector(text, rotation=self.rotation)

    async def get_embeddings(self, texts: list[str]) -> list[list[float]]:
        self.batch_calls.append(list(texts))
        return [_embedding_vector(text, rotation=self.rotation) for text in texts]

    def get_dim(self) -> int:
        return 4


class _FakeStarContext:
    def __init__(self, providers: list[_FakeEmbeddingProvider] | None = None) -> None:
        self._providers = {
            provider.provider_id: provider for provider in (providers or [])
        }
        self._embedding_providers = list(providers or [])

    def get_provider_by_id(self, provider_id: str):
        return self._providers.get(provider_id)

    def get_all_embedding_providers(self):
        return list(self._embedding_providers)

    def get_all_stars(self):
        return []


async def _call(
    bridge: CoreCapabilityBridge,
    capability: str,
    payload: dict[str, object],
    *,
    request_id: str,
) -> dict[str, object]:
    result = await bridge.execute(
        capability,
        payload,
        stream=False,
        cancel_token=_FakeCancelToken(),
        request_id=request_id,
    )
    assert isinstance(result, dict)
    return result


@pytest.fixture
def _patch_embedding_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_types = (
        type("FakeSTTProvider", (), {}),
        type("FakeTTSProvider", (), {}),
        _FakeEmbeddingProvider,
        type("FakeRerankProvider", (), {}),
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_provider_types",
        lambda: provider_types,
    )
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.provider._get_runtime_provider_types",
        lambda: provider_types,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_memory_search_uses_hybrid_embeddings_and_updates_stats(
    monkeypatch: pytest.MonkeyPatch,
    _patch_embedding_runtime: None,
) -> None:
    fake_sp = _FakeSp()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_sp",
        lambda: fake_sp,
    )
    provider = _FakeEmbeddingProvider("embedding-main")
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext([provider]),
        plugin_bridge=_FakePluginBridge(),
    )

    await _call(
        bridge,
        "memory.save",
        {"key": "fruit-note", "value": {"content": "banana smoothie with mango"}},
        request_id="plugin-a:req-1",
    )
    await _call(
        bridge,
        "memory.save",
        {"key": "ocean-note", "value": {"content": "waves on the blue ocean"}},
        request_id="plugin-a:req-2",
    )

    result = await _call(
        bridge,
        "memory.search",
        {"query": "banana smoothie", "limit": 1},
        request_id="plugin-a:req-3",
    )
    assert result["items"][0]["key"] == "fruit-note"
    assert result["items"][0]["match_type"] == "hybrid"
    assert float(result["items"][0]["score"]) > 0.0
    assert provider.batch_calls == [
        ["banana smoothie with mango", "waves on the blue ocean"]
    ]
    assert provider.single_calls == ["banana smoothie"]

    stats = await _call(bridge, "memory.stats", {}, request_id="plugin-a:req-4")
    assert stats["total_items"] == 2
    assert int(stats["total_bytes"]) > 0
    assert stats["plugin_id"] == "plugin-a"
    assert stats["ttl_entries"] == 0
    assert stats["indexed_items"] == 2
    assert stats["embedded_items"] == 2
    assert stats["dirty_items"] == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_memory_search_auto_falls_back_to_keyword_without_provider(
    monkeypatch: pytest.MonkeyPatch,
    _patch_embedding_runtime: None,
) -> None:
    fake_sp = _FakeSp()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_sp",
        lambda: fake_sp,
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext(),
        plugin_bridge=_FakePluginBridge(),
    )

    await _call(
        bridge,
        "memory.save",
        {"key": "alpha-key", "value": {"content": "blue ocean memory"}},
        request_id="plugin-a:req-1",
    )

    result = await _call(
        bridge,
        "memory.search",
        {"query": "alpha", "mode": "auto"},
        request_id="plugin-a:req-2",
    )
    assert result["items"] == [
        {
            "key": "alpha-key",
            "value": {"content": "blue ocean memory"},
            "score": 1.0,
            "match_type": "keyword",
        }
    ]

    stats = await _call(bridge, "memory.stats", {}, request_id="plugin-a:req-3")
    assert stats["embedded_items"] == 0
    assert stats["dirty_items"] == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_memory_sidecars_are_scoped_per_plugin(
    monkeypatch: pytest.MonkeyPatch,
    _patch_embedding_runtime: None,
) -> None:
    fake_sp = _FakeSp()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_sp",
        lambda: fake_sp,
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext([_FakeEmbeddingProvider("embedding-main")]),
        plugin_bridge=_FakePluginBridge(),
    )

    await _call(
        bridge,
        "memory.save",
        {"key": "shared", "value": {"content": "banana smoothie profile"}},
        request_id="plugin-a:req-1",
    )
    await _call(
        bridge,
        "memory.save",
        {"key": "shared", "value": {"content": "blue ocean profile"}},
        request_id="plugin-b:req-1",
    )

    plugin_a_result = await _call(
        bridge,
        "memory.search",
        {"query": "banana smoothie", "limit": 1},
        request_id="plugin-a:req-2",
    )
    plugin_b_result = await _call(
        bridge,
        "memory.search",
        {"query": "blue ocean", "limit": 1},
        request_id="plugin-b:req-2",
    )

    assert plugin_a_result["items"][0]["value"] == {
        "content": "banana smoothie profile"
    }
    assert plugin_b_result["items"][0]["value"] == {"content": "blue ocean profile"}
    assert (
        bridge._memory_sidecars("plugin-a")[0]["shared"]["text"]
        == "banana smoothie profile"
    )
    assert (
        bridge._memory_sidecars("plugin-b")[0]["shared"]["text"] == "blue ocean profile"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_memory_search_reembeds_when_provider_changes(
    monkeypatch: pytest.MonkeyPatch,
    _patch_embedding_runtime: None,
) -> None:
    fake_sp = _FakeSp()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_sp",
        lambda: fake_sp,
    )
    primary = _FakeEmbeddingProvider("embedding-main", rotation=0)
    alternate = _FakeEmbeddingProvider("embedding-alt", rotation=1)
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext([primary, alternate]),
        plugin_bridge=_FakePluginBridge(),
    )

    await _call(
        bridge,
        "memory.save",
        {"key": "topic", "value": {"content": "banana smoothie with mango"}},
        request_id="plugin-a:req-1",
    )

    await _call(
        bridge,
        "memory.search",
        {"query": "banana smoothie"},
        request_id="plugin-a:req-2",
    )
    first_sidecar = dict(bridge._memory_sidecars("plugin-a")[0]["topic"])

    await _call(
        bridge,
        "memory.search",
        {"query": "banana smoothie", "provider_id": "embedding-alt"},
        request_id="plugin-a:req-3",
    )
    second_sidecar = dict(bridge._memory_sidecars("plugin-a")[0]["topic"])

    assert first_sidecar["provider_id"] == "embedding-main"
    assert second_sidecar["provider_id"] == "embedding-alt"
    assert first_sidecar["embedding"] != second_sidecar["embedding"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_core_bridge_memory_ttl_entries_are_purged_during_search(
    monkeypatch: pytest.MonkeyPatch,
    _patch_embedding_runtime: None,
) -> None:
    fake_sp = _FakeSp()
    monkeypatch.setattr(
        "astrbot.core.sdk_bridge.capabilities.basic._get_runtime_sp",
        lambda: fake_sp,
    )
    bridge = CoreCapabilityBridge(
        star_context=_FakeStarContext([_FakeEmbeddingProvider("embedding-main")]),
        plugin_bridge=_FakePluginBridge(),
    )

    await _call(
        bridge,
        "memory.save_with_ttl",
        {"key": "temp", "value": {"content": "temporary note"}, "ttl_seconds": 60},
        request_id="plugin-a:req-1",
    )
    before = await _call(
        bridge,
        "memory.search",
        {"query": "temporary"},
        request_id="plugin-a:req-2",
    )
    assert before["items"][0]["value"] == {"content": "temporary note"}

    stored = await fake_sp.get_async("sdk_memory", "plugin-a", "temp", None)
    assert isinstance(stored, dict)
    expired_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    stored["expires_at"] = expired_at.isoformat()
    bridge._memory_sidecars("plugin-a")[2]["temp"] = expired_at

    after = await _call(
        bridge,
        "memory.search",
        {"query": "temporary"},
        request_id="plugin-a:req-3",
    )
    assert after == {"items": []}
    assert await fake_sp.get_async("sdk_memory", "plugin-a", "temp", None) is None
