import asyncio
import time

import pytest

from astrbot.core.computer.sandbox_manager import SandboxManager
from astrbot.core.computer.sandbox_registry import SandboxRegistry


class FakeBooter:
    def __init__(self):
        self.shutdown_calls = 0
        self.available_result = True

    async def available(self):
        return self.available_result

    async def shutdown(self):
        self.shutdown_calls += 1


class SyncAvailableBooter:
    def available(self):
        return True


class BoolAvailableBooter:
    available = True


class UnavailablePropertyBooter:
    available = False


class FakeProvider:
    provider_id = "generic"
    capabilities = {"shell", "python", "filesystem", "screenshot", "mouse", "keyboard"}
    tool_names = {"astrbot_generic_screenshot"}
    supports_persistent_reconnect = True

    def __init__(self):
        self.created = []
        self.destroyed = []
        self.idle_timeout = 0

    def build_create_config(self, context, session_id):
        return {"session_id": session_id}

    def build_connect_info(self, sandbox_name, config):
        return {"name": sandbox_name, **config}

    def update_connect_info(self, record, *, sandbox_name):
        info = dict(record.get("connect_info") or {})
        info["name"] = sandbox_name
        return info

    def get_idle_timeout(self, context, session_id):
        return self.idle_timeout

    async def create_booter(self, context, session_id, sandbox_id, config):
        booter = FakeBooter()
        self.created.append((session_id, sandbox_id, booter, config))
        return booter

    async def destroy_booter(self, booter, record):
        self.destroyed.append((booter, record["sandbox_id"]))
        await booter.shutdown()


class DeferredBootProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.boot_started = asyncio.Event()
        self.allow_boot = asyncio.Event()
        self.raise_on_boot = False

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.boot_started.set()
        await self.allow_boot.wait()
        if self.raise_on_boot:
            raise RuntimeError("boot failed")
        return await super().create_booter(context, session_id, sandbox_id, config)


class FailingReconnectProvider(FakeProvider):
    async def create_booter(self, context, session_id, sandbox_id, config):
        raise RuntimeError("boot failed")


class AlwaysBusyManager(SandboxManager):
    def acquire_lease(self, sandbox_id: str, session_id: str, *, ttl=None):
        return False


class MissingPersistentProvider(FakeProvider):
    async def check_persistent_sandbox_exists(self, record):
        return False


class ExistingPersistentProvider(FakeProvider):
    async def check_persistent_sandbox_exists(self, record):
        return True


def _manager(tmp_path, provider=None):
    provider = provider or FakeProvider()
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )
    return manager, provider


def test_manager_list_sandboxes_preserves_persisted_tool_names_without_provider(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Generic"},
        capabilities={"shell"},
        tool_names={"persisted_tool"},
    )
    manager.providers.clear()

    sandboxes = manager.list_sandboxes()

    assert sandboxes[0]["tool_names"] == ["persisted_tool"]


@pytest.mark.asyncio
async def test_manager_creates_default_sandbox_and_reuses_available_booter(tmp_path):
    manager, provider = _manager(tmp_path)

    first = await manager.get_or_create_booter(None, "session-a", "generic")
    second = await manager.get_or_create_booter(None, "session-a", "generic")

    assert first is second
    assert len(provider.created) == 1
    sandboxes = manager.list_sandboxes()
    assert len(sandboxes) == 1
    assert sandboxes[0]["provider"] == "generic"
    assert sandboxes[0]["capabilities"] == sorted(provider.capabilities)
    assert sandboxes[0]["tool_names"] == sorted(provider.tool_names)


@pytest.mark.asyncio
async def test_manager_get_or_create_booter_stops_after_repeated_lease_failures(
    tmp_path,
):
    provider = FakeProvider()
    manager = AlwaysBusyManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )

    with pytest.raises(RuntimeError, match="Could not acquire sandbox lease"):
        await manager.get_or_create_booter(None, "session-a", "generic")

    assert len(manager.registry.list_sandboxes()) <= 4


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_returns_authoritative_registry_state(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)

    sandbox = await manager.create_sandbox_uncontrolled(None, "session-a", "generic")

    assert sandbox["status"] == "running"
    assert sandbox == manager.registry.get_sandbox(sandbox["sandbox_id"])


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_rejects_duplicate_name(tmp_path):
    manager, _provider = _manager(tmp_path)

    await manager.create_sandbox_uncontrolled(None, "session-a", "generic", "Named")

    with pytest.raises(RuntimeError, match="Sandbox name 'Named' already exists"):
        await manager.create_sandbox_uncontrolled(None, "session-a", "generic", "Named")


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_blank_name_falls_back_to_sandbox_id(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)

    sandbox = await manager.create_sandbox_uncontrolled(
        None, "session-a", "generic", "   "
    )

    assert sandbox["sandbox_name"] == sandbox["sandbox_id"]


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_deferred_returns_creating_then_running(
    tmp_path,
):
    provider = DeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    assert sandbox["status"] == "creating"
    assert manager.session_booter == {}

    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)
    assert manager.registry.get_sandbox(sandbox["sandbox_id"])["status"] == "creating"

    provider.allow_boot.set()
    for _ in range(20):
        record = manager.registry.get_sandbox(sandbox["sandbox_id"])
        if record and record["status"] == "running":
            break
        await asyncio.sleep(0)

    assert manager.registry.get_sandbox(sandbox["sandbox_id"])["status"] == "running"
    assert sandbox["sandbox_id"] in manager.session_booter


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_deferred_rejects_duplicate_name(tmp_path):
    provider = DeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    with pytest.raises(RuntimeError, match="Sandbox name 'Named' already exists"):
        await manager.create_sandbox_uncontrolled_deferred(
            None, "session-a", "generic", "Named"
        )


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_deferred_keeps_error_record_on_boot_failure(
    tmp_path,
):
    provider = DeferredBootProvider()
    provider.raise_on_boot = True
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)
    provider.allow_boot.set()
    for _ in range(20):
        record = manager.registry.get_sandbox(sandbox["sandbox_id"])
        if record and record["status"] == "error":
            break
        await asyncio.sleep(0)

    record = manager.registry.get_sandbox(sandbox["sandbox_id"])
    assert record is not None
    assert record["status"] == "error"
    assert sandbox["sandbox_id"] not in manager.session_booter


@pytest.mark.asyncio
async def test_destroy_sandbox_cancels_deferred_boot_task(tmp_path):
    provider = DeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)

    destroyed = await manager.destroy_sandbox("session-a", sandbox["sandbox_id"])

    assert destroyed["sandbox_id"] == sandbox["sandbox_id"]
    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None
    assert sandbox["sandbox_id"] not in manager.session_booter
    assert sandbox["sandbox_id"] not in manager.pending_boot_tasks


@pytest.mark.asyncio
async def test_create_sandbox_sets_current_sandbox_after_lease(tmp_path):
    manager, _provider = _manager(tmp_path)

    sandbox = await manager.create_sandbox(None, "session-a", "generic")

    assert sandbox["status"] == "running"
    assert (
        manager.get_current_sandbox("session-a")["current_sandbox_id"]
        == sandbox["sandbox_id"]
    )


@pytest.mark.asyncio
async def test_manager_creates_new_sandbox_when_default_busy(tmp_path):
    manager, provider = _manager(tmp_path)

    await manager.get_or_create_booter(None, "session-a", "generic")
    await manager.get_or_create_booter(None, "session-b", "generic")

    assert len(provider.created) == 2
    assert len(manager.list_sandboxes()) == 2


@pytest.mark.asyncio
async def test_manager_creates_new_sandbox_when_current_binding_is_busy(tmp_path):
    manager, provider = _manager(tmp_path)

    first = await manager.get_or_create_booter(None, "session-a", "generic")
    first_sandbox_id = manager.get_current_sandbox("session-a")["current_sandbox_id"]
    manager.registry.set_current_sandbox_id("session-b", first_sandbox_id)

    second = await manager.get_or_create_booter(None, "session-b", "generic")

    assert second is not first
    assert len(provider.created) == 2
    assert manager.get_current_sandbox("session-b")["current_sandbox_id"] != (
        first_sandbox_id
    )
    first_record = manager.registry.get_sandbox(first_sandbox_id)
    assert first_record["controller_session_id"] == "session-a"
    assert first_record["lease_expires_at"] > time.time()


@pytest.mark.asyncio
async def test_manager_booter_available_accepts_sync_callable_and_property(tmp_path):
    manager, _provider = _manager(tmp_path)

    assert await manager.booter_available(SyncAvailableBooter()) is True
    assert await manager.booter_available(BoolAvailableBooter()) is True
    assert await manager.booter_available(UnavailablePropertyBooter()) is False


@pytest.mark.asyncio
async def test_manager_switches_releases_takes_over_and_destroys(tmp_path):
    manager, provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")

    assert (
        manager.get_current_sandbox("session-a")["current_sandbox_id"]
        == created["sandbox_id"]
    )
    released = manager.release_current_sandbox("session-a")
    assert released["controller_session_id"] is None

    switched = await manager.switch_current_sandbox_checked(
        "session-a", created["sandbox_id"]
    )
    assert switched["controller_session_id"] == "session-a"

    taken = await manager.takeover_sandbox("session-b", created["sandbox_id"])
    assert taken["controller_session_id"] == "session-b"

    destroyed = await manager.destroy_sandbox("session-b", created["sandbox_id"])
    assert destroyed["sandbox_id"] == created["sandbox_id"]
    assert provider.destroyed[0][1] == created["sandbox_id"]
    assert manager.list_sandboxes() == []


@pytest.mark.asyncio
async def test_manager_switch_releases_previous_sandbox_owned_by_same_session(tmp_path):
    manager, _provider = _manager(tmp_path)
    first = await manager.create_sandbox(None, "session-a", "generic", "First")
    second = await manager.create_sandbox(None, "session-a", "generic", "Second")

    switched = await manager.switch_current_sandbox_checked(
        "session-a", second["sandbox_id"]
    )

    first_record = manager.registry.get_sandbox(first["sandbox_id"])
    second_record = manager.registry.get_sandbox(second["sandbox_id"])
    assert switched["sandbox_id"] == second["sandbox_id"]
    assert first_record["controller_session_id"] is None
    assert first_record["lease_expires_at"] is None
    assert second_record["controller_session_id"] == "session-a"
    assert second_record["lease_expires_at"] > time.time()
    assert (
        manager.get_current_sandbox("session-a")["current_sandbox_id"]
        == second["sandbox_id"]
    )


@pytest.mark.asyncio
async def test_manager_create_releases_previous_sandbox_owned_by_same_session(tmp_path):
    manager, _provider = _manager(tmp_path)

    first = await manager.create_sandbox(None, "session-a", "generic", "First")
    second = await manager.create_sandbox(None, "session-a", "generic", "Second")

    first_record = manager.registry.get_sandbox(first["sandbox_id"])
    second_record = manager.registry.get_sandbox(second["sandbox_id"])
    assert first_record["controller_session_id"] is None
    assert first_record["lease_expires_at"] is None
    assert second_record["controller_session_id"] == "session-a"
    assert second_record["lease_expires_at"] > time.time()
    assert (
        manager.get_current_sandbox("session-a")["current_sandbox_id"]
        == second["sandbox_id"]
    )


@pytest.mark.asyncio
async def test_manager_takeover_releases_previous_sandbox_owned_by_same_session(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)

    first = await manager.create_sandbox(None, "session-a", "generic", "First")
    second = await manager.create_sandbox(None, "session-b", "generic", "Second")

    taken = await manager.takeover_sandbox("session-a", second["sandbox_id"])

    first_record = manager.registry.get_sandbox(first["sandbox_id"])
    second_record = manager.registry.get_sandbox(second["sandbox_id"])
    assert taken["sandbox_id"] == second["sandbox_id"]
    assert first_record["controller_session_id"] is None
    assert first_record["lease_expires_at"] is None
    assert second_record["controller_session_id"] == "session-a"
    assert second_record["lease_expires_at"] > time.time()


@pytest.mark.asyncio
async def test_manager_force_releases_other_session_lease(tmp_path):
    manager, _provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")
    taken = await manager.takeover_sandbox("session-b", created["sandbox_id"])
    manager.registry.set_current_sandbox_id("session-b", created["sandbox_id"])

    released = manager.force_release_sandbox(created["sandbox_id"])

    assert taken["controller_session_id"] == "session-b"
    assert released["controller_session_id"] is None
    assert released["lease_expires_at"] is None
    assert manager.get_current_sandbox("session-b")["current_sandbox_id"] is None


@pytest.mark.asyncio
async def test_manager_blocks_observer_booter_access_from_other_session(tmp_path):
    manager, _provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")

    with pytest.raises(RuntimeError, match="controlled by another session"):
        await manager.get_observer_booter_by_id(created["sandbox_id"], "session-b")


@pytest.mark.asyncio
async def test_manager_revives_persistent_sandbox_for_observer_access(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    booter = await manager.get_observer_booter_by_id(
        "generic-1", "dashboard", require_lease=False, context=object()
    )

    assert isinstance(booter, FakeBooter)
    assert len(provider.created) == 1
    assert manager.registry.get_sandbox("generic-1")["status"] == "running"


@pytest.mark.asyncio
async def test_manager_revives_persistent_sandbox_for_switch_access(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    switched = await manager.switch_current_sandbox_checked(
        "session-a", "generic-1", context=object()
    )

    assert switched["sandbox_id"] == "generic-1"
    assert len(provider.created) == 1
    assert manager.registry.get_sandbox("generic-1")["status"] == "running"


@pytest.mark.asyncio
async def test_manager_does_not_revive_destroyed_persistent_sandbox(tmp_path):
    manager, provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")
    manager.update_sandbox_config(
        created["sandbox_id"],
        idle_timeout=None,
        expires_at=None,
        retention_policy="persistent",
    )

    await manager.destroy_sandbox("session-a", created["sandbox_id"])

    with pytest.raises(RuntimeError, match="has been destroyed"):
        await manager.get_observer_booter_by_id(
            created["sandbox_id"],
            "dashboard",
            require_lease=False,
            context=object(),
        )

    assert len(provider.created) == 1


@pytest.mark.asyncio
async def test_manager_does_not_revive_persistent_sandbox_without_provider_support(
    tmp_path,
):
    manager, provider = _manager(tmp_path)
    provider.supports_persistent_reconnect = False
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    with pytest.raises(RuntimeError, match="Sandbox generic-1 is not running"):
        await manager.get_observer_booter_by_id(
            "generic-1", "dashboard", require_lease=False, context=object()
        )

    assert provider.created == []


@pytest.mark.asyncio
async def test_manager_persistent_reconnect_failure_restores_previous_status(tmp_path):
    provider = FailingReconnectProvider()
    manager, _provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    with pytest.raises(RuntimeError, match="boot failed"):
        await manager.get_observer_booter_by_id(
            "generic-1", "dashboard", require_lease=False, context=object()
        )

    assert manager.registry.get_sandbox("generic-1")["status"] == "running"
    assert manager.session_booter == {}


@pytest.mark.asyncio
async def test_manager_revives_persistent_sandbox_for_tool_access(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    booter = await manager.get_observer_booter_by_id(
        "generic-1", "session-a", require_lease=False, context=object()
    )

    assert isinstance(booter, FakeBooter)
    assert len(provider.created) == 1


@pytest.mark.asyncio
async def test_manager_restores_persistent_sandboxes_on_startup(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    await manager.restore_persistent_sandboxes(object())

    assert "generic-1" in manager.session_booter
    assert len(provider.created) == 1
    assert manager.registry.get_sandbox("generic-1")["status"] == "running"


@pytest.mark.asyncio
async def test_manager_reconcile_on_startup_removes_stale_persistent_records(
    tmp_path,
):
    provider = MissingPersistentProvider()
    manager, provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    manager.registry.save()
    await manager.reconcile_on_startup()

    assert manager.registry.get_sandbox("generic-1") is None
    assert len(provider.created) == 0


@pytest.mark.asyncio
async def test_manager_reconcile_on_startup_removes_persistent_records_for_missing_provider(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="missing-1",
        sandbox_name="Persistent",
        booter_type="missing",
        provider="missing",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    manager.registry.save()
    await manager.reconcile_on_startup()

    assert manager.registry.get_sandbox("missing-1") is None


@pytest.mark.asyncio
async def test_manager_reconcile_on_startup_keeps_valid_persistent_records(
    tmp_path,
):
    provider = ExistingPersistentProvider()
    manager, provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    manager.registry.save()
    await manager.reconcile_on_startup()

    record = manager.registry.get_sandbox("generic-1")
    assert record is not None
    assert record["status"] == "unknown"
    assert len(provider.created) == 0


@pytest.mark.asyncio
async def test_manager_idle_cleanup_removes_temporary_sandbox(tmp_path):
    provider = FakeProvider()
    provider.idle_timeout = 0.01
    manager, provider = _manager(tmp_path, provider)

    await manager.get_or_create_booter(None, "session-a", "generic")
    sandbox_id = manager.list_sandboxes()[0]["sandbox_id"]
    manager.release_current_sandbox("session-a", sandbox_id)

    await asyncio.sleep(0.05)

    assert manager.registry.get_sandbox(sandbox_id) is None
    assert provider.destroyed[0][1] == sandbox_id


@pytest.mark.asyncio
async def test_manager_cleanup_preserves_persistent_sandbox_records(
    tmp_path,
):
    manager, provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic")
    manager.update_sandbox_config(
        created["sandbox_id"],
        idle_timeout=None,
        expires_at=None,
        retention_policy="persistent",
    )

    await manager.cleanup_managed_sandboxes()

    assert manager.registry.get_sandbox(created["sandbox_id"])["status"] == "running"
    assert provider.destroyed == []


def test_manager_update_sandbox_config_rejects_duplicate_name(tmp_path):
    manager, _provider = _manager(tmp_path)
    first = manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="First",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "First"},
    )
    second = manager.registry.upsert_sandbox(
        sandbox_id="generic-2",
        sandbox_name="Second",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Second"},
    )

    with pytest.raises(RuntimeError, match="Sandbox name 'First' already exists"):
        manager.update_sandbox_config(
            second["sandbox_id"],
            sandbox_name=first["sandbox_name"],
            idle_timeout=None,
            expires_at=None,
            retention_policy="temporary",
        )


def test_manager_update_sandbox_config_rejects_persistent_for_unsupported_provider(
    tmp_path,
):
    manager, provider = _manager(tmp_path)
    provider.supports_persistent_reconnect = False
    created = manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="First",
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "First"},
    )

    with pytest.raises(
        RuntimeError, match="Provider generic does not support persistent sandboxes"
    ):
        manager.update_sandbox_config(
            created["sandbox_id"],
            sandbox_name=created["sandbox_name"],
            idle_timeout=None,
            expires_at=None,
            retention_policy="persistent",
        )


def test_manager_update_sandbox_config_rejects_persistent_for_missing_provider(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)
    created = manager.registry.upsert_sandbox(
        sandbox_id="missing-1",
        sandbox_name="Missing",
        booter_type="missing",
        provider="missing",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Missing"},
    )

    with pytest.raises(RuntimeError, match="Provider missing is not available"):
        manager.update_sandbox_config(
            created["sandbox_id"],
            sandbox_name=created["sandbox_name"],
            idle_timeout=None,
            expires_at=None,
            retention_policy="persistent",
        )


def test_manager_save_registry_propagates_write_failures(tmp_path):
    manager, _provider = _manager(tmp_path)

    def fail_save():
        raise OSError("disk full")

    manager.registry.save = fail_save

    with pytest.raises(OSError, match="disk full"):
        manager.save_registry()


@pytest.mark.asyncio
async def test_manager_save_registry_async_propagates_write_failures(tmp_path):
    manager, _provider = _manager(tmp_path)

    async def fail_save_async():
        raise OSError("disk full")

    manager.registry.save_async = fail_save_async

    with pytest.raises(OSError, match="disk full"):
        await manager.save_registry_async()


@pytest.mark.asyncio
async def test_manager_observer_access_does_not_refresh_idle_timer_for_unclaimed_sandbox(
    tmp_path,
):
    provider = FakeProvider()
    provider.idle_timeout = 30
    manager, _provider = _manager(tmp_path, provider)
    created = await manager.create_sandbox(None, "session-a", "generic")
    manager.release_current_sandbox("session-a", created["sandbox_id"])
    first_state = manager.idle_state[created["sandbox_id"]]
    first_last_used_at = manager.registry.get_sandbox(created["sandbox_id"])[
        "last_used_at"
    ]

    await manager.get_observer_booter_by_id(
        created["sandbox_id"], "dashboard", require_lease=False
    )

    second_state = manager.idle_state[created["sandbox_id"]]
    second_last_used_at = manager.registry.get_sandbox(created["sandbox_id"])[
        "last_used_at"
    ]
    assert second_state is first_state
    assert second_last_used_at == first_last_used_at
