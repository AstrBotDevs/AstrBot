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


def _manager(tmp_path, provider=None):
    provider = provider or FakeProvider()
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )
    return manager, provider


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
async def test_manager_cleanup_preserves_persistent_sandbox_records(tmp_path):
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
