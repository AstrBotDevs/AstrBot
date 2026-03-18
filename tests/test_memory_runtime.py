from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from astrbot_sdk._invocation_context import caller_plugin_scope
from astrbot_sdk.runtime.capability_router import CapabilityRouter


async def _call(
    router: CapabilityRouter,
    capability: str,
    payload: dict[str, object],
) -> dict[str, object]:
    result = await router.execute(
        capability,
        payload,
        stream=False,
        cancel_token=object(),
        request_id=f"test-{capability}",
    )
    assert isinstance(result, dict)
    return result


@pytest.mark.asyncio
async def test_memory_save_updates_sidecars_and_search() -> None:
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {"key": "user-pref", "value": {"content": "user likes blue"}},
    )

    assert router.memory_store["user-pref"] == {"content": "user likes blue"}
    assert router._memory_index["user-pref"] == {
        "text": "user likes blue",
        "embedding": None,
        "provider_id": None,
    }
    assert "user-pref" in router._memory_dirty_keys
    assert "user-pref" not in router._memory_expires_at

    result = await _call(router, "memory.search", {"query": "likes blue"})
    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["key"] == "user-pref"
    assert item["value"] == {"content": "user likes blue"}
    assert item["match_type"] == "hybrid"
    assert float(item["score"]) > 0
    assert router._memory_index["user-pref"]["provider_id"] == "mock-embedding-provider"
    assert isinstance(router._memory_index["user-pref"]["embedding"], list)
    assert "user-pref" not in router._memory_dirty_keys


@pytest.mark.asyncio
async def test_memory_search_keyword_mode_keeps_dirty_embedding_state() -> None:
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {"key": "alpha-key", "value": {"content": "blue ocean memory"}},
    )

    result = await _call(
        router,
        "memory.search",
        {"query": "alpha", "mode": "keyword", "min_score": 0.95},
    )

    assert [item["key"] for item in result["items"]] == ["alpha-key"]
    assert result["items"][0]["match_type"] == "keyword"
    assert router._memory_index["alpha-key"]["embedding"] is None
    assert "alpha-key" in router._memory_dirty_keys


@pytest.mark.asyncio
async def test_memory_search_vector_mode_supports_ranking_and_limit() -> None:
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {"key": "fruit-note", "value": {"content": "banana smoothie with mango"}},
    )
    await _call(
        router,
        "memory.save",
        {"key": "ocean-note", "value": {"content": "waves on the blue ocean"}},
    )

    result = await _call(
        router,
        "memory.search",
        {"query": "banana smoothie", "mode": "vector", "limit": 1},
    )

    assert len(result["items"]) == 1
    assert result["items"][0]["key"] == "fruit-note"
    assert result["items"][0]["match_type"] == "vector"


@pytest.mark.asyncio
async def test_memory_search_auto_falls_back_to_keyword_without_embedding_provider() -> (
    None
):
    router = CapabilityRouter()
    router._active_provider_ids["embedding"] = None

    await _call(
        router,
        "memory.save",
        {"key": "alpha-key", "value": {"content": "blue ocean memory"}},
    )

    result = await _call(router, "memory.search", {"query": "alpha", "mode": "auto"})

    assert [item["key"] for item in result["items"]] == ["alpha-key"]
    assert result["items"][0]["match_type"] == "keyword"
    assert router._memory_index["alpha-key"]["embedding"] is None
    assert "alpha-key" in router._memory_dirty_keys


@pytest.mark.asyncio
async def test_memory_search_reembeds_when_embedding_provider_changes() -> None:
    router = CapabilityRouter()
    router._provider_catalog["embedding"].append(
        {
            "id": "mock-embedding-provider-alt",
            "model": "mock-embedding-model-alt",
            "type": "mock",
            "provider_type": "embedding",
        }
    )
    router._provider_configs["mock-embedding-provider-alt"] = {
        "id": "mock-embedding-provider-alt",
        "model": "mock-embedding-model-alt",
        "type": "mock",
        "provider_type": "embedding",
        "enable": True,
    }

    await _call(
        router,
        "memory.save",
        {"key": "topic", "value": {"content": "banana smoothie with mango"}},
    )

    first = await _call(router, "memory.search", {"query": "banana smoothie"})
    first_embedding = list(router._memory_index["topic"]["embedding"])
    assert first["items"][0]["match_type"] == "hybrid"
    assert router._memory_index["topic"]["provider_id"] == "mock-embedding-provider"

    router._active_provider_ids["embedding"] = "mock-embedding-provider-alt"

    second = await _call(router, "memory.search", {"query": "banana smoothie"})
    second_embedding = list(router._memory_index["topic"]["embedding"])
    assert second["items"][0]["match_type"] == "hybrid"
    assert router._memory_index["topic"]["provider_id"] == "mock-embedding-provider-alt"
    assert first_embedding != second_embedding


@pytest.mark.asyncio
async def test_memory_stats_reports_index_embedding_and_dirty_counts() -> None:
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {"key": "a", "value": {"content": "alpha"}},
    )
    await _call(
        router,
        "memory.save_with_ttl",
        {"key": "b", "value": {"content": "beta"}, "ttl_seconds": 60},
    )

    with caller_plugin_scope("test-plugin"):
        before = await _call(router, "memory.stats", {})
    assert before["total_items"] == 2
    assert before["ttl_entries"] == 1
    assert before["indexed_items"] == 2
    assert before["embedded_items"] == 0
    assert before["dirty_items"] == 2

    await _call(router, "memory.search", {"query": "alpha"})

    with caller_plugin_scope("test-plugin"):
        after = await _call(router, "memory.stats", {})
    assert after["total_items"] == 2
    assert after["ttl_entries"] == 1
    assert after["indexed_items"] == 2
    assert after["embedded_items"] == 2
    assert after["dirty_items"] == 0


@pytest.mark.asyncio
async def test_memory_save_with_ttl_registers_expiry_and_purges_on_read() -> None:
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save_with_ttl",
        {"key": "temp-note", "value": {"content": "temporary note"}, "ttl_seconds": 60},
    )

    assert "temp-note" in router._memory_index
    assert "temp-note" in router._memory_dirty_keys
    assert router._memory_expires_at["temp-note"] is not None

    search_result = await _call(router, "memory.search", {"query": "temporary"})
    assert search_result["items"][0]["value"] == {"content": "temporary note"}

    router._memory_expires_at["temp-note"] = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )

    get_result = await _call(router, "memory.get", {"key": "temp-note"})
    assert get_result == {"value": None}
    assert "temp-note" not in router.memory_store
    assert "temp-note" not in router._memory_index
    assert "temp-note" not in router._memory_expires_at
    assert "temp-note" not in router._memory_dirty_keys


@pytest.mark.asyncio
async def test_memory_get_many_unwraps_ttl_value_and_returns_none_after_expiry() -> (
    None
):
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save_with_ttl",
        {"key": "session", "value": {"content": "active session"}, "ttl_seconds": 60},
    )

    result = await _call(router, "memory.get_many", {"keys": ["session", "missing"]})
    assert result == {
        "items": [
            {"key": "session", "value": {"content": "active session"}},
            {"key": "missing", "value": None},
        ]
    }

    router._memory_expires_at["session"] = datetime.now(timezone.utc) - timedelta(
        seconds=1
    )

    expired_result = await _call(router, "memory.get_many", {"keys": ["session"]})
    assert expired_result == {"items": [{"key": "session", "value": None}]}


@pytest.mark.asyncio
async def test_memory_delete_many_clears_sidecars() -> None:
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {"key": "a", "value": {"content": "alpha"}},
    )
    await _call(
        router,
        "memory.save_with_ttl",
        {"key": "b", "value": {"content": "beta"}, "ttl_seconds": 60},
    )

    result = await _call(router, "memory.delete_many", {"keys": ["a", "b", "c"]})
    assert result == {"deleted_count": 2}
    assert router.memory_store == {}
    assert router._memory_index == {}
    assert router._memory_expires_at == {}
    assert router._memory_dirty_keys == set()
