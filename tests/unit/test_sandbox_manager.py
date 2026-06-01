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


class BaseDefaultAvailableBooter:
    pass


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

    def build_create_config(self, context, session_id):
        return {"session_id": session_id}

    def build_connect_info(self, sandbox_name, config):
        return {"name": sandbox_name, **config}

    def update_connect_info(self, record, *, sandbox_name):
        info = dict(record.get("connect_info") or {})
        info["name"] = sandbox_name
        return info

    async def create_booter(self, context, session_id, sandbox_id, config):
        booter = FakeBooter()
        self.created.append((session_id, sandbox_id, booter, config))
        return booter

    async def destroy_booter(self, booter, record):
        self.destroyed.append((booter, record["sandbox_id"]))
        await booter.shutdown()


class FakeContext:
    def __init__(self, sandbox_config=None):
        self._sandbox_config = sandbox_config or {}

    def get_config(self, umo):
        return {"provider_settings": {"sandbox": dict(self._sandbox_config)}}


class RecordCapturingProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.boot_started = asyncio.Event()
        self.allow_boot = asyncio.Event()
        self.destroyed_records = []

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.boot_started.set()
        await self.allow_boot.wait()
        return await super().create_booter(context, session_id, sandbox_id, config)

    async def destroy_booter(self, booter, record):
        self.destroyed_records.append(dict(record))
        await super().destroy_booter(booter, record)


class SaveFailingProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.destroyed = []


class OtherFakeProvider(FakeProvider):
    provider_id = "other"


class BlockingDestroyProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.destroy_started = asyncio.Event()
        self.allow_destroy = asyncio.Event()

    async def destroy_booter(self, booter, record):
        self.destroy_started.set()
        await self.allow_destroy.wait()
        return await super().destroy_booter(booter, record)


class ImmediateDestroyProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.destroy_started = asyncio.Event()

    async def destroy_booter(self, booter, record):
        self.destroy_started.set()
        await super().destroy_booter(booter, record)


class SlowCreatedHookProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.hook_started = asyncio.Event()
        self.allow_hook = asyncio.Event()
        self.hook_calls = 0

    async def on_sandbox_created(self, record):
        self.hook_calls += 1
        self.hook_started.set()
        await self.allow_hook.wait()


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


class SlowDeferredDestroyProvider(DeferredBootProvider):
    def __init__(self):
        super().__init__()
        self.cancelled_during_boot = asyncio.Event()
        self.destroy_started = asyncio.Event()
        self.allow_destroy = asyncio.Event()
        self.pause_destroy = False

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.boot_started.set()
        try:
            await self.allow_boot.wait()
        except asyncio.CancelledError:
            self.cancelled_during_boot.set()
            await self.allow_boot.wait()
        if self.raise_on_boot:
            raise RuntimeError("boot failed")
        return await FakeProvider.create_booter(
            self, context, session_id, sandbox_id, config
        )

    async def destroy_booter(self, booter, record):
        self.destroy_started.set()
        if self.pause_destroy:
            await self.allow_destroy.wait()
        return await super().destroy_booter(booter, record)


class DeadIdleDestroyProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.destroy_started = asyncio.Event()
        self.destroy_calls = 0

    async def destroy_booter(self, booter, record):
        self.destroy_calls += 1
        self.destroy_started.set()
        booter.available_result = False
        raise RuntimeError("half-closed booter")


class AlwaysFailingIdleDestroyProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.destroy_started = asyncio.Event()
        self.destroy_calls = 0

    async def destroy_booter(self, booter, record):
        self.destroy_calls += 1
        self.destroy_started.set()
        raise RuntimeError("destroy failed")


class FailingReconnectProvider(FakeProvider):
    async def create_booter(self, context, session_id, sandbox_id, config):
        raise RuntimeError("boot failed")


class AlwaysBusyManager(SandboxManager):
    def acquire_lease(self, sandbox_id: str, session_id: str, *, ttl=None):
        return False


class MissingPersistentProvider(FakeProvider):
    async def check_persistent_sandbox_exists(self, record):
        return False


class PruningMissingPersistentProvider(MissingPersistentProvider):
    prune_missing_persistent_records = True


class ExistingPersistentProvider(FakeProvider):
    async def check_persistent_sandbox_exists(self, record):
        return True


class ContextCapturingProvider(FakeProvider):
    def __init__(self):
        super().__init__()
        self.contexts = []

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.contexts.append(context)
        return await super().create_booter(context, session_id, sandbox_id, config)


class ConnectInfoAfterBootProvider(FakeProvider):
    def update_connect_info_after_boot(self, record, booter):
        info = dict(record.get("connect_info") or {})
        info["runtime_id"] = getattr(booter, "runtime_id", "runtime-1")
        return info


def _manager(tmp_path, provider=None):
    provider = provider or FakeProvider()
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )
    return manager, provider


async def wait_until(predicate, *, timeout: float = 1.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(0.01)
    raise AssertionError("condition was not met before timeout")


def test_manager_list_sandboxes_preserves_persisted_tool_names_without_provider(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic",
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


def test_manager_list_sandboxes_does_not_emit_legacy_booter_type(tmp_path):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Generic"},
    )

    sandboxes = manager.list_sandboxes()

    assert sandboxes[0]["provider"] == "generic"
    assert "booter_type" not in sandboxes[0]


def test_manager_list_sandboxes_migrates_legacy_booter_type_to_provider(tmp_path):
    manager, _provider = _manager(tmp_path)
    manager.registry._payload["sandboxes"]["legacy-1"] = {
        "sandbox_id": "legacy-1",
        "sandbox_name": "Legacy",
        "booter_type": "generic",
        "managed": True,
        "created_by_astrbot": True,
        "connect_info": {"name": "Legacy"},
    }

    sandboxes = manager.list_sandboxes()

    assert sandboxes[0]["provider"] == "generic"
    assert "booter_type" not in sandboxes[0]


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
async def test_create_sandbox_uncontrolled_cleans_up_on_cancellation(tmp_path):
    provider = DeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    task = asyncio.create_task(
        manager.create_sandbox_uncontrolled(None, "session-a", "generic", "Named")
    )
    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    records = manager.registry.list_sandboxes()
    assert len(records) == 1
    assert records[0]["status"] == "error"
    assert manager.session_booter == {}


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_keeps_error_record_on_boot_failure(
    tmp_path,
):
    provider = FailingReconnectProvider()
    manager, _provider = _manager(tmp_path, provider)

    with pytest.raises(RuntimeError, match="boot failed"):
        await manager.create_sandbox_uncontrolled(None, "session-a", "generic", "Named")

    records = manager.registry.list_sandboxes()
    assert len(records) == 1
    assert records[0]["sandbox_name"] == "Named"
    assert records[0]["status"] == "error"
    assert manager.session_booter == {}


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_rejects_duplicate_name(tmp_path):
    manager, _provider = _manager(tmp_path)

    await manager.create_sandbox_uncontrolled(None, "session-a", "generic", "Named")

    with pytest.raises(RuntimeError, match="Sandbox name 'Named' already exists"):
        await manager.create_sandbox_uncontrolled(None, "session-a", "generic", "Named")


@pytest.mark.asyncio
async def test_create_sandbox_respects_global_max_sandboxes(tmp_path):
    manager, _provider = _manager(tmp_path)
    context = FakeContext({"max_sandboxes": 1})

    await manager.create_sandbox(context, "session-a", "generic")

    with pytest.raises(RuntimeError, match="Sandbox limit reached"):
        await manager.create_sandbox(context, "session-b", "generic")


@pytest.mark.asyncio
async def test_get_or_create_booter_respects_global_max_sandboxes(tmp_path):
    manager, _provider = _manager(tmp_path)
    context = FakeContext({"max_sandboxes": 1})

    await manager.get_or_create_booter(context, "session-a", "generic")

    with pytest.raises(RuntimeError, match="Sandbox limit reached"):
        await manager.get_or_create_booter(context, "session-b", "generic")


@pytest.mark.asyncio
async def test_create_sandbox_uses_default_max_sandboxes_when_config_missing(tmp_path):
    manager, _provider = _manager(tmp_path)
    context = FakeContext({})
    for index in range(10):
        await manager.create_sandbox(context, f"session-{index}", "generic")

    with pytest.raises(RuntimeError, match="Maximum managed sandboxes: 10"):
        await manager.create_sandbox(context, "session-over-limit", "generic")


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
async def test_create_sandbox_uncontrolled_passes_sandbox_id_to_connect_info(tmp_path):
    manager, _provider = _manager(tmp_path)

    sandbox = await manager.create_sandbox_uncontrolled(
        None, "session-a", "generic", "Display Name"
    )

    assert sandbox["sandbox_name"] == "Display Name"
    assert sandbox["connect_info"]["name"] == "Display Name"
    assert sandbox["connect_info"]["sandbox_id"] == sandbox["sandbox_id"]


@pytest.mark.asyncio
async def test_create_sandbox_updates_connect_info_after_boot(tmp_path):
    provider = ConnectInfoAfterBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled(
        None, "session-a", "generic", "Display Name"
    )

    assert sandbox["connect_info"]["runtime_id"] == "runtime-1"


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_deferred_passes_sandbox_id_to_connect_info(
    tmp_path,
):
    provider = DeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Display Name"
    )

    assert sandbox["sandbox_name"] == "Display Name"
    assert sandbox["connect_info"]["name"] == "Display Name"
    assert sandbox["connect_info"]["sandbox_id"] == sandbox["sandbox_id"]

    provider.allow_boot.set()
    await asyncio.wait_for(manager.pending_boot_tasks[sandbox["sandbox_id"]], timeout=1)


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
    await wait_until(
        lambda: (
            (record := manager.registry.get_sandbox(sandbox["sandbox_id"])) is not None
            and record["status"] == "running"
        )
    )

    assert manager.registry.get_sandbox(sandbox["sandbox_id"])["status"] == "running"
    assert sandbox["sandbox_id"] in manager.session_booter


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_deferred_tracks_pending_boot_task(
    tmp_path,
):
    provider = DeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    task = manager.pending_boot_tasks.get(sandbox["sandbox_id"])
    assert task is not None
    assert not task.done()

    provider.allow_boot.set()
    await asyncio.wait_for(task, timeout=1)
    assert sandbox["sandbox_id"] not in manager.pending_boot_tasks


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_deferred_delays_boot_past_next_loop_turn(
    tmp_path,
):
    provider = DeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    assert sandbox["status"] == "creating"
    assert not provider.boot_started.is_set()
    await asyncio.sleep(0)
    assert not provider.boot_started.is_set()

    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)


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
    await wait_until(
        lambda: (
            (record := manager.registry.get_sandbox(sandbox["sandbox_id"])) is not None
            and record["status"] == "error"
        )
    )

    record = manager.registry.get_sandbox(sandbox["sandbox_id"])
    assert record is not None
    assert record["status"] == "error"
    assert sandbox["sandbox_id"] not in manager.session_booter


@pytest.mark.asyncio
async def test_create_sandbox_uncontrolled_deferred_uses_fresh_record_for_cleanup(
    tmp_path,
):
    provider = RecordCapturingProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)
    manager.registry.delete_sandbox(sandbox["sandbox_id"])
    provider.allow_boot.set()

    await wait_until(lambda: not manager.pending_boot_tasks)

    assert provider.destroyed_records == [{}]
    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None
    assert sandbox["sandbox_id"] not in manager.session_booter


@pytest.mark.asyncio
async def test_manager_waits_for_current_creating_sandbox_instead_of_creating_another_one(
    tmp_path,
):
    class CountingDeferredBootProvider(DeferredBootProvider):
        def __init__(self):
            super().__init__()
            self.create_calls = 0
            self.second_create_started = asyncio.Event()

        async def create_booter(self, context, session_id, sandbox_id, config):
            self.create_calls += 1
            if self.create_calls == 2:
                self.second_create_started.set()
            return await super().create_booter(context, session_id, sandbox_id, config)

    provider = CountingDeferredBootProvider()
    manager, _provider = _manager(tmp_path, provider)

    created = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )
    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)
    manager.registry.set_current_sandbox_id("session-a", created["sandbox_id"])

    get_booter_task = asyncio.create_task(
        manager.get_or_create_booter(None, "session-a", "generic")
    )
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(get_booter_task, timeout=0.1)

    assert len(manager.registry.list_sandboxes()) == 1
    assert provider.create_calls == 1
    assert created["sandbox_id"] in manager.pending_boot_tasks

    provider.allow_boot.set()
    await wait_until(lambda: created["sandbox_id"] in manager.session_booter)
    booter = await manager.get_or_create_booter(None, "session-a", "generic")

    assert booter is manager.session_booter[created["sandbox_id"]]
    assert len(provider.created) == 1


@pytest.mark.asyncio
async def test_create_sandbox_rolls_back_when_lease_acquisition_fails(tmp_path):
    provider = FakeProvider()
    manager = AlwaysBusyManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )

    with pytest.raises(RuntimeError, match="Sandbox .* is busy"):
        await manager.create_sandbox(None, "session-a", "generic", "Named")

    assert manager.registry.list_sandboxes() == []
    assert manager.session_booter == {}
    assert provider.destroyed and provider.destroyed[0][1].startswith("generic-")


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
async def test_destroy_sandbox_waits_for_deferred_boot_lock_before_cleanup(tmp_path):
    provider = SlowDeferredDestroyProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)
    destroy_task = asyncio.create_task(
        manager.destroy_sandbox("session-a", sandbox["sandbox_id"])
    )

    await asyncio.wait_for(provider.cancelled_during_boot.wait(), timeout=1)
    assert not destroy_task.done()

    provider.allow_boot.set()
    destroyed = await asyncio.wait_for(destroy_task, timeout=1)

    await asyncio.sleep(0.05)

    assert destroyed["sandbox_id"] == sandbox["sandbox_id"]
    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None
    assert sandbox["sandbox_id"] not in manager.session_booter
    assert sandbox["sandbox_id"] not in manager.pending_boot_tasks


@pytest.mark.asyncio
async def test_destroy_sandbox_waits_for_deferred_boot_lock_after_cancel_timeout(
    tmp_path,
):
    provider = SlowDeferredDestroyProvider()
    manager, _provider = _manager(tmp_path, provider)

    sandbox = await manager.create_sandbox_uncontrolled_deferred(
        None, "session-a", "generic", "Named"
    )

    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)
    destroy_task = asyncio.create_task(
        manager.destroy_sandbox("session-a", sandbox["sandbox_id"])
    )

    await asyncio.wait_for(provider.cancelled_during_boot.wait(), timeout=1)
    await asyncio.sleep(1.1)
    assert not destroy_task.done()

    provider.allow_boot.set()
    destroyed = await asyncio.wait_for(destroy_task, timeout=1)

    assert destroyed["sandbox_id"] == sandbox["sandbox_id"]
    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None
    assert sandbox["sandbox_id"] not in manager.session_booter
    assert sandbox["sandbox_id"] not in manager.pending_boot_tasks


@pytest.mark.asyncio
async def test_destroy_persistent_sandbox_removes_record(tmp_path):
    manager, provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")
    manager.update_sandbox_config(
        created["sandbox_id"],
        idle_timeout=None,
        expires_at=None,
        retention_policy="persistent",
    )

    destroyed = await manager.destroy_sandbox("session-a", created["sandbox_id"])

    assert destroyed["sandbox_id"] == created["sandbox_id"]
    assert manager.registry.get_sandbox(created["sandbox_id"]) is None
    assert provider.destroyed[0][1] == created["sandbox_id"]


@pytest.mark.asyncio
async def test_destroy_sandbox_deferred_returns_stopping_before_background_delete(
    tmp_path,
):
    provider = BlockingDestroyProvider()
    manager, _provider = _manager(tmp_path, provider)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")

    destroyed = await asyncio.wait_for(
        manager.destroy_sandbox_deferred("session-a", created["sandbox_id"]),
        timeout=1,
    )

    assert destroyed["status"] == "stopping"
    assert destroyed["sandbox_id"] == created["sandbox_id"]
    await asyncio.wait_for(provider.destroy_started.wait(), timeout=1)

    record = manager.registry.get_sandbox(created["sandbox_id"])
    assert record is not None
    assert record["status"] == "stopping"

    provider.allow_destroy.set()
    await wait_until(
        lambda: manager.registry.get_sandbox(created["sandbox_id"]) is None
    )

    assert manager.registry.get_sandbox(created["sandbox_id"]) is None
    assert provider.destroyed[0][1] == created["sandbox_id"]


@pytest.mark.asyncio
async def test_destroy_sandbox_deferred_delays_cleanup_past_next_loop_turn(tmp_path):
    provider = ImmediateDestroyProvider()
    manager, _provider = _manager(tmp_path, provider)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")

    destroyed = await manager.destroy_sandbox_deferred(
        "session-a", created["sandbox_id"]
    )

    assert destroyed["status"] == "stopping"
    assert not provider.destroy_started.is_set()
    await asyncio.sleep(0)
    assert not provider.destroy_started.is_set()

    await asyncio.wait_for(provider.destroy_started.wait(), timeout=1)


@pytest.mark.asyncio
async def test_destroy_sandbox_deferred_tracks_pending_destroy_task(tmp_path):
    provider = BlockingDestroyProvider()
    manager, _provider = _manager(tmp_path, provider)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")

    destroyed = await manager.destroy_sandbox_deferred(
        "session-a", created["sandbox_id"]
    )

    task = manager.pending_destroy_tasks.get(destroyed["sandbox_id"])
    assert task is not None
    assert not task.done()

    provider.allow_destroy.set()
    await asyncio.wait_for(task, timeout=1)
    assert destroyed["sandbox_id"] not in manager.pending_destroy_tasks


@pytest.mark.asyncio
async def test_created_hook_second_call_does_not_wait_for_first_hook(tmp_path):
    provider = SlowCreatedHookProvider()
    manager, _provider = _manager(tmp_path, provider)
    created = await manager.create_sandbox_uncontrolled(
        None, "session-a", "generic", "Named"
    )

    first = asyncio.create_task(
        manager._invoke_sandbox_created_hook(provider, created["sandbox_id"])
    )
    await asyncio.wait_for(provider.hook_started.wait(), timeout=1)

    second = asyncio.create_task(
        manager._invoke_sandbox_created_hook(provider, created["sandbox_id"])
    )
    await asyncio.sleep(0)

    assert second.done()
    assert not first.done()
    assert provider.hook_calls == 1

    provider.allow_hook.set()
    await asyncio.wait_for(first, timeout=1)


@pytest.mark.asyncio
async def test_clear_runtime_state_keeps_held_boot_lock(tmp_path):
    manager, _provider = _manager(tmp_path)
    sandbox_id = "generic-1"

    async with manager._sandbox_boot_lock(sandbox_id):
        held_lock = manager.boot_locks[sandbox_id]
        manager.clear_runtime_state(sandbox_id)

        assert manager.boot_locks[sandbox_id] is held_lock


@pytest.mark.asyncio
async def test_takeover_sandbox_keeps_held_boot_lock_on_health_failure(tmp_path):
    manager, _provider = _manager(tmp_path)
    sandbox_id = "generic-1"
    manager.registry.upsert_sandbox(
        sandbox_id=sandbox_id,
        sandbox_name="Sandbox",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Sandbox"},
        status="running",
    )
    booter = FakeBooter()
    booter.available_result = False
    manager.session_booter[sandbox_id] = booter

    async with manager._sandbox_boot_lock(sandbox_id):
        held_lock = manager.boot_locks[sandbox_id]

        with pytest.raises(RuntimeError, match="booter health check failed"):
            await manager.takeover_sandbox("session-b", sandbox_id)

        assert manager.boot_locks[sandbox_id] is held_lock


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
async def test_get_or_create_booter_rolls_back_on_registry_save_failure(tmp_path):
    provider = FakeProvider()
    manager, _provider = _manager(tmp_path, provider)
    save_calls = 0

    async def fail_save():
        nonlocal save_calls
        save_calls += 1
        if save_calls > 1:
            raise RuntimeError("disk full")

    manager.save_registry_async = fail_save

    with pytest.raises(RuntimeError, match="disk full"):
        await manager.get_or_create_booter(None, "session-a", "generic")

    assert manager.session_booter == {}
    assert provider.destroyed


@pytest.mark.asyncio
async def test_manager_creates_new_sandbox_when_default_busy(tmp_path):
    manager, provider = _manager(tmp_path)

    await manager.get_or_create_booter(None, "session-a", "generic")
    await manager.get_or_create_booter(None, "session-b", "generic")

    assert len(provider.created) == 2
    assert len(manager.list_sandboxes()) == 2


@pytest.mark.asyncio
async def test_manager_reuses_idle_provider_sandbox_when_default_busy(tmp_path):
    manager, provider = _manager(tmp_path)

    default = await manager.create_sandbox(None, "session-a", "generic", "Default")
    idle = await manager.create_sandbox(None, "session-b", "generic", "Reusable")
    manager.release_current_sandbox("session-b", idle["sandbox_id"])

    booter = await manager.get_or_create_booter(None, "session-c", "generic")

    current_id = manager.get_current_sandbox("session-c")["current_sandbox_id"]
    assert current_id == idle["sandbox_id"]
    assert booter is manager.session_booter[idle["sandbox_id"]]
    assert len(provider.created) == 2
    assert (
        manager.registry.get_sandbox(default["sandbox_id"])["controller_session_id"]
        == "session-a"
    )


def test_manager_treats_expired_lease_sandbox_as_idle(tmp_path):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Expired",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Expired"},
        status="running",
        controller_user_id="session-a",
        controller_session_id="session-a",
        lease_expires_at=time.time() - 1,
    )
    manager.session_booter["generic-1"] = FakeBooter()

    assert manager._find_idle_provider_sandbox_id("generic") == "generic-1"


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
async def test_get_or_create_booter_does_not_reuse_stopping_current_sandbox(tmp_path):
    manager, provider = _manager(tmp_path)
    first = await manager.create_sandbox(None, "session-a", "generic", "Stopping")
    first_id = first["sandbox_id"]
    first_booter = manager.session_booter[first_id]
    manager.registry.update_sandbox_status(first_id, "stopping")

    next_booter = await manager.get_or_create_booter(None, "session-a", "generic")

    assert next_booter is not first_booter
    assert manager.get_current_sandbox("session-a")["current_sandbox_id"] != first_id
    assert len(provider.created) == 2


@pytest.mark.asyncio
async def test_get_or_create_booter_revives_persistent_unknown_default(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-persistent",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent", "persistent_name": "persist-1"},
        status="unknown",
        retention_policy="persistent",
        is_default=True,
    )
    manager.registry.set_default_sandbox_id("generic-persistent")

    await manager.get_or_create_booter(object(), "session-a", "generic")

    assert len(provider.created) == 1
    assert provider.created[0][3]["resume"] is True
    assert provider.created[0][3]["persistent_name"] == "persist-1"


@pytest.mark.asyncio
async def test_get_or_create_booter_passes_persistent_host_port(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-persistent",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={
            "name": "Persistent",
            "persistent_name": "persist-1",
            "host_port": 23456,
        },
        status="unknown",
        retention_policy="persistent",
        is_default=True,
    )
    manager.registry.set_default_sandbox_id("generic-persistent")

    await manager.get_or_create_booter(object(), "session-a", "generic")

    assert provider.created[0][3]["host_port"] == 23456


@pytest.mark.asyncio
async def test_get_or_create_booter_defaults_to_temporary_retention(tmp_path):
    manager, _provider = _manager(tmp_path)

    await manager.get_or_create_booter(None, "session-a", "generic")

    sandbox_id = manager.get_current_sandbox("session-a")["current_sandbox_id"]
    record = manager.registry.get_sandbox(sandbox_id)
    assert record["retention_policy"] == "temporary"


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
    assert manager.get_current_sandbox("session-a")["current_sandbox_id"] is None

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
async def test_manager_get_or_create_releases_previous_cross_provider_sandbox(tmp_path):
    first_provider = FakeProvider()
    second_provider = OtherFakeProvider()
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={
            first_provider.provider_id: first_provider,
            second_provider.provider_id: second_provider,
        },
    )

    first = await manager.create_sandbox(None, "session-a", "generic", "First")
    await manager.get_or_create_booter(None, "session-a", "other")

    first_record = manager.registry.get_sandbox(first["sandbox_id"])
    current_id = manager.get_current_sandbox("session-a")["current_sandbox_id"]
    current_record = manager.registry.get_sandbox(current_id)
    assert first_record["controller_session_id"] is None
    assert first_record["lease_expires_at"] is None
    assert current_record["provider"] == "other"
    assert current_record["controller_session_id"] == "session-a"


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
async def test_manager_takeover_uses_configured_lease_timeout(tmp_path):
    manager, _provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")

    taken = await manager.takeover_sandbox(
        "session-b",
        created["sandbox_id"],
        context=FakeContext({"sandbox_lease_timeout": 12}),
    )

    assert taken["controller_session_id"] == "session-b"
    assert taken["lease_expires_at"] > time.time() + 10
    assert taken["lease_expires_at"] < time.time() + 20


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
async def test_manager_renews_current_sandbox_lease_with_requested_ttl(tmp_path):
    manager, _provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")

    renewed = await manager.renew_current_sandbox_lease("session-a", ttl_seconds=7200)

    assert renewed["sandbox_id"] == created["sandbox_id"]
    assert renewed["controller_session_id"] == "session-a"
    assert renewed["lease_expires_at"] > time.time() + 7190


@pytest.mark.asyncio
async def test_manager_renew_current_sandbox_rejects_missing_current(tmp_path):
    manager, _provider = _manager(tmp_path)

    with pytest.raises(RuntimeError, match="No current sandbox"):
        await manager.renew_current_sandbox_lease("session-a")


@pytest.mark.asyncio
async def test_manager_renew_current_sandbox_allows_zero_ttl_for_permanent_lease(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)
    await manager.create_sandbox(None, "session-a", "generic", "Named")

    renewed = await manager.renew_current_sandbox_lease("session-a", ttl_seconds=0)

    assert renewed["controller_session_id"] == "session-a"
    assert renewed["lease_expires_at"] is None


@pytest.mark.asyncio
async def test_manager_renew_current_sandbox_rejects_non_finite_ttl(tmp_path):
    manager, _provider = _manager(tmp_path)
    await manager.create_sandbox(None, "session-a", "generic", "Named")

    with pytest.raises(RuntimeError, match="ttl_seconds must be finite"):
        await manager.renew_current_sandbox_lease("session-a", ttl_seconds=float("inf"))


@pytest.mark.asyncio
async def test_manager_uses_configured_lease_timeout_for_new_sandboxes(tmp_path):
    manager, _provider = _manager(tmp_path)

    created = await manager.create_sandbox(
        FakeContext({"sandbox_lease_timeout": 12}),
        "session-a",
        "generic",
        "Named",
    )

    assert created["lease_expires_at"] > time.time() + 10


@pytest.mark.asyncio
async def test_manager_list_sandboxes_exposes_exact_cleanup_times(tmp_path):
    manager, _provider = _manager(tmp_path)

    idle_created = await manager.create_sandbox(
        FakeContext({"sandbox_idle_timeout": 30, "sandbox_ttl": 0}),
        "session-a",
        "generic",
        "Idle",
    )
    ttl_created = await manager.create_sandbox(
        FakeContext({"sandbox_idle_timeout": 0, "sandbox_ttl": 120}),
        "session-b",
        "generic",
        "TTL",
    )
    listed = {item["sandbox_id"]: item for item in manager.list_sandboxes()}

    assert idle_created["expires_at"] is None
    assert listed[idle_created["sandbox_id"]]["idle_cleanup_at"] is None
    manager.release_current_sandbox("session-a", idle_created["sandbox_id"])
    idle_listed = {item["sandbox_id"]: item for item in manager.list_sandboxes()}[
        idle_created["sandbox_id"]
    ]
    assert idle_listed["idle_cleanup_at"] == pytest.approx(
        idle_listed["last_used_at"] + idle_listed["idle_timeout"], abs=0.01
    )
    assert ttl_created["expires_at"] > time.time() + 110
    assert listed[ttl_created["sandbox_id"]]["idle_cleanup_at"] is None


@pytest.mark.asyncio
async def test_manager_ttl_cleanup_removes_temporary_sandbox_when_idle_cleanup_disabled(
    tmp_path,
):
    manager, provider = _manager(tmp_path)

    sandbox = await manager.create_sandbox(
        FakeContext({"sandbox_idle_timeout": 0, "sandbox_ttl": 0.01}),
        "session-a",
        "generic",
        "TTL",
    )

    await asyncio.sleep(0.05)

    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None
    assert provider.destroyed[0][1] == sandbox["sandbox_id"]


@pytest.mark.asyncio
async def test_manager_renew_current_sandbox_rejects_non_running_sandbox(tmp_path):
    manager, _provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")
    manager.session_booter.pop(created["sandbox_id"])
    manager.registry.update_sandbox_status(created["sandbox_id"], "error")

    with pytest.raises(RuntimeError, match="encountered an error"):
        await manager.renew_current_sandbox_lease("session-a")

    assert (
        manager.get_current_sandbox("session-a")["current_sandbox_id"]
        == created["sandbox_id"]
    )


@pytest.mark.asyncio
async def test_manager_renew_current_sandbox_rejects_unavailable_booter(tmp_path):
    manager, _provider = _manager(tmp_path)
    created = await manager.create_sandbox(None, "session-a", "generic", "Named")
    booter = manager.session_booter[created["sandbox_id"]]
    booter.available_result = False

    with pytest.raises(RuntimeError, match="is not running"):
        await manager.renew_current_sandbox_lease("session-a")

    assert created["sandbox_id"] not in manager.session_booter
    assert manager.registry.get_sandbox(created["sandbox_id"])["status"] == "unknown"


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

    with pytest.raises(RuntimeError, match="not found"):
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
async def test_manager_marks_persistent_reconnect_as_restoring(tmp_path):
    provider = RecordCapturingProvider()
    manager, _provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="unknown",
        retention_policy="persistent",
    )

    task = asyncio.create_task(
        manager.get_observer_booter_by_id(
            "generic-1", "dashboard", require_lease=False, context=object()
        )
    )
    await asyncio.wait_for(provider.boot_started.wait(), timeout=1)

    assert manager.registry.get_sandbox("generic-1")["status"] == "restoring"

    provider.allow_boot.set()
    await task
    assert manager.registry.get_sandbox("generic-1")["status"] == "running"


@pytest.mark.asyncio
async def test_manager_treats_base_available_stub_as_available(tmp_path):
    manager, _provider = _manager(tmp_path)
    assert await manager.booter_available(BaseDefaultAvailableBooter()) is True


@pytest.mark.asyncio
async def test_manager_persistent_health_failure_marks_unknown_for_retry(tmp_path):
    manager, _provider = _manager(tmp_path)
    booter = FakeBooter()
    booter.available_result = False
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )
    manager.session_booter["generic-1"] = booter

    with pytest.raises(RuntimeError, match="booter health check failed"):
        await manager.get_observer_booter_by_id(
            "generic-1", "dashboard", require_lease=False, context=object()
        )

    assert manager.registry.get_sandbox("generic-1")["status"] == "unknown"
    assert "generic-1" not in manager.session_booter


@pytest.mark.asyncio
async def test_manager_revives_persistent_sandbox_for_tool_access(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
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
    provider = FakeProvider()
    manager, provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
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
    assert "generic-1" not in manager.idle_state


@pytest.mark.asyncio
async def test_manager_reconcile_on_startup_removes_stale_persistent_records(
    tmp_path,
):
    provider = PruningMissingPersistentProvider()
    manager, provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
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
async def test_manager_reconcile_on_startup_keeps_unconfirmed_persistent_records_by_default(
    tmp_path,
):
    provider = MissingPersistentProvider()
    manager, provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
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
async def test_manager_reconcile_on_startup_clears_all_runtime_state(tmp_path):
    manager, _provider = _manager(tmp_path)
    manager.session_booter["stale-1"] = FakeBooter()
    manager._sandbox_boot_lock("stale-1")
    manager.schedule_idle_cleanup("stale-1", 30)
    manager.registry.save()

    await manager.reconcile_on_startup()

    assert manager.session_booter == {}
    assert manager.idle_state == {}
    assert manager.boot_locks == {}


@pytest.mark.asyncio
async def test_manager_reconcile_on_startup_waits_for_pending_destroy_tasks(tmp_path):
    manager, provider = _manager(tmp_path, BlockingDestroyProvider())
    sandbox = await manager.create_sandbox(None, "session-a", "generic", "Named")
    task = asyncio.create_task(
        manager.destroy_sandbox_deferred("session-a", sandbox["sandbox_id"])
    )
    await asyncio.wait_for(provider.destroy_started.wait(), timeout=1)
    provider.allow_destroy.set()

    await manager.reconcile_on_startup()
    await task

    assert sandbox["sandbox_id"] not in manager.pending_destroy_tasks
    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None


@pytest.mark.asyncio
async def test_manager_reconcile_on_startup_keeps_persistent_records_for_missing_provider(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="missing-1",
        sandbox_name="Persistent",
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

    record = manager.registry.get_sandbox("missing-1")
    assert record is not None
    assert record["status"] == "unknown"


@pytest.mark.asyncio
async def test_manager_takeover_rejects_non_running_sandbox(tmp_path):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Broken",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Broken"},
        status="error",
    )

    with pytest.raises(RuntimeError, match="encountered an error"):
        await manager.takeover_sandbox("session-b", "generic-1")

    record = manager.registry.get_sandbox("generic-1")
    assert record["controller_session_id"] is None


@pytest.mark.asyncio
async def test_manager_takeover_revives_persistent_sandbox_with_context(tmp_path):
    provider = ContextCapturingProvider()
    manager, provider = _manager(tmp_path, provider)
    context = FakeContext({})
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="unknown",
        retention_policy="persistent",
    )

    await manager.takeover_sandbox("session-b", "generic-1", context=context)

    assert provider.contexts == [context]
    assert "generic-1" in manager.session_booter


@pytest.mark.asyncio
async def test_manager_reconcile_on_startup_keeps_valid_persistent_records(
    tmp_path,
):
    provider = ExistingPersistentProvider()
    manager, provider = _manager(tmp_path, provider)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
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
async def test_manager_restore_persistent_sandboxes_times_out_and_keeps_record(
    tmp_path,
):
    provider = FailingReconnectProvider()
    manager, _provider = _manager(tmp_path, provider)
    restore_started = asyncio.Event()

    async def slow_create_booter(context, session_id, sandbox_id, config):
        restore_started.set()
        await asyncio.sleep(1)
        return await FakeProvider().create_booter(
            context, session_id, sandbox_id, config
        )

    provider.create_booter = slow_create_booter
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
    )

    restored, timed_out = await manager.restore_persistent_sandboxes(
        object(), per_sandbox_timeout=0.01
    )

    assert restore_started.is_set()
    assert restored == 0
    assert timed_out == 1
    record = manager.registry.get_sandbox("generic-1")
    assert record is not None
    assert record["status"] == "unknown"


def test_manager_reconcile_on_startup_marks_temporary_records_error(tmp_path):
    manager, _provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Temporary",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Temporary"},
        status="running",
        retention_policy="temporary",
    )

    manager.registry.save()
    manager.registry.reconcile_startup()

    record = manager.registry.get_sandbox("generic-1")
    assert record is not None
    assert record["status"] == "error"


@pytest.mark.asyncio
async def test_manager_idle_cleanup_removes_temporary_sandbox(tmp_path):
    manager, provider = _manager(tmp_path)
    context = FakeContext({"sandbox_idle_timeout": 0.01, "sandbox_ttl": 0})

    await manager.get_or_create_booter(context, "session-a", "generic")
    sandbox_id = manager.list_sandboxes()[0]["sandbox_id"]
    manager.release_current_sandbox("session-a", sandbox_id)

    await asyncio.sleep(0.05)

    assert manager.registry.get_sandbox(sandbox_id) is None
    assert provider.destroyed[0][1] == sandbox_id


@pytest.mark.asyncio
async def test_manager_idle_cleanup_uses_scheduled_monotonic_deadline(tmp_path):
    manager, provider = _manager(tmp_path)
    context = FakeContext({"sandbox_idle_timeout": 0.01, "sandbox_ttl": 0})

    sandbox = await manager.create_sandbox(context, "session-a", "generic", "Named")
    sandbox_id = sandbox["sandbox_id"]
    manager.release_current_sandbox("session-a", sandbox_id)
    manager.registry._payload["sandboxes"][sandbox_id]["last_used_at"] = (
        time.time() + 3600
    )

    await asyncio.sleep(0.05)

    assert manager.registry.get_sandbox(sandbox_id) is None
    assert provider.destroyed[0][1] == sandbox_id


@pytest.mark.asyncio
async def test_manager_idle_cleanup_ignores_persistent_sandbox(tmp_path):
    manager, provider = _manager(tmp_path)
    context = FakeContext({"sandbox_idle_timeout": 0.01, "sandbox_ttl": 0})

    sandbox = await manager.create_sandbox(context, "session-a", "generic", "Named")
    sandbox_id = sandbox["sandbox_id"]
    manager.update_sandbox_config(
        sandbox_id,
        idle_timeout=None,
        expires_at=None,
        retention_policy="persistent",
    )
    manager.release_current_sandbox("session-a", sandbox_id)

    await asyncio.sleep(0.05)

    record = manager.registry.get_sandbox(sandbox_id)
    assert record is not None
    assert record["status"] == "running"
    assert provider.destroyed == []


@pytest.mark.asyncio
async def test_manager_stale_idle_cleanup_task_skips_persistent_sandbox(tmp_path):
    manager, provider = _manager(tmp_path)
    manager.registry.upsert_sandbox(
        sandbox_id="persistent-1",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Persistent"},
        status="running",
        retention_policy="persistent",
        idle_timeout=0.01,
    )
    booter = FakeBooter()
    manager.session_booter["persistent-1"] = booter

    manager.schedule_idle_cleanup("persistent-1", 0.01)
    await asyncio.sleep(0.05)

    record = manager.registry.get_sandbox("persistent-1")
    assert record is not None
    assert record["status"] == "running"
    assert manager.session_booter["persistent-1"] is booter
    assert provider.destroyed == []


@pytest.mark.asyncio
async def test_manager_idle_cleanup_does_not_retry_dead_booter(tmp_path):
    provider = DeadIdleDestroyProvider()
    manager, provider = _manager(tmp_path, provider)
    context = FakeContext({"sandbox_idle_timeout": 0.01, "sandbox_ttl": 0})

    sandbox = await manager.create_sandbox(context, "session-a", "generic", "Named")
    manager.release_current_sandbox("session-a", sandbox["sandbox_id"])

    await asyncio.wait_for(provider.destroy_started.wait(), timeout=1)
    await asyncio.sleep(0.05)

    assert provider.destroy_calls == 1
    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None
    assert sandbox["sandbox_id"] not in manager.session_booter
    assert sandbox["sandbox_id"] not in manager.idle_state


@pytest.mark.asyncio
async def test_manager_idle_cleanup_stops_retrying_after_max_attempts(tmp_path):
    from astrbot.core.computer import sandbox_manager as sandbox_manager_module

    provider = AlwaysFailingIdleDestroyProvider()
    manager, provider = _manager(tmp_path, provider)
    context = FakeContext({"sandbox_idle_timeout": 0.01, "sandbox_ttl": 0})

    sandbox = await manager.create_sandbox(context, "session-a", "generic", "Named")
    manager.release_current_sandbox("session-a", sandbox["sandbox_id"])

    await asyncio.wait_for(provider.destroy_started.wait(), timeout=1)
    await asyncio.sleep(0.12)

    assert provider.destroy_calls == sandbox_manager_module.MAX_IDLE_DESTROY_ATTEMPTS
    record = manager.registry.get_sandbox(sandbox["sandbox_id"])
    assert record is not None
    assert record["status"] == "error"
    assert sandbox["sandbox_id"] in manager.session_booter
    assert sandbox["sandbox_id"] not in manager.idle_state


@pytest.mark.asyncio
async def test_manager_cleanup_waits_for_pending_destroy_tasks(tmp_path):
    manager, provider = _manager(tmp_path, BlockingDestroyProvider())

    sandbox = await manager.create_sandbox(None, "session-a", "generic", "Named")
    task = asyncio.create_task(
        manager.destroy_sandbox_deferred("session-a", sandbox["sandbox_id"])
    )
    await asyncio.wait_for(provider.destroy_started.wait(), timeout=1)
    provider.allow_destroy.set()

    await manager.cleanup_managed_sandboxes()

    await task
    assert sandbox["sandbox_id"] not in manager.pending_destroy_tasks
    assert manager.registry.get_sandbox(sandbox["sandbox_id"]) is None
    assert sandbox["sandbox_id"] not in manager.session_booter
    assert provider.destroyed[0][1] == sandbox["sandbox_id"]


@pytest.mark.asyncio
async def test_manager_cleanup_destroys_temporary_sandboxes_and_keeps_persistent_records(
    tmp_path,
):
    manager, provider = _manager(tmp_path)
    temporary = await manager.create_sandbox(None, "session-a", "generic")
    persistent = await manager.create_sandbox(None, "session-b", "generic")
    persistent_booter = manager.session_booter[persistent["sandbox_id"]]
    manager.update_sandbox_config(
        persistent["sandbox_id"],
        idle_timeout=None,
        expires_at=None,
        retention_policy="persistent",
    )

    await manager.cleanup_managed_sandboxes()

    assert manager.registry.get_sandbox(temporary["sandbox_id"]) is None
    assert manager.registry.get_sandbox(persistent["sandbox_id"])["status"] == "running"
    assert len(provider.destroyed) == 1
    assert provider.destroyed[0][1] == temporary["sandbox_id"]
    assert persistent_booter.shutdown_calls == 1


@pytest.mark.asyncio
async def test_manager_cleanup_clears_persistent_runtime_memory_state(tmp_path):
    manager, provider = _manager(tmp_path)
    persistent = await manager.create_sandbox(None, "session-a", "generic")
    persistent_booter = manager.session_booter[persistent["sandbox_id"]]
    manager.update_sandbox_config(
        persistent["sandbox_id"],
        idle_timeout=None,
        expires_at=None,
        retention_policy="persistent",
    )
    persistent_id = persistent["sandbox_id"]
    manager._sandbox_boot_lock(persistent_id)

    await manager.cleanup_managed_sandboxes()

    assert manager.registry.get_sandbox(persistent_id) is not None
    assert persistent_id not in manager.session_booter
    assert persistent_id not in manager.idle_state
    assert persistent_id not in manager.boot_locks
    assert provider.destroyed == []
    assert persistent_booter.shutdown_calls == 1


def test_manager_update_sandbox_config_rejects_duplicate_name(tmp_path):
    manager, _provider = _manager(tmp_path)
    first = manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="First",
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


@pytest.mark.asyncio
async def test_manager_update_sandbox_config_clears_expires_at_when_idle_enabled(
    tmp_path,
):
    manager, _provider = _manager(tmp_path)
    record = manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Generic"},
        idle_timeout=0,
        expires_at=time.time() + 3600,
    )

    updated = manager.update_sandbox_config(
        record["sandbox_id"],
        idle_timeout=30,
        expires_at=time.time() + 7200,
        retention_policy="temporary",
    )

    assert updated["idle_timeout"] == 30
    assert updated["expires_at"] is None
    assert record["sandbox_id"] in manager.idle_state
    assert record["sandbox_id"] not in manager.expiration_state


def test_manager_update_sandbox_config_rejects_persistent_for_unsupported_provider(
    tmp_path,
):
    manager, provider = _manager(tmp_path)
    provider.supports_persistent_reconnect = False
    created = manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="First",
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


@pytest.mark.asyncio
async def test_manager_set_sandbox_retention_policy_makes_sandbox_persistent(tmp_path):
    manager, _provider = _manager(tmp_path)
    record = manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Generic"},
        idle_timeout=30,
        expires_at=time.time() + 3600,
    )
    manager.schedule_idle_cleanup(record["sandbox_id"], 30)

    updated = manager.set_sandbox_retention_policy(
        FakeContext({"sandbox_idle_timeout": 30, "sandbox_ttl": 120}),
        "session-a",
        record["sandbox_id"],
        "persistent",
    )

    assert updated["retention_policy"] == "persistent"
    assert updated["idle_timeout"] is None
    assert updated["expires_at"] is None
    assert record["sandbox_id"] not in manager.idle_state
    assert record["sandbox_id"] not in manager.expiration_state


@pytest.mark.asyncio
async def test_manager_set_sandbox_retention_policy_makes_sandbox_temporary(tmp_path):
    manager, _provider = _manager(tmp_path)
    record = manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={"name": "Generic"},
        retention_policy="persistent",
    )

    updated = manager.set_sandbox_retention_policy(
        FakeContext({"sandbox_idle_timeout": 30, "sandbox_ttl": 120}),
        "session-a",
        record["sandbox_id"],
        "temporary",
    )

    assert updated["retention_policy"] == "temporary"
    assert updated["idle_timeout"] == 30
    assert updated["expires_at"] is None
    assert record["sandbox_id"] in manager.idle_state


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
    manager, _provider = _manager(tmp_path, provider)
    created = await manager.create_sandbox(
        FakeContext({"sandbox_idle_timeout": 30, "sandbox_ttl": 0}),
        "session-a",
        "generic",
    )
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
