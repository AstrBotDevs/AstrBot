from __future__ import annotations

from typing import Any

import pytest
from astrbot_sdk.clients.memory import MemoryClient


class _FakeProxy:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, dict(payload)))
        return dict(self.responses.get(name, {}))


@pytest.mark.asyncio
async def test_root_client_search_preserves_explicit_root_namespace() -> None:
    proxy = _FakeProxy({"memory.search": {"items": []}})
    client = MemoryClient(proxy)  # type: ignore[arg-type]

    await client.search("shared", namespace="", include_descendants=False)

    assert proxy.calls == [
        (
            "memory.search",
            {
                "query": "shared",
                "mode": "auto",
                "namespace": "",
                "include_descendants": False,
            },
        )
    ]


@pytest.mark.asyncio
async def test_root_client_search_omits_namespace_when_scope_is_unspecified() -> None:
    proxy = _FakeProxy({"memory.search": {"items": []}})
    client = MemoryClient(proxy)  # type: ignore[arg-type]

    await client.search("shared")

    assert proxy.calls == [
        (
            "memory.search",
            {
                "query": "shared",
                "mode": "auto",
                "include_descendants": True,
            },
        )
    ]


@pytest.mark.asyncio
async def test_stats_returns_namespace_backend_fields() -> None:
    proxy = _FakeProxy(
        {
            "memory.stats": {
                "total_items": 3,
                "total_bytes": 128,
                "namespace": "users/alice",
                "namespace_count": 2,
                "fts_enabled": True,
                "vector_backend": "faiss",
                "vector_indexes": [{"provider_id": "embedding-1", "dirty": False}],
                "plugin_id": "test-plugin",
                "ttl_entries": 1,
            }
        }
    )
    client = MemoryClient(proxy, namespace="users")  # type: ignore[arg-type]

    stats = await client.stats(namespace="alice", include_descendants=False)

    assert proxy.calls == [
        (
            "memory.stats",
            {
                "include_descendants": False,
                "namespace": "users/alice",
            },
        )
    ]
    assert stats == {
        "total_items": 3,
        "total_bytes": 128,
        "namespace": "users/alice",
        "namespace_count": 2,
        "fts_enabled": True,
        "vector_backend": "faiss",
        "vector_indexes": [{"provider_id": "embedding-1", "dirty": False}],
        "plugin_id": "test-plugin",
        "ttl_entries": 1,
    }
