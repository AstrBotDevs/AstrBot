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

    def build_create_config(self, context, session_id):
        return {}

    def build_connect_info(self, sandbox_name, config):
        return {"name": sandbox_name}

    def update_connect_info(self, record, *, sandbox_name):
        return {"name": sandbox_name}

    def get_idle_timeout(self, context, session_id):
        return 0

    async def create_booter(self, context, session_id, sandbox_id, config):
        return FakeBooter()

    async def destroy_booter(self, booter, record):
        await booter.shutdown()


class OtherFakeProvider(FakeProvider):
    provider_id = "other"
    capabilities = {"filesystem", "python"}


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
        booter_type="generic",
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
        booter_type="generic",
        provider="generic",
        managed=True,
        created_by_astrbot=True,
        owner_user_id="session-a",
        owner_session_id="session-a",
        connect_info={},
    )

    computer_client.unregister_sandbox_provider("generic", force=True)

    assert computer_client.get_sandbox_provider_info("generic") is None


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
    manager = SandboxManager(
        registry=SandboxRegistry(tmp_path / "sandbox_registry.json"),
        providers={provider.provider_id: provider},
    )
    monkeypatch.setattr(computer_client, "sandbox_manager", manager)

    await manager.create_sandbox(None, "session-a", "generic")
    await computer_client.cleanup_managed_sandboxes()

    assert manager.list_sandboxes() == []


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
