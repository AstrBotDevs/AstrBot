import asyncio
import time

import pytest

from astrbot.core.computer.sandbox_manager import SandboxManager
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

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.boots.append((session_id, sandbox_id, config))
        return FakeBooter(sandbox_id, self)

    async def destroy_booter(self, booter, record):
        self.shutdowns.append(booter.sandbox_id)


class FakeBooter:
    def __init__(self, sandbox_id: str, provider: FakeProvider):
        self.sandbox_id = sandbox_id
        self.provider = provider

    async def available(self):
        return True

    async def shutdown(self):
        self.provider.shutdowns.append(self.sandbox_id)


def _manager(tmp_path):
    provider = FakeProvider()
    registry = SandboxRegistry(storage_path=tmp_path / "registry.json")
    manager = SandboxManager(registry=registry, providers={"fake": provider})
    return manager, registry, provider


@pytest.mark.asyncio
async def test_sandbox_manager_creates_default_and_current_sandbox(tmp_path):
    manager, registry, provider = _manager(tmp_path)

    booter = await manager.get_or_create_booter(FakeContext(), "session-a", "fake")

    assert booter.sandbox_id == registry.default_sandbox_id
    assert registry.get_current_sandbox_id("session-a") == booter.sandbox_id
    assert provider.boots == [("session-a", booter.sandbox_id, {"image": "fake"})]


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
