import asyncio
import json
import threading
from pathlib import Path

import pytest

from astrbot.core.computer.sandbox_registry import SandboxRegistry


def _registry(tmp_path):
    return SandboxRegistry(tmp_path / "sandbox_registry.json")


def _upsert(registry, sandbox_id="generic-1", provider="generic"):
    return registry.upsert_sandbox(
        sandbox_id=sandbox_id,
        sandbox_name=f"Sandbox {sandbox_id}",
        provider=provider,
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": sandbox_id},
        capabilities={"shell", "python", "filesystem"},
        tool_names={"generic_tool"},
    )


def test_registry_upserts_lists_and_deletes_sandboxes(tmp_path):
    registry = _registry(tmp_path)

    record = _upsert(registry)

    assert record["sandbox_id"] == "generic-1"
    assert record["capabilities"] == ["filesystem", "python", "shell"]
    assert record["tool_names"] == ["generic_tool"]
    assert registry.get_sandbox("generic-1")["sandbox_name"] == "Sandbox generic-1"
    assert [item["sandbox_id"] for item in registry.list_sandboxes()] == ["generic-1"]

    registry.delete_sandbox("generic-1")

    assert registry.get_sandbox("generic-1") is None
    assert registry.list_sandboxes() == []


def test_registry_tracks_provider_defaults_and_current_session(tmp_path):
    registry = _registry(tmp_path)
    _upsert(registry, "generic-1", provider="generic")
    _upsert(registry, "other-1", provider="other")

    registry.set_default_sandbox_id("generic-1")
    registry.set_current_sandbox_id("session-a", "generic-1")

    assert registry.get_default_sandbox_id("generic") == "generic-1"
    assert registry.get_default_sandbox_id("other") is None
    assert registry.get_current_sandbox_id("session-a") == "generic-1"

    registry.delete_sandbox("generic-1")

    assert registry.get_current_sandbox_id("session-a") is None


def test_registry_acquires_releases_and_takes_over_leases(tmp_path):
    registry = _registry(tmp_path)
    _upsert(registry)

    assert registry.acquire_lease(
        sandbox_id="generic-1", session_id="session-a", user_id="user-a", ttl=60, now=10
    )
    assert not registry.acquire_lease(
        sandbox_id="generic-1", session_id="session-b", user_id="user-b", ttl=60, now=20
    )

    released = registry.release_lease("generic-1")
    assert released["controller_session_id"] is None
    assert registry.acquire_lease(
        sandbox_id="generic-1", session_id="session-b", user_id="user-b", ttl=60, now=20
    )

    taken = registry.takeover_lease(
        sandbox_id="generic-1", session_id="session-c", user_id="user-c", ttl=60, now=30
    )
    assert taken["controller_session_id"] == "session-c"


def test_registry_saves_loads_and_reconciles_runtime_state(tmp_path):
    registry = _registry(tmp_path)
    _upsert(registry)
    registry.acquire_lease(
        sandbox_id="generic-1", session_id="session-a", user_id="user-a", ttl=60, now=10
    )
    registry.set_current_sandbox_id("session-a", "generic-1")
    registry.save()

    loaded = _registry(tmp_path)
    loaded.load()
    assert loaded.get_sandbox("generic-1")["controller_session_id"] == "session-a"

    loaded.reconcile_startup()

    assert loaded.get_sandbox("generic-1") is None
    assert loaded.get_current_sandbox_id("session-a") is None

    payload = json.loads((tmp_path / "sandbox_registry.json").read_text())
    assert "sandboxes" in payload


def test_registry_reconcile_startup_deletes_non_persistent_creating_records(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Sandbox generic-1",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "generic-1"},
        status="creating",
    )

    registry.reconcile_startup()

    assert registry.get_sandbox("generic-1") is None


def test_registry_reconcile_startup_marks_persistent_running_unknown(tmp_path):
    registry = _registry(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Sandbox generic-1",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "generic-1"},
        status="running",
        retention_policy="persistent",
    )

    registry.reconcile_startup()

    assert registry.get_sandbox("generic-1")["status"] == "unknown"


@pytest.mark.asyncio
async def test_registry_save_async_runs_save_in_worker_thread(tmp_path):
    registry = _registry(tmp_path)
    main_thread_id = threading.get_ident()
    save_thread_id = None

    def fake_write_payload(payload):
        nonlocal save_thread_id
        assert payload == registry._payload
        save_thread_id = threading.get_ident()

    registry._write_payload = fake_write_payload

    await registry.save_async()

    assert save_thread_id is not None
    assert save_thread_id != main_thread_id


@pytest.mark.asyncio
async def test_registry_save_async_serializes_writes(tmp_path):
    registry = _registry(tmp_path)
    active_writes = 0
    max_active_writes = 0
    release_first_write = None
    first_write_started = asyncio.Event()

    def fake_write_payload(payload):
        nonlocal active_writes, max_active_writes, release_first_write
        active_writes += 1
        max_active_writes = max(max_active_writes, active_writes)
        if release_first_write is None:
            release_first_write = threading.Event()
            first_write_started.set()
            assert release_first_write.wait(timeout=1)
        active_writes -= 1

    registry._write_payload = fake_write_payload

    first = asyncio.create_task(registry.save_async())
    await first_write_started.wait()
    second = asyncio.create_task(registry.save_async())
    await asyncio.sleep(0.05)

    assert max_active_writes == 1
    release_first_write.set()
    await first
    await second


def test_registry_write_payload_replaces_temp_file_atomically(tmp_path, monkeypatch):
    registry = _registry(tmp_path)
    payload = {
        "default_sandbox_id": None,
        "default_sandbox_ids": {},
        "sandboxes": {"generic-1": {"sandbox_id": "generic-1"}},
        "session_current": {},
    }
    replace_calls = []
    original_replace = Path.replace

    def track_replace(self, target):
        replace_calls.append((Path(self), Path(target)))
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", track_replace)

    registry._write_payload(payload)

    assert replace_calls
    source_path, target_path = replace_calls[0]
    assert source_path != target_path
    assert target_path == registry.storage_path
    assert source_path.parent == target_path.parent
    assert json.loads(registry.storage_path.read_text(encoding="utf-8")) == payload
