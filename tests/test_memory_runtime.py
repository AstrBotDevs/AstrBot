from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import astrbot_sdk._memory_backend as memory_backend_module
import pytest
from astrbot_sdk._internal.invocation_context import caller_plugin_scope
from astrbot_sdk.errors import AstrBotError
from astrbot_sdk.runtime.capability_router import CapabilityRouter


async def _call(
    router: CapabilityRouter,
    capability: str,
    payload: dict[str, object],
    *,
    plugin_id: str = "test-plugin",
) -> dict[str, object]:
    with caller_plugin_scope(plugin_id):
        result = await router.execute(
            capability,
            payload,
            stream=False,
            cancel_token=object(),
            request_id=f"{plugin_id}:{capability}",
        )
    assert isinstance(result, dict)
    return result


def _memory_db_path(tmp_path: Path, plugin_id: str) -> Path:
    return (
        tmp_path
        / ".astrbot_sdk_testing"
        / "plugin_data"
        / plugin_id
        / "memory"
        / "memory.sqlite3"
    )


@pytest.mark.asyncio
async def test_memory_is_plugin_scoped_and_persistent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {"key": "profile", "value": {"content": "alice likes blue"}},
        plugin_id="plugin-a",
    )
    await _call(
        router,
        "memory.save",
        {"key": "profile", "value": {"content": "bob likes green"}},
        plugin_id="plugin-b",
    )

    profile_a = await _call(
        router,
        "memory.get",
        {"key": "profile"},
        plugin_id="plugin-a",
    )
    profile_b = await _call(
        router,
        "memory.get",
        {"key": "profile"},
        plugin_id="plugin-b",
    )

    assert profile_a == {"value": {"content": "alice likes blue"}}
    assert profile_b == {"value": {"content": "bob likes green"}}
    assert _memory_db_path(tmp_path, "plugin-a").exists()

    restarted = CapabilityRouter()
    persisted = await _call(
        restarted,
        "memory.get",
        {"key": "profile"},
        plugin_id="plugin-a",
    )
    assert persisted == {"value": {"content": "alice likes blue"}}


@pytest.mark.asyncio
async def test_memory_namespace_search_respects_descendants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {
            "key": "profile",
            "namespace": "users/alice",
            "value": {"content": "alice likes blue"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "session-note",
            "namespace": "users/alice/sessions/1",
            "value": {"content": "alice asked about the sea"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "profile",
            "namespace": "users/bob",
            "value": {"content": "bob likes green"},
        },
    )

    exact = await _call(
        router,
        "memory.search",
        {
            "query": "alice",
            "namespace": "users/alice",
            "include_descendants": False,
            "mode": "keyword",
        },
    )
    scoped = await _call(
        router,
        "memory.search",
        {
            "query": "alice",
            "namespace": "users/alice",
            "include_descendants": True,
            "mode": "keyword",
        },
    )

    assert [(item["namespace"], item["key"]) for item in exact["items"]] == [
        ("users/alice", "profile")
    ]
    assert {(item["namespace"], item["key"]) for item in scoped["items"]} == {
        ("users/alice", "profile"),
        ("users/alice/sessions/1", "session-note"),
    }


@pytest.mark.asyncio
async def test_memory_search_auto_falls_back_to_keyword_without_embedding_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
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


@pytest.mark.asyncio
async def test_memory_vector_search_and_stats_report_vector_backend(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
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
    stats = await _call(router, "memory.stats", {})

    assert len(result["items"]) == 1
    assert result["items"][0]["key"] == "fruit-note"
    assert result["items"][0]["match_type"] == "vector"
    assert stats["plugin_id"] == "test-plugin"
    assert stats["total_items"] == 2
    assert stats["vector_backend"] in {"faiss", "exact"}


@pytest.mark.asyncio
async def test_memory_save_with_ttl_expires_across_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    base_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(memory_backend_module, "_utcnow", lambda: base_now)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save_with_ttl",
        {
            "key": "session",
            "namespace": "users/alice/sessions/1",
            "value": {"content": "active session"},
            "ttl_seconds": 60,
        },
    )

    result = await _call(
        router,
        "memory.get_many",
        {"keys": ["session"], "namespace": "users/alice/sessions/1"},
    )
    assert result == {
        "items": [{"key": "session", "value": {"content": "active session"}}]
    }

    monkeypatch.setattr(
        memory_backend_module,
        "_utcnow",
        lambda: base_now + timedelta(seconds=61),
    )
    restarted = CapabilityRouter()
    expired = await _call(
        restarted,
        "memory.get",
        {"key": "session", "namespace": "users/alice/sessions/1"},
    )
    assert expired == {"value": None}


@pytest.mark.asyncio
async def test_memory_rejects_unsafe_plugin_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    with pytest.raises(AstrBotError) as exc_info:
        await _call(
            router,
            "memory.save",
            {"key": "profile", "value": {"content": "alice likes blue"}},
            plugin_id="../escape",
        )

    assert exc_info.value.code == "invalid_input"
    assert "safe plugin_id" in exc_info.value.message


@pytest.mark.asyncio
async def test_memory_stats_can_scope_by_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {
            "key": "root-note",
            "value": {"content": "top level"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "user-note",
            "namespace": "users/alice",
            "value": {"content": "alice memory"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "session-note",
            "namespace": "users/alice/sessions/1",
            "value": {"content": "session memory"},
        },
    )

    scoped = await _call(
        router,
        "memory.stats",
        {"namespace": "users/alice", "include_descendants": True},
    )

    assert scoped["namespace"] == "users/alice"
    assert scoped["total_items"] == 2
    assert scoped["namespace_count"] == 2
    assert scoped["fts_enabled"] in {True, False}


@pytest.mark.asyncio
async def test_memory_search_and_stats_can_target_root_namespace_exactly(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {"key": "root-note", "value": {"content": "shared note at root"}},
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "child-note",
            "namespace": "users/alice",
            "value": {"content": "shared note in child namespace"},
        },
    )

    result = await _call(
        router,
        "memory.search",
        {
            "query": "shared note",
            "namespace": "",
            "include_descendants": False,
            "mode": "keyword",
        },
    )
    stats = await _call(
        router,
        "memory.stats",
        {"namespace": "", "include_descendants": False},
    )

    assert [(item.get("namespace"), item["key"]) for item in result["items"]] == [
        (None, "root-note")
    ]
    assert stats["namespace"] == ""
    assert stats["total_items"] == 1


@pytest.mark.asyncio
async def test_memory_namespace_scope_escapes_like_wildcards(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {
            "key": "safe",
            "namespace": "team_1/room",
            "value": {"content": "team scoped note"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "leak",
            "namespace": "teamA1/room",
            "value": {"content": "team scoped note"},
        },
    )

    result = await _call(
        router,
        "memory.search",
        {
            "query": "team scoped",
            "namespace": "team_1",
            "include_descendants": True,
            "mode": "keyword",
        },
    )
    stats = await _call(
        router,
        "memory.stats",
        {"namespace": "team_1", "include_descendants": True},
    )

    assert [(item["namespace"], item["key"]) for item in result["items"]] == [
        ("team_1/room", "safe")
    ]
    assert stats["total_items"] == 1


@pytest.mark.asyncio
async def test_memory_management_capabilities_cover_exact_and_recursive_scope(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {
            "key": "beta",
            "namespace": "users/alice",
            "value": {"content": "beta note"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "Alpha",
            "namespace": "users/alice",
            "value": {"content": "alpha note"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "apple",
            "namespace": "users/alice",
            "value": {"content": "apple note"},
        },
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "child-note",
            "namespace": "users/alice/sessions/1",
            "value": {"content": "child note"},
        },
    )

    keys = await _call(
        router,
        "memory.list_keys",
        {"namespace": "users/alice"},
    )
    exact_count = await _call(
        router,
        "memory.count",
        {"namespace": "users/alice"},
    )
    recursive_count = await _call(
        router,
        "memory.count",
        {"namespace": "users/alice", "include_descendants": True},
    )
    exists = await _call(
        router,
        "memory.exists",
        {"key": "child-note", "namespace": "users/alice/sessions/1"},
    )
    missing = await _call(
        router,
        "memory.exists",
        {"key": "child-note", "namespace": "users/alice"},
    )
    cleared_exact = await _call(
        router,
        "memory.clear_namespace",
        {"namespace": "users/alice"},
    )
    remaining_recursive = await _call(
        router,
        "memory.count",
        {"namespace": "users/alice", "include_descendants": True},
    )
    cleared_recursive = await _call(
        router,
        "memory.clear_namespace",
        {"namespace": "users/alice", "include_descendants": True},
    )
    final_count = await _call(
        router,
        "memory.count",
        {"namespace": "users/alice", "include_descendants": True},
    )

    assert keys == {"keys": ["Alpha", "apple", "beta"]}
    assert exact_count == {"count": 3}
    assert recursive_count == {"count": 4}
    assert exists == {"exists": True}
    assert missing == {"exists": False}
    assert cleared_exact == {"deleted_count": 3}
    assert remaining_recursive == {"count": 1}
    assert cleared_recursive == {"deleted_count": 1}
    assert final_count == {"count": 0}


@pytest.mark.asyncio
async def test_memory_management_capabilities_ignore_expired_ttl_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    base_now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(memory_backend_module, "_utcnow", lambda: base_now)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save_with_ttl",
        {
            "key": "temp",
            "namespace": "users/alice",
            "value": {"content": "temporary"},
            "ttl_seconds": 60,
        },
    )

    monkeypatch.setattr(
        memory_backend_module,
        "_utcnow",
        lambda: base_now + timedelta(seconds=61),
    )
    restarted = CapabilityRouter()

    keys = await _call(
        restarted,
        "memory.list_keys",
        {"namespace": "users/alice"},
    )
    count = await _call(
        restarted,
        "memory.count",
        {"namespace": "users/alice"},
    )
    exists = await _call(
        restarted,
        "memory.exists",
        {"key": "temp", "namespace": "users/alice"},
    )

    assert keys == {"keys": []}
    assert count == {"count": 0}
    assert exists == {"exists": False}


@pytest.mark.asyncio
async def test_memory_management_capabilities_remain_plugin_scoped_under_overlap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    router = CapabilityRouter()

    await _call(
        router,
        "memory.save",
        {
            "key": "profile",
            "namespace": "users/alice",
            "value": {"content": "plugin a"},
        },
        plugin_id="plugin-a",
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "session",
            "namespace": "users/alice/sessions/1",
            "value": {"content": "plugin a child"},
        },
        plugin_id="plugin-a",
    )
    await _call(
        router,
        "memory.save",
        {
            "key": "profile",
            "namespace": "users/alice",
            "value": {"content": "plugin b"},
        },
        plugin_id="plugin-b",
    )

    clear_task = _call(
        router,
        "memory.clear_namespace",
        {"namespace": "users/alice", "include_descendants": True},
        plugin_id="plugin-a",
    )
    count_task = _call(
        router,
        "memory.count",
        {"namespace": "users/alice", "include_descendants": True},
        plugin_id="plugin-b",
    )
    exists_task = _call(
        router,
        "memory.exists",
        {"key": "profile", "namespace": "users/alice"},
        plugin_id="plugin-b",
    )
    cleared, plugin_b_count, plugin_b_exists = await asyncio.gather(
        clear_task,
        count_task,
        exists_task,
    )

    plugin_a_after = await _call(
        router,
        "memory.count",
        {"namespace": "users/alice", "include_descendants": True},
        plugin_id="plugin-a",
    )

    assert cleared == {"deleted_count": 2}
    assert plugin_b_count == {"count": 1}
    assert plugin_b_exists == {"exists": True}
    assert plugin_a_after == {"count": 0}
