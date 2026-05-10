import asyncio
import time

import pytest


class FakeBooter:
    async def available(self):
        return True

    async def shutdown(self):
        pass


class FakeProvider:
    provider_id = "generic"
    capabilities = {"shell"}
    tool_names = {"generic_tool"}
    system_prompt = "Use provider-specific sandbox rules."

    def __init__(self):
        self.created = []

    def build_create_config(self, context, session_id):
        return {}

    def build_connect_info(self, sandbox_name, config):
        return {"name": sandbox_name}

    def update_connect_info(self, record, *, sandbox_name):
        return {"name": sandbox_name}

    def get_idle_timeout(self, context, session_id):
        return 0

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.created.append((session_id, sandbox_id, config))
        return FakeBooter()

    async def destroy_booter(self, booter, record):
        await booter.shutdown()


class OtherFakeProvider(FakeProvider):
    provider_id = "other"
    capabilities = {"filesystem", "python"}

    async def create_booter(self, context, session_id, sandbox_id, config):
        self.created.append((session_id, sandbox_id, config))
        return OtherFakeBooter()


class OtherFakeBooter(FakeBooter):
    pass


class FakeContext:
    def get_config(self, umo=None):
        return {
            "provider_settings": {
                "computer_use_runtime": "sandbox",
                "sandbox": {"booter": "generic"},
            }
        }


@pytest.mark.asyncio
async def test_registered_generic_provider_handles_booter(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    provider = FakeProvider()
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    monkeypatch.setattr(computer_client, "sandbox_registry", manager.registry)
    monkeypatch.setattr(computer_client, "_sync_skills_to_sandbox", lambda booter: None)

    computer_client.register_sandbox_provider(provider)
    booter = await computer_client.get_booter(FakeContext(), "session-a")

    assert isinstance(booter, FakeBooter)
    assert computer_client.list_sandbox_providers() == [
        {
            "provider_id": "generic",
            "capabilities": ["shell"],
            "tool_names": ["generic_tool"],
            "system_prompt": "Use provider-specific sandbox rules.",
        }
    ]


def test_register_sandbox_provider_tags_provider_tools(monkeypatch, tmp_path):
    from astrbot.core.agent.tool import FunctionTool
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    monkeypatch.setattr(computer_client, "sandbox_registry", manager.registry)
    tool = FunctionTool(
        name="generic_tool",
        parameters={"type": "object", "properties": {}},
        description="generic",
    )

    computer_client.register_sandbox_provider(FakeProvider(), tools=[tool])

    assert tool.sandbox_provider_id == "generic"


@pytest.mark.asyncio
async def test_get_booter_prefers_current_sandbox_over_configured_provider(
    monkeypatch, tmp_path
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    generic = FakeProvider()
    other = OtherFakeProvider()
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={generic.provider_id: generic, other.provider_id: other},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    monkeypatch.setattr(computer_client, "sandbox_registry", manager.registry)
    current = await manager.create_sandbox(None, "session-a", "other")

    booter = await computer_client.get_booter(FakeContext(), "session-a")

    assert isinstance(booter, OtherFakeBooter)
    assert manager.registry.get_current_sandbox_id("session-a") == current["sandbox_id"]
    assert len(generic.created) == 0


@pytest.mark.asyncio
async def test_get_booter_renews_current_sandbox_lease(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    generic = FakeProvider()
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={generic.provider_id: generic},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    monkeypatch.setattr(computer_client, "sandbox_registry", manager.registry)
    current = await manager.create_sandbox(None, "session-a", "generic")
    manager.registry._payload["sandboxes"][current["sandbox_id"]][
        "lease_expires_at"
    ] = time.time() - 1

    await computer_client.get_booter(FakeContext(), "session-a")

    renewed = manager.registry.get_sandbox(current["sandbox_id"])
    assert renewed["controller_session_id"] == "session-a"
    assert renewed["lease_expires_at"] > time.time()


def test_computer_client_does_not_expose_legacy_session_cache():
    from astrbot.core.computer import computer_client

    assert not hasattr(computer_client, "session_booter")


@pytest.mark.asyncio
async def test_sync_skills_uses_active_manager_booters(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)

    synced = []

    async def fake_sync(booter):
        synced.append(booter)

    manager_booter = FakeBooter()
    manager.session_booter["generic-1"] = manager_booter
    monkeypatch.setattr(computer_client, "_sync_skills_to_sandbox", fake_sync)

    await computer_client.sync_skills_to_active_sandboxes()

    assert synced == [manager_booter]


def test_register_provider_rejects_duplicate_by_default(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)

    computer_client.register_sandbox_provider(FakeProvider())

    with pytest.raises(RuntimeError, match="already registered"):
        computer_client.register_sandbox_provider(FakeProvider())


def test_computer_client_does_not_load_registry_on_import(monkeypatch):
    import importlib

    import astrbot.core.computer.sandbox_registry as sandbox_registry_module

    loads = []
    original_class = sandbox_registry_module.SandboxRegistry

    class TrackingSandboxRegistry(original_class):
        def load(self):
            loads.append(self.storage_path)

    monkeypatch.setattr(
        sandbox_registry_module, "SandboxRegistry", TrackingSandboxRegistry
    )

    import astrbot.core.computer.computer_client as computer_client_module

    importlib.reload(computer_client_module)

    assert loads == []


def test_register_provider_can_replace_when_requested(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    replacement = FakeProvider()
    replacement.capabilities = {"keyboard", "mouse"}

    computer_client.register_sandbox_provider(FakeProvider())
    computer_client.register_sandbox_provider(replacement, replace=True)

    assert computer_client.get_sandbox_provider_info("generic") == {
        "provider_id": "generic",
        "capabilities": ["keyboard", "mouse"],
        "tool_names": ["generic_tool"],
        "system_prompt": "Use provider-specific sandbox rules.",
    }


def test_unregister_provider_rejects_active_managed_sandboxes(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    computer_client.register_sandbox_provider(FakeProvider())
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic 1",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )

    with pytest.raises(RuntimeError, match="active managed sandboxes"):
        computer_client.unregister_sandbox_provider("generic")


def test_unregister_provider_allows_force(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    computer_client.register_sandbox_provider(FakeProvider())
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic 1",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )

    computer_client.unregister_sandbox_provider("generic", force=True)

    assert computer_client.get_sandbox_provider_info("generic") is None


def test_unregister_provider_force_preserves_persistent_sandboxes(
    monkeypatch, tmp_path
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    computer_client.register_sandbox_provider(FakeProvider())
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic 1",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        retention_policy="persistent",
        status="running",
    )
    manager.session_booter["generic-1"] = object()

    computer_client.unregister_sandbox_provider("generic", force=True)

    record = manager.registry.get_sandbox("generic-1")
    assert record is not None
    assert record["retention_policy"] == "persistent"
    assert computer_client.get_sandbox_provider_info("generic") is None
    assert "generic-1" not in manager.session_booter


@pytest.mark.asyncio
async def test_unregister_provider_force_closes_persistent_booters(
    monkeypatch, tmp_path
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    closed = []

    class PersistentBooter:
        async def shutdown(self):
            closed.append("shutdown")

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)
    computer_client.register_sandbox_provider(FakeProvider())
    manager.registry.upsert_sandbox(
        sandbox_id="generic-1",
        sandbox_name="Generic 1",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        retention_policy="persistent",
        status="running",
    )
    manager.session_booter["generic-1"] = PersistentBooter()

    computer_client.unregister_sandbox_provider("generic", force=True)
    await asyncio.sleep(0)

    record = manager.registry.get_sandbox("generic-1")
    assert record is not None
    assert record["retention_policy"] == "persistent"
    assert "generic-1" not in manager.session_booter
    assert closed == []


def test_list_sandbox_providers_is_sorted(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)

    computer_client.register_sandbox_provider(OtherFakeProvider())
    computer_client.register_sandbox_provider(FakeProvider())

    assert computer_client.list_sandbox_providers() == [
        {
            "provider_id": "generic",
            "capabilities": ["shell"],
            "tool_names": ["generic_tool"],
            "system_prompt": "Use provider-specific sandbox rules.",
        },
        {
            "provider_id": "other",
            "capabilities": ["filesystem", "python"],
            "tool_names": ["generic_tool"],
            "system_prompt": "Use provider-specific sandbox rules.",
        },
    ]


@pytest.mark.asyncio
async def test_cleanup_registered_sandbox_manager(monkeypatch, tmp_path):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    provider = FakeProvider()
    destroyed = []

    async def fake_destroy_booter(booter, record):
        destroyed.append(record["sandbox_id"])
        await booter.shutdown()

    provider.destroy_booter = fake_destroy_booter
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)

    await manager.create_sandbox(None, "session-a", "generic")
    await computer_client.cleanup_managed_sandboxes()

    assert manager.list_sandboxes() == []


@pytest.mark.asyncio
async def test_cleanup_sandbox_provider_destroys_temporary_and_preserves_persistent_records(
    monkeypatch, tmp_path
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    provider = FakeProvider()
    destroyed = []

    async def fake_destroy_booter(booter, record):
        destroyed.append(record["sandbox_id"])
        await booter.shutdown()

    provider.destroy_booter = fake_destroy_booter
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)

    temporary = manager.registry.upsert_sandbox(
        sandbox_id="generic-temp",
        sandbox_name="Temp",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
        retention_policy="temporary",
        status="running",
    )
    persistent = manager.registry.upsert_sandbox(
        sandbox_id="generic-persistent",
        sandbox_name="Persistent",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-b",
        owner_session_id="session-b",
        connect_info={},
        retention_policy="persistent",
        status="running",
    )
    temp_booter = FakeBooter()
    temp_booter.provider_id = provider.provider_id
    persistent_booter = FakeBooter()
    persistent_booter.provider_id = provider.provider_id
    manager.session_booter[temporary["sandbox_id"]] = temp_booter
    manager.session_booter[persistent["sandbox_id"]] = persistent_booter

    await computer_client.cleanup_sandbox_provider("generic")

    assert manager.registry.get_sandbox("generic-temp") is None
    assert manager.registry.get_sandbox("generic-persistent") is not None
    assert destroyed == ["generic-temp"]


@pytest.mark.asyncio
async def test_cleanup_sandbox_provider_cleans_live_booter_without_registry_record(
    monkeypatch, tmp_path
):
    from astrbot.core.computer import computer_client
    from astrbot.core.computer.sandbox_manager import SandboxManager
    from astrbot.core.computer.sandbox_registry import SandboxRegistry

    provider = FakeProvider()
    destroyed = []

    async def fake_destroy_booter(booter, record):
        destroyed.append(record["sandbox_id"])
        await booter.shutdown()

    provider.destroy_booter = fake_destroy_booter
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)

    booter = FakeBooter()
    booter.provider_id = provider.provider_id
    manager.session_booter["generic-orphan"] = booter

    await computer_client.cleanup_sandbox_provider("generic")

    assert destroyed == ["generic-orphan"]
    assert manager.session_booter == {}


@pytest.mark.asyncio
async def test_core_lifecycle_stop_cleans_up_temporary_managed_sandboxes(monkeypatch):
    from types import SimpleNamespace

    from astrbot.core.core_lifecycle import AstrBotCoreLifecycle

    cleaned = []

    async def fake_cleanup_managed_sandboxes():
        cleaned.append("called")

    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.cleanup_managed_sandboxes",
        fake_cleanup_managed_sandboxes,
    )

    lifecycle = object.__new__(AstrBotCoreLifecycle)
    lifecycle.temp_dir_cleaner = None
    lifecycle.curr_tasks = []
    lifecycle.cron_manager = None
    lifecycle.provider_manager = SimpleNamespace(terminate=lambda: None)
    lifecycle.platform_manager = SimpleNamespace(terminate=lambda: None)
    lifecycle.kb_manager = SimpleNamespace(terminate=lambda: None)
    lifecycle.dashboard_shutdown_event = SimpleNamespace(set=lambda: None)
    lifecycle.plugin_manager = SimpleNamespace(
        context=SimpleNamespace(get_all_stars=lambda: []),
        _terminate_plugin=lambda plugin: None,
    )

    async def provider_terminate():
        return None

    async def platform_terminate():
        return None

    async def kb_terminate():
        return None

    async def terminate_plugin(plugin):
        return None

    lifecycle.provider_manager.terminate = provider_terminate
    lifecycle.platform_manager.terminate = platform_terminate
    lifecycle.kb_manager.terminate = kb_terminate
    lifecycle.plugin_manager._terminate_plugin = terminate_plugin

    await AstrBotCoreLifecycle.stop(lifecycle)

    assert cleaned == ["called"]
