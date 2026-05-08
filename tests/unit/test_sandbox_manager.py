import asyncio
import time

import pytest

from astrbot.core.computer.sandbox_manager import SandboxIdleState, SandboxManager
from astrbot.core.computer.sandbox_registry import SandboxRegistry


class FakeContext:
    def __init__(self, config: dict | None = None):
        self._config = config or {"provider_settings": {"sandbox": {}}}

    def get_config(self, umo: str | None = None):
        return self._config


class FakeProvider:
    provider_id = "fake"

    def __init__(self):
        self.boots = []
        self.shutdowns = []

    def build_create_config(self, context, session_id):
        return {"image": "fake"}

    def build_connect_info(self, sandbox_name, config):
        return {"kind": "fake", "name": sandbox_name}

    def get_idle_timeout(self, context, session_id):
        return 7.0

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.boots.append((session_id, sandbox_id, config))
        return FakeBooter(sandbox_id, self)

    async def destroy_booter(self, booter, record):
        self.shutdowns.append(booter.sandbox_id)


class FailingProvider(FakeProvider):
    async def create_booter(self, context, session_id, sandbox_id, config):
        self.boots.append((session_id, sandbox_id, config))
        raise RuntimeError("boot failed")


class FailingDestroyProvider(FakeProvider):
    async def destroy_booter(self, booter, record):
        self.shutdowns.append(booter.sandbox_id)
        raise RuntimeError("shutdown failed")


class PreleasedProvider(FakeProvider):
    async def create_booter(self, context, session_id, sandbox_id, config):
        context.registry.takeover_lease(
            sandbox_id=sandbox_id,
            session_id="other-session",
            user_id="other-session",
            ttl=60,
        )
        return await super().create_booter(context, session_id, sandbox_id, config)


class FakeBooter:
    def __init__(
        self,
        sandbox_id: str,
        provider: FakeProvider,
        available: bool = True,
        available_error: Exception | None = None,
    ):
        self.sandbox_id = sandbox_id
        self.provider = provider
        self._available = available
        self._available_error = available_error

    async def available(self):
        if self._available_error is not None:
            raise self._available_error
        return self._available

    async def shutdown(self):
        self.provider.shutdowns.append(self.sandbox_id)


def _manager(tmp_path):
    provider = FakeProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})
    return manager, registry, provider


class RegistryContext(FakeContext):
    def __init__(self, registry: SandboxRegistry):
        super().__init__()
        self.registry = registry


@pytest.mark.asyncio
async def test_sandbox_manager_creates_default_and_current_sandbox(tmp_path):
    manager, registry, provider = _manager(tmp_path)

    booter = await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert booter.sandbox_id == registry.default_sandbox_id
    assert registry.get_current_sandbox_id("session-a") == booter.sandbox_id
    assert registry.get_sandbox(booter.sandbox_id)["connect_info"] == {
        "kind": "fake",
        "name": booter.sandbox_id,
    }
    assert registry.get_sandbox(booter.sandbox_id)["idle_timeout"] == 7.0
    assert provider.boots == [("session-a", booter.sandbox_id, {"image": "fake"})]


@pytest.mark.asyncio
async def test_sandbox_manager_create_sandbox_requires_control_lease(tmp_path):
    provider = PreleasedProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})

    with pytest.raises(RuntimeError, match="busy"):
        await manager.create_sandbox(RegistryContext(registry), "session-a", "fake")

    records = registry.list_sandboxes()
    assert len(records) == 1
    assert records[0]["controller_session_id"] == "other-session"
    assert registry.get_current_sandbox_id("session-a") is None


@pytest.mark.asyncio
async def test_sandbox_manager_serializes_same_session_default_boot(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    boot_started = asyncio.Event()
    release_boot = asyncio.Event()

    async def slow_create(context, session_id, sandbox_id, config):
        provider.boots.append((session_id, sandbox_id, config))
        boot_started.set()
        await release_boot.wait()
        return FakeBooter(sandbox_id, provider)

    provider.create_booter = slow_create

    task_one = asyncio.create_task(
        manager.get_or_create_booter(FakeContext(), "session-a", "fake")
    )
    await boot_started.wait()
    task_two = asyncio.create_task(
        manager.get_or_create_booter(FakeContext(), "session-a", "fake")
    )
    release_boot.set()

    booter_one, booter_two = await asyncio.gather(task_one, task_two)

    assert booter_one is booter_two
    assert len(provider.boots) == 1


def test_sandbox_manager_switch_releases_previous_current_lease(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    for sandbox_id in ("old", "new"):
        registry.upsert_sandbox(
            sandbox_id=sandbox_id,
            sandbox_name=sandbox_id,
            booter_type="fake",
            provider="fake",
            managed=True,
            created_by_astrbot=True,
            owner_user_id="session-a",
            owner_session_id="session-a",
            controller_user_id="session-a" if sandbox_id == "old" else None,
            controller_session_id="session-a" if sandbox_id == "old" else None,
            lease_expires_at=time.time() + 60 if sandbox_id == "old" else None,
            connect_info={},
        )
        manager.session_booter[sandbox_id] = FakeBooter(sandbox_id, provider)
    registry.set_current_sandbox_id("session-a", "old")

    manager.switch_current_sandbox("session-a", "new")

    assert registry.get_sandbox("old")["controller_session_id"] is None
    assert registry.get_sandbox("new")["controller_session_id"] == "session-a"


@pytest.mark.asyncio
async def test_sandbox_manager_checked_switch_rejects_unavailable_booter(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="target",
        sandbox_name="target",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )
    manager.session_booter["target"] = FakeBooter("target", provider, available=False)

    with pytest.raises(RuntimeError, match="not running"):
        await manager.switch_current_sandbox_checked("session-a", "target")

    assert registry.get_current_sandbox_id("session-a") is None
    assert registry.get_sandbox("target")["controller_session_id"] is None


@pytest.mark.asyncio
async def test_sandbox_manager_observer_marks_unknown_on_availability_error(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="target",
        sandbox_name="target",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )
    manager.session_booter["target"] = FakeBooter(
        "target", provider, available_error=RuntimeError("availability failed")
    )

    with pytest.raises(RuntimeError, match="availability failed"):
        await manager.get_observer_booter_by_id("target")

    assert registry.get_sandbox("target")["status"] == "unknown"


@pytest.mark.asyncio
async def test_sandbox_manager_clears_stale_current_before_fallback(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.set_current_sandbox_id("session-a", "missing")

    booter = await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert registry.get_current_sandbox_id("session-a") == booter.sandbox_id
    assert booter.sandbox_id != "missing"


@pytest.mark.asyncio
async def test_sandbox_manager_clears_wrong_provider_current_before_fallback(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="neo-current",
        sandbox_name="neo",
        booter_type="shipyard_neo",
        provider="shipyard_neo",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-neo",
        owner_session_id="session-neo",
        connect_info={},
    )
    registry.set_current_sandbox_id("session-a", "neo-current")

    booter = await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert registry.get_current_sandbox_id("session-a") == booter.sandbox_id
    assert booter.sandbox_id != "neo-current"


@pytest.mark.asyncio
async def test_sandbox_manager_checked_switch_releases_previous_current_lease(
    tmp_path,
):
    manager, registry, provider = _manager(tmp_path)
    for sandbox_id in ("old", "new"):
        registry.upsert_sandbox(
            sandbox_id=sandbox_id,
            sandbox_name=sandbox_id,
            booter_type="fake",
            provider="fake",
            managed=True,
            created_by_astrbot=True,
            owner_user_id="session-a",
            owner_session_id="session-a",
            controller_user_id="session-a" if sandbox_id == "old" else None,
            controller_session_id="session-a" if sandbox_id == "old" else None,
            lease_expires_at=time.time() + 60 if sandbox_id == "old" else None,
            connect_info={},
        )
        manager.session_booter[sandbox_id] = FakeBooter(sandbox_id, provider)
    registry.set_current_sandbox_id("session-a", "old")

    await manager.switch_current_sandbox_checked("session-a", "new")

    assert registry.get_sandbox("old")["controller_session_id"] is None
    assert registry.get_sandbox("new")["controller_session_id"] == "session-a"
    assert registry.get_current_sandbox_id("session-a") == "new"


@pytest.mark.asyncio
async def test_sandbox_manager_destroy_prunes_boot_lock(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="sb-lock",
        sandbox_name="lock",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )
    manager._sandbox_boot_lock("sb-lock")

    await manager.destroy_sandbox("session-a", "sb-lock")

    assert "sb-lock" not in manager.boot_locks


@pytest.mark.asyncio
async def test_sandbox_manager_cleans_registry_when_default_boot_fails(tmp_path):
    provider = FailingProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})

    with pytest.raises(RuntimeError, match="boot failed"):
        await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert registry.list_sandboxes() == []
    assert registry.default_sandbox_id is None
    assert manager.session_booter == {}


@pytest.mark.asyncio
async def test_sandbox_manager_preserves_existing_record_when_boot_fails(tmp_path):
    provider = FailingProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})
    registry.upsert_sandbox(
        sandbox_id="existing",
        sandbox_name="existing",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        is_default=True,
        retention_policy="persistent",
        status="unknown",
    )

    with pytest.raises(RuntimeError, match="boot failed"):
        await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    record = registry.get_sandbox("existing")
    assert record is not None
    assert record["status"] == "unknown"
    assert record["controller_session_id"] is None
    assert registry.default_sandbox_id == "existing"


@pytest.mark.asyncio
async def test_sandbox_manager_ignores_default_for_other_provider(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="neo-default",
        sandbox_name="neo",
        booter_type="shipyard_neo",
        provider="shipyard_neo",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-neo",
        owner_session_id="session-neo",
        connect_info={},
        is_default=True,
    )

    booter = await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert booter.sandbox_id != "neo-default"
    assert registry.get_sandbox(booter.sandbox_id)["provider"] == "fake"
    assert provider.boots == [("session-a", booter.sandbox_id, {"image": "fake"})]


@pytest.mark.asyncio
async def test_sandbox_manager_reports_unsupported_provider_on_destroy(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="neo",
        sandbox_name="neo",
        booter_type="shipyard_neo",
        provider="shipyard_neo",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-neo",
        owner_session_id="session-neo",
        connect_info={},
    )
    manager.session_booter["neo"] = FakeBooter("neo", provider)

    with pytest.raises(RuntimeError, match="Provider shipyard_neo is not supported"):
        await manager.destroy_sandbox("session-a", "neo")

    assert manager.session_booter["neo"].sandbox_id == "neo"
    assert registry.get_sandbox("neo") is not None


@pytest.mark.asyncio
async def test_sandbox_manager_keeps_record_when_idle_shutdown_fails(tmp_path):
    provider = FailingDestroyProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})
    registry.upsert_sandbox(
        sandbox_id="idle",
        sandbox_name="idle",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        idle_timeout=0.001,
        last_used_at=time.time() - 10,
    )
    manager.session_booter["idle"] = FakeBooter("idle", provider)
    expires_at = time.monotonic()
    marker_task = asyncio.create_task(asyncio.sleep(0))
    manager.idle_state["idle"] = SandboxIdleState(
        expires_at=expires_at,
        task=marker_task,
    )

    await manager._expire_when_idle("idle", 0.001, expires_at)
    await marker_task

    record = registry.get_sandbox("idle")
    assert record is not None
    assert record["status"] == "unknown"
    assert manager.session_booter["idle"].sandbox_id == "idle"


@pytest.mark.asyncio
async def test_sandbox_manager_preserves_booter_when_destroy_shutdown_fails(tmp_path):
    provider = FailingDestroyProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})
    registry.upsert_sandbox(
        sandbox_id="target",
        sandbox_name="target",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )
    manager.session_booter["target"] = FakeBooter("target", provider)

    with pytest.raises(RuntimeError, match="shutdown failed"):
        await manager.destroy_sandbox("session-a", "target")

    assert manager.session_booter["target"].sandbox_id == "target"
    assert registry.get_sandbox("target") is not None


@pytest.mark.asyncio
async def test_sandbox_manager_keeps_cleanup_record_when_shutdown_fails(tmp_path):
    provider = FailingDestroyProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})
    registry.upsert_sandbox(
        sandbox_id="target",
        sandbox_name="target",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )
    manager.session_booter["target"] = FakeBooter("target", provider)

    await manager.cleanup_managed_sandboxes()

    record = registry.get_sandbox("target")
    assert record is not None
    assert record["status"] == "unknown"
    assert manager.session_booter["target"].sandbox_id == "target"


@pytest.mark.asyncio
async def test_sandbox_manager_releases_lease_when_availability_check_fails(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="current",
        sandbox_name="current",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )
    registry.set_current_sandbox_id("session-a", "current")
    manager.session_booter["current"] = FakeBooter(
        "current", provider, available_error=RuntimeError("availability failed")
    )

    with pytest.raises(RuntimeError, match="availability failed"):
        await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert registry.get_sandbox("current")["controller_session_id"] is None


@pytest.mark.asyncio
async def test_sandbox_manager_releases_target_lease_when_availability_check_fails(
    tmp_path,
):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="target",
        sandbox_name="target",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        is_default=True,
    )
    manager.session_booter["target"] = FakeBooter(
        "target", provider, available_error=RuntimeError("availability failed")
    )

    with pytest.raises(RuntimeError, match="availability failed"):
        await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert registry.get_sandbox("target")["controller_session_id"] is None


@pytest.mark.asyncio
async def test_sandbox_manager_cleanup_continues_after_unsupported_provider(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="neo",
        sandbox_name="neo",
        booter_type="shipyard_neo",
        provider="shipyard_neo",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-neo",
        owner_session_id="session-neo",
        connect_info={},
    )
    registry.upsert_sandbox(
        sandbox_id="fake",
        sandbox_name="fake",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )
    manager.session_booter["fake"] = FakeBooter("fake", provider)

    await manager.cleanup_managed_sandboxes()

    assert registry.get_sandbox("neo")["status"] == "unknown"
    assert registry.get_sandbox("fake") is None


@pytest.mark.asyncio
async def test_sandbox_manager_marks_unknown_record_running_after_boot(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="existing",
        sandbox_name="existing",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        is_default=True,
        status="unknown",
    )

    await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert registry.get_sandbox("existing")["status"] == "running"


@pytest.mark.asyncio
async def test_sandbox_manager_recreates_unavailable_cached_default_booter(tmp_path):
    manager, registry, provider = _manager(tmp_path)
    registry.upsert_sandbox(
        sandbox_id="existing",
        sandbox_name="existing",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        is_default=True,
    )
    manager.session_booter["existing"] = FakeBooter(
        "existing", provider, available=False
    )

    booter = await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert booter is manager.session_booter["existing"]
    assert booter._available is True
    assert provider.boots == [("session-a", "existing", {"image": "fake"})]
    assert registry.get_sandbox("existing")["controller_session_id"] == "session-a"


@pytest.mark.asyncio
async def test_sandbox_manager_releases_lease_before_recreating_unavailable_target(
    tmp_path,
):
    provider = FailingProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})
    registry.upsert_sandbox(
        sandbox_id="existing",
        sandbox_name="existing",
        booter_type="fake",
        provider="fake",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        is_default=True,
    )
    manager.session_booter["existing"] = FakeBooter(
        "existing", provider, available=False
    )

    with pytest.raises(RuntimeError, match="boot failed"):
        await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    record = registry.get_sandbox("existing")
    assert record is not None
    assert record["status"] == "unknown"
    assert record["controller_session_id"] is None
