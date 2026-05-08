from pathlib import Path

from astrbot.core.computer.cua_registry import CuaSandboxRegistry


def test_registry_creates_managed_sandbox_record(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")

    record = registry.upsert_sandbox(
        sandbox_id="sb-1",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
    )

    assert record["sandbox_id"] == "sb-1"
    assert record["sandbox_name"] == "default-sandbox"
    assert record["managed"] is True
    assert record["created_by_astrbot"] is True
    assert record["owner_user_id"] == "user-1"
    assert registry.get_sandbox("sb-1") == record


def test_registry_tracks_default_sandbox_pointer(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-default",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
    )

    registry.set_default_sandbox_id("sb-default")

    assert registry.default_sandbox_id == "sb-default"
    assert registry.get_sandbox("sb-default")["is_default"] is True


def test_registry_first_managed_sandbox_becomes_default(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")

    registry.upsert_sandbox(
        sandbox_id="sb-first",
        sandbox_name="first-sandbox",
        booter_type="shipyard_neo",
        provider="shipyard_neo",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "first-sandbox"},
    )

    assert registry.default_sandbox_id == "sb-first"
    assert registry.get_sandbox("sb-first")["is_default"] is True


def test_registry_delete_default_promotes_another_managed_sandbox(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-default",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox"},
        is_default=True,
    )
    registry.upsert_sandbox(
        sandbox_id="sb-next",
        sandbox_name="next-sandbox",
        booter_type="shipyard_neo",
        provider="shipyard_neo",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-2",
        owner_session_id="session-2",
        connect_info={"name": "next-sandbox"},
    )

    registry.delete_sandbox("sb-default")

    assert registry.default_sandbox_id == "sb-next"
    assert registry.get_sandbox("sb-next")["is_default"] is True


def test_registry_tracks_current_sandbox_binding_per_session(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")

    registry.set_current_sandbox_id("session-a", "sb-1")
    registry.set_current_sandbox_id("session-b", "sb-2")

    assert registry.get_current_sandbox_id("session-a") == "sb-1"
    assert registry.get_current_sandbox_id("session-b") == "sb-2"


def test_registry_persists_and_reloads_state(tmp_path: Path):
    storage_path = tmp_path / "sandbox_registry.json"
    registry = CuaSandboxRegistry(storage_path=storage_path)
    registry.upsert_sandbox(
        sandbox_id="sb-1",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
    )
    registry.set_default_sandbox_id("sb-1")
    registry.set_current_sandbox_id("session-a", "sb-1")
    registry.save()

    restored = CuaSandboxRegistry(storage_path=storage_path)
    restored.load()

    assert restored.default_sandbox_id == "sb-1"
    assert restored.get_current_sandbox_id("session-a") == "sb-1"
    assert restored.get_sandbox("sb-1")["sandbox_name"] == "default-sandbox"


def test_registry_load_clears_stale_control_lease_state(tmp_path: Path):
    storage_path = tmp_path / "sandbox_registry.json"
    registry = CuaSandboxRegistry(storage_path=storage_path)
    registry.upsert_sandbox(
        sandbox_id="sb-1",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
        controller_user_id="user-lease",
        controller_session_id="session-lease",
        lease_expires_at=9999999999,
    )
    registry.save()

    restored = CuaSandboxRegistry(storage_path=storage_path)
    restored.load()
    record = restored.get_sandbox("sb-1")

    assert record["controller_user_id"] is None
    assert record["controller_session_id"] is None
    assert record["lease_expires_at"] is None


def test_registry_reconcile_startup_clears_only_managed_control_leases(
    tmp_path: Path,
):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    registry.upsert_sandbox(
        sandbox_id="managed-running",
        sandbox_name="Managed running",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "Managed running"},
        controller_user_id="stale-user",
        controller_session_id="stale-session",
        lease_expires_at=9999999999,
    )
    registry.upsert_sandbox(
        sandbox_id="external-running",
        sandbox_name="External running",
        booter_type="shipyard_neo",
        provider="shipyard_neo",
        managed=False,
        created_by_astrbot=False,
        owner_user_id="user-2",
        owner_session_id="session-2",
        connect_info={"profile": "default"},
        controller_user_id="external-user",
        controller_session_id="external-session",
        lease_expires_at=9999999999,
    )

    registry.reconcile_startup()

    managed = registry.get_sandbox("managed-running")
    external = registry.get_sandbox("external-running")
    assert managed["controller_user_id"] is None
    assert managed["controller_session_id"] is None
    assert managed["lease_expires_at"] is None
    assert external["controller_session_id"] == "external-session"
    assert external["lease_expires_at"] == 9999999999


def test_registry_acquires_and_refreshes_control_lease(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-1",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
    )

    acquired = registry.acquire_lease(
        sandbox_id="sb-1",
        session_id="session-2",
        user_id="user-2",
        ttl=30,
        now=1000.0,
    )

    assert acquired is True
    record = registry.get_sandbox("sb-1")
    assert record["controller_session_id"] == "session-2"
    assert record["controller_user_id"] == "user-2"
    assert record["lease_expires_at"] == 1030.0

    refreshed = registry.acquire_lease(
        sandbox_id="sb-1",
        session_id="session-2",
        user_id="user-2",
        ttl=45,
        now=1010.0,
    )
    assert refreshed is True
    assert registry.get_sandbox("sb-1")["lease_expires_at"] == 1055.0


def test_registry_rejects_busy_lease_from_other_session(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-1",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
        controller_user_id="user-a",
        controller_session_id="session-a",
        lease_expires_at=1100.0,
    )

    acquired = registry.acquire_lease(
        sandbox_id="sb-1",
        session_id="session-b",
        user_id="user-b",
        ttl=30,
        now=1000.0,
    )

    assert acquired is False
    assert registry.get_sandbox("sb-1")["controller_session_id"] == "session-a"


def test_registry_release_and_takeover_control_lease(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-1",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
        controller_user_id="user-a",
        controller_session_id="session-a",
        lease_expires_at=1100.0,
    )

    registry.release_lease("sb-1")
    record = registry.get_sandbox("sb-1")
    assert record["controller_session_id"] is None
    assert record["controller_user_id"] is None
    assert record["lease_expires_at"] is None

    registry.acquire_lease(
        sandbox_id="sb-1",
        session_id="session-a",
        user_id="user-a",
        ttl=30,
        now=1000.0,
    )
    registry.takeover_lease(
        sandbox_id="sb-1",
        session_id="session-b",
        user_id="user-b",
        ttl=15,
        now=1010.0,
    )
    record = registry.get_sandbox("sb-1")
    assert record["controller_session_id"] == "session-b"
    assert record["controller_user_id"] == "user-b"
    assert record["lease_expires_at"] == 1025.0


def test_registry_acquire_lease_uses_five_minute_default_window(tmp_path: Path):
    registry = CuaSandboxRegistry(storage_path=tmp_path / "sandbox_registry.json")
    registry.upsert_sandbox(
        sandbox_id="sb-1",
        sandbox_name="default-sandbox",
        booter_type="cua",
        provider="cua",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="user-1",
        owner_session_id="session-1",
        connect_info={"name": "default-sandbox", "local": True},
    )

    registry.acquire_lease(
        sandbox_id="sb-1",
        session_id="session-2",
        user_id="user-2",
        ttl=300,
        now=1000.0,
    )

    assert registry.get_sandbox("sb-1")["lease_expires_at"] == 1300.0
