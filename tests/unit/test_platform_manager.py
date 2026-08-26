import asyncio
from collections.abc import Coroutine
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import Platform, PlatformMetadata, discovery
from astrbot.core.platform.catalog import PlatformAdapterDescriptor, PlatformCatalog
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.send_result import PlatformSendResult
from astrbot.core.star.star import PluginRegistry
from astrbot.core.star.star_handler import HandlerRegistry
from astrbot.core.webchat.queue_manager import WebChatQueueManager

pytestmark = pytest.mark.platform


def _make_registries() -> tuple[HandlerRegistry, PluginRegistry]:
    plugins = PluginRegistry()
    return HandlerRegistry(plugins), plugins


def _make_metrics() -> SimpleNamespace:
    """Return a per-manager telemetry port without shared test state."""
    return SimpleNamespace(upload=AsyncMock())


def _make_manager() -> PlatformManager:
    return PlatformManager(
        {
            "platform": [],
            "platform_settings": {},
        },
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )


class _ConfigWithAsyncSave(dict):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.save_config_async = AsyncMock(return_value=True)


class _LifecycleFakeAdapter(Platform):
    """Controllable adapter used to exercise PlatformManager's real task paths."""

    instances: list[_LifecycleFakeAdapter] = []
    client_ids: list[str] = []

    @classmethod
    def reset(cls, client_ids: list[str] | None = None) -> None:
        cls.instances = []
        cls.client_ids = list(client_ids or [])

    def __init__(
        self,
        platform_config: dict,
        platform_settings: dict,
        event_queue: asyncio.Queue,
    ) -> None:
        super().__init__(platform_config, event_queue)
        del platform_settings
        self.client_self_id = (
            type(self).client_ids.pop(0)
            if type(self).client_ids
            else f"client-{len(type(self).instances)}"
        )
        self.run_started = asyncio.Event()
        self.run_cancelled = asyncio.Event()
        self.run_finished = asyncio.Event()
        self.allow_run_exit = asyncio.Event()
        self.terminate_started = asyncio.Event()
        self.allow_terminate = asyncio.Event()
        self.allow_terminate.set()
        self.background_started = asyncio.Event()
        self.background_cancelled = asyncio.Event()
        self.allow_background_exit = asyncio.Event()
        self.spawn_background_on_run_cancel = False
        self.late_background_started = asyncio.Event()
        self.late_background_cancelled = asyncio.Event()
        self.allow_late_background_exit = asyncio.Event()
        self.run_error: Exception | None = None
        self.terminate_error: Exception | None = None
        type(self).instances.append(self)

    async def _run(self) -> None:
        self.run_started.set()
        try:
            await self.allow_run_exit.wait()
            if self.run_error is not None:
                raise self.run_error
        except asyncio.CancelledError:
            self.run_cancelled.set()
            if self.spawn_background_on_run_cancel:
                self.start_late_background_task()
            raise
        finally:
            self.run_finished.set()

    def run(self) -> Coroutine[Any, Any, None]:
        return self._run()

    def meta(self) -> PlatformMetadata:
        return PlatformMetadata(
            name="lifecycle-fake",
            description="lifecycle fake adapter",
            id=self.config.get("id", "webchat"),
        )

    async def terminate(self) -> None:
        self.terminate_started.set()
        await self.allow_terminate.wait()
        if self.terminate_error is not None:
            raise self.terminate_error

    def start_background_task(self) -> asyncio.Task[None]:
        """Start auxiliary work without asking ``terminate`` to clean it up."""

        async def wait_in_background() -> None:
            self.background_started.set()
            try:
                await self.allow_background_exit.wait()
            except asyncio.CancelledError:
                self.background_cancelled.set()
                raise

        task = asyncio.create_task(wait_in_background(), name="lifecycle-background")
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    def start_late_background_task(self) -> asyncio.Task[None]:
        """Create tracked work from the run task's cancellation path."""

        async def wait_in_background() -> None:
            self.late_background_started.set()
            try:
                await self.allow_late_background_exit.wait()
            except asyncio.CancelledError:
                self.late_background_cancelled.set()
                raise

        task = asyncio.create_task(
            wait_in_background(),
            name="lifecycle-late-background",
        )
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task


def _install_lifecycle_adapter(monkeypatch, *, client_ids: list[str] | None = None):
    _LifecycleFakeAdapter.reset(client_ids)
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter",
        lambda _adapter_type, _catalog: _LifecycleFakeAdapter,
    )
    return _LifecycleFakeAdapter.instances


async def _cleanup_lifecycle_manager(
    manager: PlatformManager,
    instances: list[_LifecycleFakeAdapter],
) -> None:
    """Release every fake, including one an intentionally broken manager orphaned."""

    for inst in instances:
        inst.allow_terminate.set()
        inst.allow_run_exit.set()
        inst.allow_background_exit.set()
        inst.allow_late_background_exit.set()
        inst.run_error = None
        inst.terminate_error = None
    await manager.terminate()
    background_tasks = [
        task for inst in instances for task in list(inst._background_tasks)
    ]
    for task in background_tasks:
        task.cancel()
    await asyncio.gather(*background_tasks, return_exceptions=True)
    await asyncio.gather(
        *(inst.run_finished.wait() for inst in instances if inst.run_started.is_set())
    )


def test_platform_manager_sets_and_clears_concurrency_limit() -> None:
    manager = _make_manager()

    assert manager.get_platform_concurrency_limit("telegram") is None

    manager.set_platform_concurrency_limit("telegram", 2)
    assert manager.get_platform_concurrency_limit("telegram") == 2

    manager.set_platform_concurrency_limit("telegram", None)
    assert manager.get_platform_concurrency_limit("telegram") is None


def test_platform_manager_find_inst_by_name_returns_matching_adapter() -> None:
    manager = _make_manager()
    platform = MagicMock()
    platform.meta.return_value.name = "telegram"
    manager._platform_insts = [platform]

    result = manager._find_inst_by_name("telegram")

    assert result is platform


def test_platform_manager_get_platform_count_returns_loaded_adapter_count() -> None:
    manager = _make_manager()
    manager._platform_insts = [MagicMock(), MagicMock()]

    assert manager.get_platform_count() == 2


def test_platform_manager_find_inst_by_webhook_uuid_returns_only_unified_webhook():
    manager = _make_manager()
    matched = MagicMock()
    matched.config = {"webhook_uuid": "uuid-1"}
    matched.unified_webhook.return_value = True
    unmatched = MagicMock()
    unmatched.config = {"webhook_uuid": "uuid-1"}
    unmatched.unified_webhook.return_value = False
    manager._platform_insts = [unmatched, matched]

    result = manager.find_inst_by_webhook_uuid("uuid-1")

    assert result is matched


def test_platform_manager_rejects_invalid_concurrency_limit() -> None:
    manager = _make_manager()

    with pytest.raises(ValueError, match="platform concurrency limit must be >= 1"):
        manager.set_platform_concurrency_limit("telegram", 0)


@pytest.mark.asyncio
async def test_initialize_persists_webhook_defaults_before_loading_platform(
    monkeypatch,
):
    config = _ConfigWithAsyncSave(
        {
            "platform": [{"enable": False, "id": "bot", "type": "unused"}],
            "platform_settings": {},
        }
    )
    manager = PlatformManager(
        config,
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    transitions: list[str] = []

    async def persist() -> bool:
        transitions.append("persist")
        return True

    async def load(platform_config: dict) -> None:
        assert platform_config is config["platform"][0]
        transitions.append("load")

    class WebChatAdapter:
        def __init__(self, *_args) -> None:
            self.client_self_id = "webchat"

    config.save_config_async.side_effect = persist
    manager.load_platform = AsyncMock(side_effect=load)
    manager._start_platform_task = MagicMock()
    monkeypatch.setattr(
        "astrbot.core.platform.manager.ensure_platform_webhook_config",
        lambda _platform: True,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter",
        lambda _adapter_type, _catalog: WebChatAdapter,
    )

    await manager.initialize()

    config.save_config_async.assert_awaited_once()
    manager.load_platform.assert_awaited_once_with(config["platform"][0])
    assert transitions == ["persist", "load"]


@pytest.mark.asyncio
async def test_initialize_does_not_load_platform_when_webhook_save_is_superseded(
    monkeypatch,
):
    config = _ConfigWithAsyncSave(
        {
            "platform": [{"enable": True, "id": "bot", "type": "unused"}],
            "platform_settings": {},
        }
    )
    config.save_config_async.return_value = False
    manager = PlatformManager(
        config,
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    manager.load_platform = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.platform.manager.ensure_platform_webhook_config",
        lambda _platform: True,
    )

    with pytest.raises(RuntimeError, match="webhook configuration save was superseded"):
        await manager.initialize()

    manager.load_platform.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_platform_does_not_create_adapter_when_id_save_is_superseded(
    monkeypatch,
):
    config = _ConfigWithAsyncSave(
        {
            "platform": [{"enable": True, "id": "bot:legacy", "type": "unused"}],
            "platform_settings": {},
        }
    )
    config.save_config_async.return_value = False
    manager = PlatformManager(
        config,
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    discover = MagicMock()
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter",
        discover,
    )

    with pytest.raises(RuntimeError, match="ID migration save was superseded"):
        await manager.load_platform(config["platform"][0])

    discover.assert_not_called()
    assert manager._platform_insts == []
    assert config["platform"][0]["id"] == "bot:legacy"


@pytest.mark.asyncio
async def test_reload_keeps_existing_adapter_when_id_save_is_superseded(
    monkeypatch,
):
    config = _ConfigWithAsyncSave(
        {
            "platform": [
                {"enable": True, "id": "bot:legacy", "type": "unused"},
            ],
            "platform_settings": {},
        }
    )
    config.save_config_async.return_value = False
    manager = PlatformManager(
        config,
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    terminate = AsyncMock()
    manager._terminate_platform_unlocked = terminate
    discover = MagicMock()
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter",
        discover,
    )

    with pytest.raises(RuntimeError, match="ID migration save was superseded"):
        await manager.reload(config["platform"][0])

    terminate.assert_not_awaited()
    discover.assert_not_called()
    assert config["platform"][0]["id"] == "bot:legacy"


@pytest.mark.asyncio
async def test_platform_manager_injects_runtime_queue_into_declaring_adapter(
    monkeypatch,
):
    queue_manager = WebChatQueueManager()
    manager = PlatformManager(
        {"platform": [], "platform_settings": {}},
        asyncio.Queue(),
        queue_manager,
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    instances = []

    class WebChatAdapter:
        requires_webchat_queue_manager = True

        def __init__(
            self,
            _platform_config,
            _platform_settings,
            _event_queue,
            injected_queue_manager,
        ) -> None:
            self.client_self_id = "webchat"
            self.injected_queue_manager = injected_queue_manager
            instances.append(self)

    manager._start_platform_task = MagicMock()
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter",
        lambda _adapter_type, _catalog: WebChatAdapter,
    )

    await manager.initialize()

    assert instances[0].injected_queue_manager is queue_manager


def test_platform_manager_injects_scoped_handler_and_plugin_registries() -> None:
    handlers, plugins = _make_registries()
    metrics = _make_metrics()
    manager = PlatformManager(
        {"platform": [], "platform_settings": {}},
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        handlers,
        plugins,
        metrics=metrics,
    )
    _LifecycleFakeAdapter.reset()
    adapter = _LifecycleFakeAdapter({}, {}, asyncio.Queue())

    manager._configure_platform_instance(adapter)

    assert adapter.get_handler_registry() is handlers
    assert adapter.get_plugin_registry() is plugins
    assert adapter._metrics is metrics


@pytest.mark.asyncio
async def test_invalid_platform_id_is_persisted_before_adapter_starts(monkeypatch):
    config = _ConfigWithAsyncSave(
        {
            "platform": [
                {"enable": True, "id": "bot:one", "type": "fake-platform"},
            ],
            "platform_settings": {},
        }
    )
    manager = PlatformManager(
        config,
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    transitions: list[str] = []

    async def persist() -> bool:
        transitions.append("persist")
        return True

    class Adapter:
        def __init__(self, *_args) -> None:
            self.client_self_id = "bot"

    config.save_config_async.side_effect = persist
    manager._start_platform_task = MagicMock(
        side_effect=lambda *_args: transitions.append("start")
    )
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter",
        lambda _adapter_type, _catalog: Adapter,
    )
    await manager._load_platform_unlocked(config["platform"][0])

    assert config["platform"][0]["id"] == "bot_one"
    config.save_config_async.assert_awaited_once()
    assert transitions == ["persist", "start"]


@pytest.mark.asyncio
async def test_platform_manager_run_with_platform_limit_without_registered_limit():
    manager = _make_manager()

    async def operation() -> str:
        return "ok"

    result = await manager.run_with_platform_limit("telegram", operation)

    assert result == "ok"


@pytest.mark.asyncio
async def test_platform_manager_refreshes_native_commands_on_all_adapters(caplog):
    manager = _make_manager()
    healthy = MagicMock()
    healthy.refresh_registered_commands = AsyncMock()
    failing = MagicMock()
    failing.meta.return_value.name = "discord"
    failing.refresh_registered_commands = AsyncMock(
        side_effect=RuntimeError("sync failed")
    )
    manager._platform_insts = [healthy, failing]

    await manager.refresh_registered_commands()

    healthy.refresh_registered_commands.assert_awaited_once()
    failing.refresh_registered_commands.assert_awaited_once()
    assert "Failed to refresh native commands for platform discord" in caplog.text


@pytest.mark.asyncio
async def test_platform_manager_invoke_action_uses_registered_platform_limit():
    manager = _make_manager()
    manager.set_platform_concurrency_limit("telegram", 1)
    events: list[str] = []
    first_started = asyncio.Event()
    second_submitted = asyncio.Event()
    release = asyncio.Event()

    async def action_handler(*, value: str) -> dict[str, object]:
        events.append(f"start:{value}")
        if value == "first":
            first_started.set()
        await release.wait()
        events.append(f"end:{value}")
        return {"value": value}

    platform = MagicMock()
    platform.supports_action.return_value = True
    platform.some_action = action_handler
    manager._find_inst_by_id = MagicMock(return_value=platform)

    first = asyncio.create_task(
        manager.invoke_action("telegram", "some_action", value="first")
    )
    await first_started.wait()

    async def invoke_second() -> dict[str, object]:
        second_submitted.set()
        return await manager.invoke_action("telegram", "some_action", value="second")

    second = asyncio.create_task(invoke_second())
    await second_submitted.wait()

    assert events == ["start:first"]

    release.set()
    first_result = await first
    second_result = await second

    assert first_result == {"value": "first"}
    assert second_result == {"value": "second"}
    assert events == [
        "start:first",
        "end:first",
        "start:second",
        "end:second",
    ]


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_uses_registered_platform_limit():
    manager = _make_manager()
    manager.set_platform_concurrency_limit("telegram", 1)
    events: list[str] = []
    first_started = asyncio.Event()
    second_submitted = asyncio.Event()
    release = asyncio.Event()
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])

    async def send_by_session(_session, _chain) -> PlatformSendResult:
        events.append("start")
        if len(events) == 1:
            first_started.set()
        await release.wait()
        events.append("end")
        return PlatformSendResult(
            platform_id="telegram",
            success=True,
            target="chat-1",
            message_count=1,
        )

    platform = MagicMock()
    platform.send_by_session = AsyncMock(side_effect=send_by_session)
    manager._find_inst_by_id = MagicMock(return_value=platform)

    first = asyncio.create_task(manager.send_to_session(session, chain))
    await first_started.wait()

    async def send_second() -> PlatformSendResult:
        second_submitted.set()
        return await manager.send_to_session(session, chain)

    second = asyncio.create_task(send_second())
    await second_submitted.wait()

    assert events == ["start"]

    release.set()
    first_result = await first
    second_result = await second

    assert first_result.success is True
    assert second_result.success is True
    assert events == ["start", "end", "start", "end"]


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_returns_failure_when_missing():
    manager = _make_manager()
    manager._find_inst_by_id = MagicMock(return_value=None)
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])

    result = await manager.send_to_session(session, chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="platform adapter not found",
    )


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_normalizes_legacy_none_result():
    manager = _make_manager()
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])
    platform = MagicMock()
    platform.send_by_session = AsyncMock(return_value=None)
    manager._find_inst_by_id = MagicMock(return_value=platform)

    result = await manager.send_to_session(session, chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="platform did not return an acceptance receipt",
        status="unknown",
    )


@pytest.mark.asyncio
async def test_platform_manager_send_to_session_hides_adapter_failure_details(caplog):
    manager = _make_manager()
    session = MessageSession.from_str("telegram:FriendMessage:chat-1")
    chain = MessageChain(chain=[Plain("hello")])
    platform = MagicMock()
    platform.send_by_session = AsyncMock(
        side_effect=RuntimeError(
            "adapter rejected api_key=top-secret Bearer token-123 "
            "https://internal.example/send C:\\private\\secret.txt"
        )
    )
    manager._find_inst_by_id = MagicMock(return_value=platform)

    result = await manager.send_to_session(session, chain)

    assert result == PlatformSendResult(
        platform_id="telegram",
        success=False,
        target="chat-1",
        message_count=1,
        error_message="message delivery failed",
        status="unknown",
    )
    assert "top-secret" not in caplog.text
    assert "token-123" not in caplog.text
    assert "internal.example" not in caplog.text
    assert "C:\\private\\secret.txt" not in caplog.text


@pytest.mark.asyncio
async def test_platform_manager_terminate_platform_clears_platform_limit():
    manager = _make_manager()
    manager.set_platform_concurrency_limit("telegram", 2)
    platform = MagicMock()
    platform.client_self_id = "client-1"
    manager._inst_map["telegram"] = {
        "inst": platform,
        "client_id": "client-1",
    }
    manager._platform_insts = [platform]
    manager._terminate_inst_and_tasks = AsyncMock()

    await manager.terminate_platform("telegram")

    assert manager.get_platform_concurrency_limit("telegram") is None


def test_platform_manager_get_all_stats_redacts_adapter_failure(caplog):
    manager = _make_manager()
    platform = MagicMock()
    platform.config = {"id": "bot"}
    platform.get_stats.side_effect = RuntimeError(
        "password=very-secret https://internal.example/stats C:\\private\\stats.txt"
    )
    manager._platform_insts = [platform]

    stats = manager.get_all_stats()

    assert stats["platforms"] == [
        {
            "id": "bot",
            "type": "unknown",
            "status": "unknown",
            "error_count": 0,
            "last_error": None,
        }
    ]
    assert "very-secret" not in caplog.text
    assert "internal.example" not in caplog.text
    assert "C:\\private\\stats.txt" not in caplog.text


@pytest.mark.asyncio
async def test_platform_manager_serializes_disable_then_enable_reload(monkeypatch):
    manager = _make_manager()
    first_termination_started = asyncio.Event()
    allow_first_termination = asyncio.Event()
    enable_reload_entered = asyncio.Event()
    events: list[str] = []
    termination_count = 0

    async def terminate_platform_unlocked(platform_id: str) -> None:
        nonlocal termination_count
        termination_count += 1
        events.append(f"terminate:{platform_id}:{termination_count}")
        if termination_count == 1:
            first_termination_started.set()
            await allow_first_termination.wait()

    async def load_platform_unlocked(platform_config: dict) -> None:
        events.append(f"load:{platform_config['id']}")

    monkeypatch.setattr(
        manager,
        "_terminate_platform_unlocked",
        terminate_platform_unlocked,
    )
    monkeypatch.setattr(
        manager,
        "_load_platform_unlocked",
        load_platform_unlocked,
    )

    disable_task = asyncio.create_task(
        manager.reload({"enable": False, "id": "napcat", "type": "napcat"})
    )
    await first_termination_started.wait()

    async def enable_reload() -> None:
        enable_reload_entered.set()
        await manager.reload({"enable": True, "id": "napcat", "type": "napcat"})

    enable_task = asyncio.create_task(enable_reload())
    await enable_reload_entered.wait()

    assert events == ["terminate:napcat:1"]

    allow_first_termination.set()
    await asyncio.gather(disable_task, enable_task)

    assert events == [
        "terminate:napcat:1",
        "terminate:napcat:2",
        "load:napcat",
    ]


def test_platform_manager_create_event_falls_back_to_platform_name() -> None:
    manager = _make_manager()
    platform = MagicMock()
    platform.create_event.return_value = MagicMock()
    manager._find_inst_by_id = MagicMock(return_value=None)
    manager._find_inst_by_name = MagicMock(return_value=platform)

    manager.create_event("telegram", MagicMock(), is_wake=False)

    manager._find_inst_by_id.assert_called_once_with("telegram")
    manager._find_inst_by_name.assert_called_once_with("telegram")
    platform.create_event.assert_called_once()
    platform.commit_event.assert_called_once()
    platform.commit_event.call_args.args[0].set_extra.assert_called_once_with(
        "adapter_preconfigured",
        False,
    )


def test_platform_discovery_imports_registered_builtin_adapter_once(monkeypatch):
    adapter_type = "test-adapter"
    module_name = "astrbot.core.platform.sources.test_adapter"
    adapter = type("TestAdapter", (), {})
    adapter.__module__ = module_name
    setattr(
        adapter,
        "__astrbot_platform_adapter_descriptor__",
        PlatformAdapterDescriptor.create(
            name=adapter_type,
            description="test adapter",
            default_config_tmpl=None,
            adapter_display_name=None,
            logo_path=None,
            support_streaming_message=True,
            i18n_resources=None,
            config_metadata=None,
        ),
    )
    module = ModuleType(module_name)
    module.TestAdapter = adapter
    imported = []
    monkeypatch.setattr(
        discovery, "BUILTIN_PLATFORM_MODULES", {adapter_type: module_name}
    )

    def import_module(name):
        imported.append(name)
        return module

    monkeypatch.setattr(discovery.importlib, "import_module", import_module)
    catalog = PlatformCatalog()

    assert discovery.discover_platform_adapter(adapter_type, catalog) is adapter
    assert discovery.discover_platform_adapter(adapter_type, catalog) is adapter
    assert imported == [module_name]


@pytest.mark.asyncio
async def test_platform_manager_skips_disabled_and_unknown_platform(monkeypatch):
    manager = _make_manager()
    discover = MagicMock(return_value=None)
    monkeypatch.setattr(
        "astrbot.core.platform.manager.discover_platform_adapter", discover
    )

    await manager.load_platform({"enable": False, "id": "disabled", "type": "x"})
    await manager.load_platform({"enable": True, "id": "unknown", "type": "x"})

    discover.assert_called_once_with("x", manager.catalog)
    assert manager._platform_insts == []


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_injects_runtime_dependencies_into_owned_webchat(
    monkeypatch,
):
    manager = _make_manager()
    manager.database = object()
    manager.preferences = object()
    instances = _install_lifecycle_adapter(monkeypatch)

    try:
        await manager.initialize()

        assert len(instances) == 1
        webchat = instances[0]
        await webchat.run_started.wait()
        assert webchat.config == {}
        assert webchat.database is manager.database
        assert webchat.runtime_config is manager.astrbot_config
        assert webchat.preferences is manager.preferences
        assert manager._inst_map == {}
        assert manager._platform_insts == [webchat]
        assert len(manager._platform_tasks) == 1

        await manager.terminate()

        assert webchat.terminate_started.is_set()
        assert webchat.run_cancelled.is_set()
        assert manager._platform_insts == []
        assert manager._platform_tasks == {}
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_terminate_owns_webchat_on_client_id_collision(
    monkeypatch,
):
    """Configured adapters cannot make the built-in WebChat task disappear."""
    manager = PlatformManager(
        {
            "platform": [{"enable": True, "id": "bot", "type": "lifecycle-fake"}],
            "platform_settings": {},
        },
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    instances = _install_lifecycle_adapter(monkeypatch, client_ids=["same", "same"])

    try:
        await manager.initialize()
        configured, webchat = instances
        await asyncio.gather(configured.run_started.wait(), webchat.run_started.wait())

        await manager.terminate()

        assert configured.terminate_started.is_set()
        assert webchat.terminate_started.is_set()
        assert configured.run_cancelled.is_set()
        assert webchat.run_cancelled.is_set()
        assert manager._platform_insts == []
        assert manager._platform_tasks == {}
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_task_wrapper_propagates_direct_cancellation(
    monkeypatch,
):
    """A direct wrapper cancellation must remain observable to its owner."""
    manager = _make_manager()
    instances = _install_lifecycle_adapter(monkeypatch)
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}

    try:
        await manager.load_platform(config)
        inst = instances[0]
        await inst.run_started.wait()
        tasks = next(iter(manager._platform_tasks.values()))

        tasks.wrapper.cancel()
        with pytest.raises(asyncio.CancelledError):
            await tasks.wrapper

        await inst.run_finished.wait()
        assert tasks.run.cancelled()
        assert inst.run_cancelled.is_set()
        assert inst.status.value == "stopped"
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_terminates_adapter_owned_background_tasks(
    monkeypatch,
):
    """Manager cleanup owns work an adapter leaves behind in ``terminate``."""
    manager = _make_manager()
    instances = _install_lifecycle_adapter(monkeypatch)
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}

    try:
        await manager.load_platform(config)
        inst = instances[0]
        await inst.run_started.wait()
        background_task = inst.start_background_task()
        await inst.background_started.wait()

        await manager.terminate_platform("bot")

        assert inst.terminate_started.is_set()
        assert background_task.cancelled()
        assert inst.background_cancelled.is_set()
        assert inst._background_tasks == set()
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
@pytest.mark.parametrize("attempt", range(3))
async def test_platform_manager_reclaims_tasks_created_during_run_cancellation(
    monkeypatch,
    attempt: int,
):
    """A run coroutine cannot register background work after its final cleanup."""
    del attempt
    manager = _make_manager()
    instances = _install_lifecycle_adapter(monkeypatch)
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}

    try:
        await manager.load_platform(config)
        inst = instances[0]
        await inst.run_started.wait()
        inst.spawn_background_on_run_cancel = True

        await manager.terminate_platform("bot")
        await inst.late_background_started.wait()

        assert inst.run_cancelled.is_set()
        assert inst.late_background_cancelled.is_set()
        assert inst._background_tasks == set()
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
@pytest.mark.parametrize("attempt", range(3))
async def test_platform_manager_serializes_real_same_id_reload_and_reclaims_old_tasks(
    monkeypatch,
    attempt: int,
):
    del attempt
    manager = _make_manager()
    instances = _install_lifecycle_adapter(
        monkeypatch,
        client_ids=["shared", "shared", "shared"],
    )
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}
    manager.platforms_config.append(config)

    first_reload: asyncio.Task | None = None
    second_reload: asyncio.Task | None = None
    try:
        await manager.load_platform(config)
        old = instances[0]
        await old.run_started.wait()
        old.allow_terminate.clear()

        first_reload = asyncio.create_task(
            manager.reload(config), name="lifecycle-first-reload"
        )
        await old.terminate_started.wait()

        second_reload_entered = asyncio.Event()

        async def reload_again() -> None:
            second_reload_entered.set()
            await manager.reload(config)

        second_reload = asyncio.create_task(
            reload_again(), name="lifecycle-second-reload"
        )
        await second_reload_entered.wait()

        # The first reload owns the lifecycle lock until it has reclaimed old.
        assert instances == [old]

        old.allow_terminate.set()
        await asyncio.gather(first_reload, second_reload)

        replacement, current = instances[1:]
        await current.run_started.wait()
        assert old.run_cancelled.is_set()
        assert replacement.run_cancelled.is_set()
        assert manager._inst_map["bot"]["inst"] is current
        assert manager._platform_insts == [current]
        assert len(manager._platform_tasks) == 1
        assert next(iter(manager._platform_tasks.values())).platform is current
    finally:
        for task in (first_reload, second_reload):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (first_reload, second_reload) if task is not None),
            return_exceptions=True,
        )
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
@pytest.mark.parametrize("attempt", range(3))
async def test_platform_manager_terminate_and_reload_keep_new_instance_owned(
    monkeypatch,
    attempt: int,
):
    del attempt
    manager = PlatformManager(
        {
            "platform": [{"enable": True, "id": "bot", "type": "lifecycle-fake"}],
            "platform_settings": {},
        },
        asyncio.Queue(),
        WebChatQueueManager(),
        PlatformCatalog(),
        *_make_registries(),
        metrics=_make_metrics(),
    )
    instances = _install_lifecycle_adapter(
        monkeypatch,
        client_ids=["shared", "webchat", "shared"],
    )
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}
    shutdown: asyncio.Task | None = None
    reload_task: asyncio.Task | None = None
    try:
        await manager.initialize()
        old, webchat = instances
        await asyncio.gather(old.run_started.wait(), webchat.run_started.wait())
        webchat.allow_terminate.clear()

        shutdown = asyncio.create_task(manager.terminate(), name="lifecycle-shutdown")
        await webchat.terminate_started.wait()
        assert old.run_cancelled.is_set()

        reload_entered = asyncio.Event()

        async def reload_after_shutdown_started() -> None:
            reload_entered.set()
            await manager.reload(config)

        reload_task = asyncio.create_task(
            reload_after_shutdown_started(), name="lifecycle-reload-during-shutdown"
        )
        await reload_entered.wait()

        # A shutdown in progress must retain exclusive ownership until cleanup ends.
        assert instances == [old, webchat]

        webchat.allow_terminate.set()
        await asyncio.gather(shutdown, reload_task)

        current = instances[2]
        await current.run_started.wait()
        assert manager._inst_map["bot"]["inst"] is current
        assert manager._platform_insts == [current]
        assert len(manager._platform_tasks) == 1
        assert next(iter(manager._platform_tasks.values())).platform is current
    finally:
        for task in (shutdown, reload_task):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (shutdown, reload_task) if task is not None),
            return_exceptions=True,
        )
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_keeps_task_ownership_by_instance_on_client_id_collision(
    monkeypatch,
):
    manager = _make_manager()
    instances = _install_lifecycle_adapter(monkeypatch, client_ids=["same", "same"])
    first_config = {"enable": True, "id": "first", "type": "lifecycle-fake"}
    second_config = {"enable": True, "id": "second", "type": "lifecycle-fake"}

    try:
        await manager.load_platform(first_config)
        first = instances[0]
        await first.run_started.wait()
        await manager.load_platform(second_config)
        second = instances[1]
        await second.run_started.wait()

        await manager.terminate_platform("second")

        assert second.run_cancelled.is_set()
        assert not first.run_finished.is_set()
        assert manager._inst_map == {"first": {"inst": first, "client_id": "same"}}
        assert manager._platform_insts == [first]
        assert len(manager._platform_tasks) == 1
        assert next(iter(manager._platform_tasks.values())).platform is first
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_reclaims_run_task_when_adapter_terminate_fails(
    monkeypatch,
    caplog,
):
    manager = _make_manager()
    instances = _install_lifecycle_adapter(monkeypatch)
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}

    try:
        await manager.load_platform(config)
        inst = instances[0]
        await inst.run_started.wait()
        inst.terminate_error = RuntimeError(
            "api_key=top-secret Bearer token-123 "
            "https://internal.example/path C:\\private\\secret.txt"
        )

        await manager.terminate_platform("bot")

        assert inst.terminate_started.is_set()
        assert inst.run_cancelled.is_set()
        assert manager._inst_map == {}
        assert manager._platform_insts == []
        assert manager._platform_tasks == {}
        assert "top-secret" not in caplog.text
        assert "token-123" not in caplog.text
        assert "internal.example" not in caplog.text
        assert "C:\\private\\secret.txt" not in caplog.text
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_redacts_adapter_task_failures_before_stats_and_logs(
    monkeypatch,
    caplog,
):
    manager = _make_manager()
    instances = _install_lifecycle_adapter(monkeypatch)
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}

    try:
        await manager.load_platform(config)
        inst = instances[0]
        await inst.run_started.wait()
        inst.run_error = RuntimeError(
            "password=very-secret https://internal.example/adapter"
        )
        tasks = next(iter(manager._platform_tasks.values()))
        inst.allow_run_exit.set()
        await tasks.wrapper

        assert inst.last_error is not None
        assert "very-secret" not in inst.last_error.message
        assert "internal.example" not in inst.last_error.message
        assert "very-secret" not in (inst.last_error.traceback or "")
        assert "internal.example" not in (inst.last_error.traceback or "")
        assert "very-secret" not in caplog.text
        assert "internal.example" not in caplog.text
    finally:
        await _cleanup_lifecycle_manager(manager, instances)


@pytest.mark.asyncio
@pytest.mark.blocking
async def test_platform_manager_cancellation_still_reclaims_adapter_run_task(
    monkeypatch,
):
    manager = _make_manager()
    instances = _install_lifecycle_adapter(monkeypatch)
    config = {"enable": True, "id": "bot", "type": "lifecycle-fake"}
    termination: asyncio.Task | None = None

    try:
        await manager.load_platform(config)
        inst = instances[0]
        await inst.run_started.wait()
        inst.allow_terminate.clear()

        termination = asyncio.create_task(
            manager.terminate_platform("bot"), name="lifecycle-cancel-terminate"
        )
        await inst.terminate_started.wait()
        termination.cancel()
        with pytest.raises(asyncio.CancelledError):
            await termination

        assert inst.run_cancelled.is_set()
        assert manager._inst_map == {}
        assert manager._platform_insts == []
        assert manager._platform_tasks == {}
    finally:
        if termination is not None and not termination.done():
            termination.cancel()
        if termination is not None:
            await asyncio.gather(termination, return_exceptions=True)
        await _cleanup_lifecycle_manager(manager, instances)
