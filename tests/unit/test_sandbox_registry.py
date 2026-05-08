from pathlib import Path

from astrbot.core.computer.sandbox_registry import SandboxRegistry


def _upsert(registry: SandboxRegistry, sandbox_id: str, **kwargs):
    return registry.upsert_sandbox(
        sandbox_id=sandbox_id,
        sandbox_name=kwargs.pop("sandbox_name", sandbox_id),
        booter_type=kwargs.pop("booter_type", "cua"),
        provider=kwargs.pop("provider", "cua"),
        managed=kwargs.pop("managed", True),
        created_by_astrbot=kwargs.pop("created_by_astrbot", True),
        owner_user_id=kwargs.pop("owner_user_id", "user-a"),
        owner_session_id=kwargs.pop("owner_session_id", "session-a"),
        connect_info=kwargs.pop("connect_info", {}),
        **kwargs,
    )


def test_sandbox_registry_persists_and_reloads_state(tmp_path: Path):
    storage_path = tmp_path / "sandbox_registry.json"
    registry = SandboxRegistry(storage_path=storage_path)
    _upsert(registry, "sb-1", is_default=True)
    registry.set_current_sandbox_id("session-a", "sb-1")
    registry.save()

    restored = SandboxRegistry(storage_path=storage_path)
    restored.load()

    assert restored.default_sandbox_id == "sb-1"
    assert restored.get_current_sandbox_id("session-a") == "sb-1"
    assert restored.get_sandbox("sb-1")["sandbox_name"] == "sb-1"


def test_sandbox_registry_delete_default_promotes_another_managed_sandbox(tmp_path):
    registry = SandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    _upsert(registry, "sb-default", is_default=True)
    _upsert(registry, "sb-next")

    registry.delete_sandbox("sb-default")

    assert registry.default_sandbox_id == "sb-next"
    assert registry.get_sandbox("sb-next")["is_default"] is True


def test_sandbox_registry_tracks_default_per_provider(tmp_path):
    registry = SandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    _upsert(registry, "cua-default", provider="cua", is_default=True)
    _upsert(registry, "neo-default", provider="shipyard_neo", is_default=True)

    assert registry.get_default_sandbox_id("cua") == "cua-default"
    assert registry.get_default_sandbox_id("shipyard_neo") == "neo-default"
    assert registry.default_sandbox_id == "neo-default"

    registry.delete_sandbox("neo-default")

    assert registry.get_default_sandbox_id("shipyard_neo") is None
    assert registry.get_default_sandbox_id("cua") == "cua-default"


def test_sandbox_registry_acquires_releases_and_takes_over_lease(tmp_path):
    registry = SandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    _upsert(registry, "sb-1")

    assert registry.acquire_lease(
        sandbox_id="sb-1", session_id="session-a", user_id="user-a", ttl=30, now=100
    )
    assert (
        registry.acquire_lease(
            sandbox_id="sb-1", session_id="session-b", user_id="user-b", ttl=30, now=110
        )
        is False
    )

    registry.release_lease("sb-1")
    assert registry.get_sandbox("sb-1")["controller_session_id"] is None

    registry.takeover_lease(
        sandbox_id="sb-1", session_id="session-b", user_id="user-b", ttl=10, now=120
    )
    assert registry.get_sandbox("sb-1")["lease_expires_at"] == 130


def test_sandbox_registry_reconcile_startup_clears_managed_leases(tmp_path):
    registry = SandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    _upsert(
        registry,
        "managed",
        controller_user_id="user-a",
        controller_session_id="session-a",
        lease_expires_at=999,
    )
    _upsert(
        registry,
        "external",
        managed=False,
        created_by_astrbot=False,
        controller_user_id="user-b",
        controller_session_id="session-b",
        lease_expires_at=999,
    )

    registry.reconcile_startup()

    assert registry.get_sandbox("managed")["controller_session_id"] is None
    assert registry.get_sandbox("managed")["status"] == "unknown"
    assert registry.get_sandbox("external")["controller_session_id"] == "session-b"


def test_sandbox_registry_load_only_clears_managed_leases(tmp_path):
    storage_path = tmp_path / "sandbox_registry.json"
    registry = SandboxRegistry(storage_path=storage_path)
    _upsert(
        registry,
        "managed",
        controller_user_id="user-a",
        controller_session_id="session-a",
        lease_expires_at=999,
    )
    _upsert(
        registry,
        "external",
        managed=False,
        created_by_astrbot=False,
        controller_user_id="user-b",
        controller_session_id="session-b",
        lease_expires_at=999,
    )
    registry.save()

    restored = SandboxRegistry(storage_path=storage_path)
    restored.load()

    assert restored.get_sandbox("managed")["controller_session_id"] is None
    assert restored.get_sandbox("external")["controller_session_id"] == "session-b"


def test_sandbox_registry_load_recovers_from_corrupted_json(tmp_path):
    storage_path = tmp_path / "sandbox_registry.json"
    storage_path.write_text("{not-json", encoding="utf-8")

    registry = SandboxRegistry(storage_path=storage_path)
    registry.load()

    assert registry.default_sandbox_id is None
    assert registry.list_sandboxes() == []


def test_sandbox_registry_updates_config_and_status(tmp_path):
    registry = SandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    _upsert(registry, "sb-1")

    registry.update_sandbox_config(
        "sb-1", idle_timeout=30, expires_at=200, retention_policy="persistent"
    )
    registry.update_sandbox_status("sb-1", "stopped")

    record = registry.get_sandbox("sb-1")
    assert record["idle_timeout"] == 30
    assert record["expires_at"] == 200
    assert record["retention_policy"] == "persistent"
    assert record["status"] == "stopped"


def test_sandbox_registry_upsert_preserves_runtime_fields_when_omitted(tmp_path):
    registry = SandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    _upsert(
        registry,
        "sb-1",
        controller_user_id="user-a",
        controller_session_id="session-a",
        lease_expires_at=200,
        last_used_at=100,
        idle_timeout=30,
        status="unknown",
    )

    _upsert(registry, "sb-1", sandbox_name="renamed", connect_info={"name": "renamed"})

    record = registry.get_sandbox("sb-1")
    assert record["sandbox_name"] == "renamed"
    assert record["connect_info"] == {"name": "renamed"}
    assert record["controller_user_id"] == "user-a"
    assert record["controller_session_id"] == "session-a"
    assert record["lease_expires_at"] == 200
    assert record["last_used_at"] == 100
    assert record["idle_timeout"] == 30
    assert record["status"] == "unknown"


def test_sandbox_registry_upsert_preserves_default_marker_when_omitted(tmp_path):
    registry = SandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    _upsert(registry, "sb-1", is_default=True)

    _upsert(registry, "sb-1", sandbox_name="renamed")

    record = registry.get_sandbox("sb-1")
    assert registry.default_sandbox_id == "sb-1"
    assert record["is_default"] is True
