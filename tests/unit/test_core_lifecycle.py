"""Tests for AstrBotCoreLifecycle."""

import asyncio
import os
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle, LifecycleState
from astrbot.core.log import LogBroker
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.star.context import Context


@pytest.fixture
def mock_log_broker():
    """Create a mock log broker."""
    log_broker = MagicMock(spec=LogBroker)
    return log_broker


@pytest.fixture
def mock_db():
    """Create a mock database."""
    db = MagicMock()
    db.initialize = AsyncMock()
    return db


@pytest.fixture
def mock_astrbot_config():
    """Create a mock AstrBot config."""
    config = MagicMock()
    config.get = MagicMock(return_value="")
    config.__getitem__ = MagicMock(return_value={})
    config.copy = MagicMock(return_value={})
    return config


def build_initialize_test_mocks():
    """Create common mocks for lifecycle initialization tests."""
    mocks = {}

    mocks["html_renderer"] = MagicMock()
    mocks["html_renderer"].initialize = AsyncMock()

    mocks["umop_config_router"] = MagicMock()
    mocks["umop_config_router"].initialize = AsyncMock()

    mocks["astrbot_config_mgr"] = MagicMock()
    mocks["astrbot_config_mgr"].default_conf = {}
    mocks["astrbot_config_mgr"].confs = {}

    mocks["persona_mgr"] = MagicMock()
    mocks["persona_mgr"].initialize = AsyncMock()

    mocks["provider_manager"] = MagicMock()
    mocks["provider_manager"].initialize = AsyncMock()

    mocks["platform_manager"] = MagicMock()
    mocks["platform_manager"].initialize = AsyncMock()

    mocks["conversation_manager"] = MagicMock()
    mocks["platform_message_history_manager"] = MagicMock()

    mocks["kb_manager"] = MagicMock()
    mocks["kb_manager"].initialize = AsyncMock()

    mocks["cron_manager"] = MagicMock()

    mocks["star_context"] = MagicMock()
    mocks["star_context"].registered_web_apis = []
    mocks["star_context"]._register_tasks = []

    def reset_runtime_registrations() -> None:
        mocks["star_context"].registered_web_apis.clear()
        mocks["star_context"]._register_tasks.clear()

    mocks["star_context"].reset_runtime_registrations = MagicMock(
        side_effect=reset_runtime_registrations
    )

    mocks["plugin_manager"] = MagicMock()
    mocks["plugin_manager"].reload = AsyncMock()

    mocks["astrbot_updator"] = MagicMock()
    mocks["astrbot_updator_cls"] = MagicMock(return_value=mocks["astrbot_updator"])

    mocks["event_bus"] = MagicMock()
    mocks["event_bus_cls"] = MagicMock(return_value=mocks["event_bus"])

    mocks["migra"] = AsyncMock()

    async def update_llm_metadata():
        return None

    mocks["update_llm_metadata"] = update_llm_metadata
    mocks["create_task"] = MagicMock(return_value=MagicMock())
    mocks["init_subagent_orchestrator"] = AsyncMock()

    return mocks


def patch_initialize_test_mocks(mock_astrbot_config, mocks):
    """Patch shared lifecycle initialization dependencies."""
    stack = ExitStack()
    stack.enter_context(
        patch("astrbot.core.core_lifecycle.astrbot_config", mock_astrbot_config)
    )
    stack.enter_context(
        patch("astrbot.core.core_lifecycle.html_renderer", mocks["html_renderer"])
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.UmopConfigRouter",
            return_value=mocks["umop_config_router"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.AstrBotConfigManager",
            return_value=mocks["astrbot_config_mgr"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.PersonaManager",
            return_value=mocks["persona_mgr"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.ProviderManager",
            return_value=mocks["provider_manager"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.PlatformManager",
            return_value=mocks["platform_manager"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.ConversationManager",
            return_value=mocks["conversation_manager"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.PlatformMessageHistoryManager",
            return_value=mocks["platform_message_history_manager"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.KnowledgeBaseManager",
            return_value=mocks["kb_manager"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.CronJobManager",
            return_value=mocks["cron_manager"],
        )
    )
    stack.enter_context(
        patch("astrbot.core.core_lifecycle.Context", return_value=mocks["star_context"])
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.PluginManager",
            return_value=mocks["plugin_manager"],
        )
    )
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.AstrBotUpdator",
            mocks["astrbot_updator_cls"],
        )
    )
    stack.enter_context(
        patch("astrbot.core.core_lifecycle.EventBus", mocks["event_bus_cls"])
    )
    stack.enter_context(patch("astrbot.core.core_lifecycle.migra", mocks["migra"]))
    stack.enter_context(
        patch(
            "astrbot.core.core_lifecycle.update_llm_metadata",
            mocks["update_llm_metadata"],
        )
    )
    stack.enter_context(
        patch("astrbot.core.core_lifecycle.asyncio.create_task", mocks["create_task"])
    )
    stack.enter_context(
        patch.object(
            AstrBotCoreLifecycle,
            "_init_or_reload_subagent_orchestrator",
            mocks["init_subagent_orchestrator"],
        )
    )
    return stack


async def build_inflight_runtime_bootstrap_lifecycle(
    mock_log_broker, mock_db, mock_astrbot_config
):
    """Create a lifecycle with an in-flight runtime bootstrap task."""
    lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
    mocks = build_initialize_test_mocks()
    blocker = asyncio.Event()

    async def blocking_reload():
        await blocker.wait()

    mocks["plugin_manager"].reload.side_effect = blocking_reload

    with patch_initialize_test_mocks(mock_astrbot_config, mocks):
        await lifecycle.initialize_core()

    lifecycle.temp_dir_cleaner = None
    lifecycle.cron_manager = None
    assert lifecycle.plugin_manager is not None
    assert lifecycle.provider_manager is not None
    assert lifecycle.platform_manager is not None
    assert lifecycle.kb_manager is not None
    lifecycle.plugin_manager.context = MagicMock()
    lifecycle.plugin_manager.context.get_all_stars = MagicMock(return_value=[])
    lifecycle.provider_manager.terminate = AsyncMock()
    lifecycle.platform_manager.terminate = AsyncMock()
    lifecycle.kb_manager.terminate = AsyncMock()
    lifecycle.runtime_bootstrap_task = asyncio.create_task(
        lifecycle.bootstrap_runtime()
    )

    await asyncio.sleep(0)

    return lifecycle


class DummyAwaitable:
    def __init__(self, name: str) -> None:
        self.name = name

    def __await__(self):
        if False:
            yield None
        return None


def build_provider_manager_for_tests() -> ProviderManager:
    acm = MagicMock()
    acm.confs = {
        "default": {
            "provider": [],
            "provider_settings": {},
            "provider_stt_settings": {},
            "provider_tts_settings": {},
            "provider_sources": [],
        }
    }
    persona_mgr = MagicMock()
    persona_mgr.default_persona = "default"
    return ProviderManager(acm, MagicMock(), persona_mgr)


def build_context_for_tests() -> Context:
    return Context(
        asyncio.Queue(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(platform_insts=[]),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )


def mark_runtime_failed(
    lifecycle: AstrBotCoreLifecycle,
    error: BaseException,
) -> None:
    failed_state = getattr(LifecycleState, "RUNTIME_FAILED", None)
    if failed_state is not None:
        lifecycle._set_lifecycle_state(failed_state)
    else:
        lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)
        cast(Any, lifecycle).lifecycle_state = SimpleNamespace(value="runtime_failed")
        cast(Any, lifecycle).runtime_failed = True
    lifecycle.runtime_ready_event.clear()
    lifecycle.runtime_failed_event.set()
    lifecycle.runtime_bootstrap_error = error


class TestAstrBotCoreLifecycleInit:
    """Tests for AstrBotCoreLifecycle initialization."""

    def test_init(self, mock_log_broker, mock_db):
        """Test AstrBotCoreLifecycle initialization."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        assert lifecycle.log_broker == mock_log_broker
        assert lifecycle.db == mock_db
        assert lifecycle.lifecycle_state == LifecycleState.CREATED
        assert lifecycle.subagent_orchestrator is None
        assert lifecycle.cron_manager is None
        assert lifecycle.temp_dir_cleaner is None

    def test_init_with_proxy(
        self,
        mock_log_broker,
        mock_db,
        mock_astrbot_config,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test initialization with proxy settings."""
        mock_astrbot_config.get = MagicMock(
            side_effect=lambda key, default="": {
                "http_proxy": "http://proxy.example.com:8080",
                "no_proxy": ["localhost", "127.0.0.1"],
            }.get(key, default)
        )
        monkeypatch.delenv("http_proxy", raising=False)
        monkeypatch.delenv("https_proxy", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)

        with patch("astrbot.core.core_lifecycle.astrbot_config", mock_astrbot_config):
            lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

            assert lifecycle.log_broker == mock_log_broker
            assert lifecycle.db == mock_db
            # Verify proxy environment variables are set
            assert os.environ.get("http_proxy") == "http://proxy.example.com:8080"
            assert os.environ.get("https_proxy") == "http://proxy.example.com:8080"
            assert "localhost" in os.environ.get("no_proxy", "")
            assert "127.0.0.1" in os.environ.get("no_proxy", "")

    def test_init_clears_proxy(
        self,
        mock_log_broker,
        mock_db,
        mock_astrbot_config,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Test initialization clears proxy settings when configured."""
        mock_astrbot_config.get = MagicMock(return_value="")
        # Set proxy in environment to test clearing
        monkeypatch.setenv("http_proxy", "http://old-proxy:8080")
        monkeypatch.setenv("https_proxy", "http://old-proxy:8080")

        with patch("astrbot.core.core_lifecycle.astrbot_config", mock_astrbot_config):
            lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

            assert lifecycle.log_broker == mock_log_broker
            # Verify proxy environment variables are cleared
            assert "http_proxy" not in os.environ
            assert "https_proxy" not in os.environ


class TestProviderManagerCleanup:
    """Tests for ProviderManager cleanup safety."""

    @pytest.mark.asyncio
    async def test_terminate_clears_loaded_instances_and_registrations(self):
        """Test terminate removes stale loaded providers so retry starts cleanly."""
        provider_manager = build_provider_manager_for_tests()
        provider_manager.llm_tools.disable_mcp_server = AsyncMock()

        chat_provider = MagicMock()
        chat_provider.terminate = AsyncMock()
        stt_provider = MagicMock()
        stt_provider.terminate = AsyncMock()
        tts_provider = MagicMock()
        tts_provider.terminate = AsyncMock()
        embedding_provider = MagicMock()
        embedding_provider.terminate = AsyncMock()
        rerank_provider = MagicMock()
        rerank_provider.terminate = AsyncMock()

        provider_manager.provider_insts = [chat_provider]
        provider_manager.stt_provider_insts = [stt_provider]
        provider_manager.tts_provider_insts = [tts_provider]
        provider_manager.embedding_provider_insts = [embedding_provider]
        provider_manager.rerank_provider_insts = [rerank_provider]
        provider_manager.inst_map = {
            "chat": chat_provider,
            "stt": stt_provider,
            "tts": tts_provider,
            "embedding": embedding_provider,
            "rerank": rerank_provider,
        }
        provider_manager.curr_provider_inst = chat_provider
        provider_manager.curr_stt_provider_inst = stt_provider
        provider_manager.curr_tts_provider_inst = tts_provider

        await provider_manager.terminate()

        chat_provider.terminate.assert_awaited_once()
        stt_provider.terminate.assert_awaited_once()
        tts_provider.terminate.assert_awaited_once()
        embedding_provider.terminate.assert_awaited_once()
        rerank_provider.terminate.assert_awaited_once()
        provider_manager.llm_tools.disable_mcp_server.assert_awaited_once()
        assert provider_manager.provider_insts == []
        assert provider_manager.stt_provider_insts == []
        assert provider_manager.tts_provider_insts == []
        assert provider_manager.embedding_provider_insts == []
        assert provider_manager.rerank_provider_insts == []
        assert provider_manager.inst_map == {}
        assert provider_manager.curr_provider_inst is None
        assert provider_manager.curr_stt_provider_inst is None
        assert provider_manager.curr_tts_provider_inst is None

    @pytest.mark.asyncio
    async def test_terminate_continues_when_individual_provider_terminate_fails(self):
        """Test terminate keeps cleaning remaining providers and MCP servers after one provider fails."""
        provider_manager = build_provider_manager_for_tests()
        provider_manager.llm_tools.disable_mcp_server = AsyncMock()

        failing_provider = MagicMock()
        failing_provider.meta.return_value.id = "failing"
        failing_provider.terminate = AsyncMock(side_effect=RuntimeError("terminate failed"))

        healthy_provider = MagicMock()
        healthy_provider.meta.return_value.id = "healthy"
        healthy_provider.terminate = AsyncMock()

        provider_manager.provider_insts = [failing_provider, healthy_provider]
        provider_manager.inst_map = {
            "failing": failing_provider,
            "healthy": healthy_provider,
        }

        with patch("astrbot.core.provider.manager.logger") as mock_logger:
            await provider_manager.terminate()

        failing_provider.terminate.assert_awaited_once()
        healthy_provider.terminate.assert_awaited_once()
        provider_manager.llm_tools.disable_mcp_server.assert_awaited_once()
        mock_logger.error.assert_called()


class TestContextRuntimeRegistrations:
    """Tests for runtime registration containers on Context."""

    def test_runtime_registrations_are_isolated_and_resettable(self):
        """Test Context runtime registration containers do not leak and can reset."""
        first_context = build_context_for_tests()
        second_context = build_context_for_tests()
        stale_task = DummyAwaitable("stale-task")

        first_context.register_web_api(
            "/stale",
            MagicMock(),
            ["GET"],
            "stale route",
        )
        first_context.register_task(stale_task, "stale task")

        assert second_context.registered_web_apis == []
        assert second_context._register_tasks == []

        cast(Any, first_context).reset_runtime_registrations()

        assert first_context.registered_web_apis == []
        assert first_context._register_tasks == []


class TestAstrBotCoreLifecycleStop:
    """Tests for AstrBotCoreLifecycle.stop method."""

    @pytest.mark.asyncio
    async def test_stop_without_initialize(self, mock_log_broker, mock_db):
        """Test stop without initialize should not raise errors."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Should not raise
        await lifecycle.stop()
        assert lifecycle.lifecycle_state == LifecycleState.CREATED
        assert lifecycle.runtime_ready is False

    @pytest.mark.asyncio
    async def test_stop_in_core_ready_state_tolerates_missing_runtime_components(
        self, mock_log_broker, mock_db
    ):
        """Test stop works before runtime bootstrap completes."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        lifecycle.curr_tasks = []
        lifecycle.dashboard_shutdown_event = asyncio.Event()
        lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)

        await lifecycle.stop()

        assert lifecycle.lifecycle_state == LifecycleState.CREATED
        assert lifecycle.runtime_ready is False


class TestAstrBotCoreLifecycleTaskWrapper:
    """Tests for AstrBotCoreLifecycle._task_wrapper method."""

    @pytest.mark.asyncio
    async def test_task_wrapper_normal_completion(self, mock_log_broker, mock_db):
        """Test task wrapper with normal completion."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        async def normal_task():
            pass

        task = asyncio.create_task(normal_task(), name="test_task")

        # Should not raise
        await lifecycle._task_wrapper(task)

    @pytest.mark.asyncio
    async def test_task_wrapper_with_exception(self, mock_log_broker, mock_db):
        """Test task wrapper with exception."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        async def failing_task():
            raise ValueError("Test error")

        task = asyncio.create_task(failing_task(), name="test_task")

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            await lifecycle._task_wrapper(task)

            # Verify error was logged
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_task_wrapper_with_cancelled_error(self, mock_log_broker, mock_db):
        """Test task wrapper with CancelledError."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        async def cancelled_task():
            raise asyncio.CancelledError()

        task = asyncio.create_task(cancelled_task(), name="test_task")

        # Should not raise and should not log
        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            await lifecycle._task_wrapper(task)

            # CancelledError should be handled silently
            assert not any(
                "error" in str(call).lower()
                for call in mock_logger.error.call_args_list
            )


class TestAstrBotCoreLifecycleLoadPlatform:
    """Tests for AstrBotCoreLifecycle.load_platform method."""

    @pytest.mark.asyncio
    async def test_load_platform(self, mock_log_broker, mock_db):
        """Test load_platform method."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Set up mock platform manager
        mock_platform_manager = MagicMock()

        mock_inst1 = MagicMock()
        mock_inst1.meta = MagicMock()
        mock_inst1.meta.return_value.id = "inst1"
        mock_inst1.meta.return_value.name = "Instance1"
        mock_inst1.run = AsyncMock()

        mock_inst2 = MagicMock()
        mock_inst2.meta = MagicMock()
        mock_inst2.meta.return_value.id = "inst2"
        mock_inst2.meta.return_value.name = "Instance2"
        mock_inst2.run = AsyncMock()

        mock_platform_manager.get_insts = MagicMock(
            return_value=[mock_inst1, mock_inst2]
        )
        lifecycle.platform_manager = mock_platform_manager

        # Call load_platform
        tasks = lifecycle.load_platform()

        # Verify tasks were created
        assert len(tasks) == 2

        # Verify task names
        assert any("inst1" in task.get_name() for task in tasks)
        assert any("inst2" in task.get_name() for task in tasks)


class TestAstrBotCoreLifecycleErrorHandling:
    """Tests for AstrBotCoreLifecycle error handling."""

    @pytest.mark.asyncio
    async def test_subagent_orchestrator_error_is_logged(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that subagent orchestrator init errors are logged."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.llm_tools = MagicMock()
        lifecycle.persona_mgr = MagicMock()
        lifecycle.astrbot_config = mock_astrbot_config
        lifecycle.astrbot_config.get = MagicMock(return_value={})

        mock_subagent = MagicMock()
        mock_subagent.reload_from_config = AsyncMock(
            side_effect=Exception("Orchestrator init failed")
        )

        with (
            patch(
                "astrbot.core.core_lifecycle.SubAgentOrchestrator",
                return_value=mock_subagent,
            ) as mock_subagent_cls,
            patch("astrbot.core.core_lifecycle.logger") as mock_logger,
        ):
            await lifecycle._init_or_reload_subagent_orchestrator()

        mock_subagent_cls.assert_called_once_with(
            lifecycle.provider_manager.llm_tools,
            lifecycle.persona_mgr,
        )
        mock_subagent.reload_from_config.assert_awaited_once_with({})
        assert mock_logger.error.called
        assert any(
            "Subagent orchestrator init failed" in str(call)
            for call in mock_logger.error.call_args_list
        )


class TestAstrBotCoreLifecycleInitialize:
    """Tests for AstrBotCoreLifecycle.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_core_stops_before_runtime_bootstrap(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that initialize_core sets up only the fast core phase."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        mocks = build_initialize_test_mocks()

        with patch_initialize_test_mocks(mock_astrbot_config, mocks):
            await lifecycle.initialize_core()

        mock_db.initialize.assert_awaited_once()
        mocks["html_renderer"].initialize.assert_awaited_once()
        mocks["umop_config_router"].initialize.assert_awaited_once()
        mocks["persona_mgr"].initialize.assert_awaited_once()
        mocks["init_subagent_orchestrator"].assert_awaited_once()

        mocks["plugin_manager"].reload.assert_not_called()
        mocks["provider_manager"].initialize.assert_not_called()
        mocks["kb_manager"].initialize.assert_not_called()
        mocks["platform_manager"].initialize.assert_not_called()
        mocks["event_bus_cls"].assert_not_called()
        mocks["create_task"].assert_not_called()
        mocks["astrbot_updator_cls"].assert_called_once_with()

        assert lifecycle.lifecycle_state == LifecycleState.CORE_READY
        assert lifecycle.astrbot_updator == mocks["astrbot_updator"]
        assert isinstance(lifecycle.dashboard_shutdown_event, asyncio.Event)
        assert lifecycle.core_initialized is True
        assert lifecycle.runtime_ready is False
        assert lifecycle.runtime_ready_event.is_set() is False
        assert lifecycle.runtime_failed_event.is_set() is False

    @pytest.mark.asyncio
    async def test_bootstrap_runtime_requires_initialize_core(
        self, mock_log_broker, mock_db
    ):
        """Test that bootstrap_runtime requires the core phase first."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        with pytest.raises(RuntimeError, match="initialize_core"):
            await lifecycle.bootstrap_runtime()

    @pytest.mark.asyncio
    async def test_bootstrap_runtime_initializes_deferred_components_in_order(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that bootstrap_runtime completes deferred runtime setup in order."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        mocks = build_initialize_test_mocks()
        call_order = []
        pipeline_scheduler_mapping = {"default": MagicMock()}

        async def load_pipeline_scheduler():
            call_order.append("pipeline_scheduler")
            return pipeline_scheduler_mapping

        async def record_async(name):
            call_order.append(name)

        def record_create_task(coro):
            call_order.append("metadata_task")
            coro.close()
            return MagicMock()

        async def plugin_reload():
            await record_async("plugin_reload")

        async def provider_init():
            await record_async("provider_init")

        async def kb_init():
            await record_async("kb_init")

        async def platform_init():
            await record_async("platform_init")

        mocks["plugin_manager"].reload.side_effect = plugin_reload
        mocks["provider_manager"].initialize.side_effect = provider_init
        mocks["kb_manager"].initialize.side_effect = kb_init
        mocks["platform_manager"].initialize.side_effect = platform_init
        mocks["event_bus_cls"].side_effect = lambda *args, **kwargs: (
            call_order.append("event_bus") or mocks["event_bus"]
        )
        mocks["create_task"].side_effect = record_create_task

        with patch_initialize_test_mocks(mock_astrbot_config, mocks):
            await lifecycle.initialize_core()
            lifecycle.load_pipeline_scheduler = AsyncMock(
                side_effect=load_pipeline_scheduler
            )

            await lifecycle.bootstrap_runtime()

        assert call_order == [
            "plugin_reload",
            "provider_init",
            "kb_init",
            "pipeline_scheduler",
            "event_bus",
            "platform_init",
            "metadata_task",
        ]
        assert lifecycle.pipeline_scheduler_mapping == pipeline_scheduler_mapping
        assert lifecycle.event_bus == mocks["event_bus"]
        assert lifecycle.lifecycle_state == LifecycleState.RUNTIME_READY
        assert lifecycle.core_initialized is True
        assert lifecycle.runtime_ready is True
        assert lifecycle.runtime_ready_event.is_set() is True
        assert lifecycle.runtime_failed_event.is_set() is False

    @pytest.mark.asyncio
    async def test_bootstrap_runtime_sets_runtime_failed_signal_on_error(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that bootstrap_runtime signals failure so start can stop waiting."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        mocks = build_initialize_test_mocks()
        error = RuntimeError("runtime bootstrap failed")
        mocks["plugin_manager"].reload.side_effect = error

        with patch_initialize_test_mocks(mock_astrbot_config, mocks):
            await lifecycle.initialize_core()

            with pytest.raises(RuntimeError, match="runtime bootstrap failed"):
                await lifecycle.bootstrap_runtime()

        assert lifecycle.runtime_ready is False
        assert lifecycle.runtime_ready_event.is_set() is False
        assert lifecycle.runtime_failed_event.is_set() is True
        assert lifecycle.runtime_bootstrap_error is error

    @pytest.mark.asyncio
    async def test_bootstrap_failure_sets_failed_state_and_cleans_partial_runtime_artifacts(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test bootstrap failures leave an explicit failed state without stale runtime artifacts."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        mocks = build_initialize_test_mocks()
        error = RuntimeError("platform init failed after partial bootstrap")
        pipeline_scheduler_mapping = {"default": MagicMock()}
        provider_manager = mocks["provider_manager"]
        platform_manager = mocks["platform_manager"]
        kb_manager = mocks["kb_manager"]
        mocks["provider_manager"].terminate = AsyncMock()
        mocks["platform_manager"].terminate = AsyncMock()
        mocks["kb_manager"].terminate = AsyncMock()
        mocks["platform_manager"].initialize.side_effect = error

        with patch_initialize_test_mocks(mock_astrbot_config, mocks):
            await lifecycle.initialize_core()
            lifecycle.load_pipeline_scheduler = AsyncMock(
                return_value=pipeline_scheduler_mapping
            )

            with pytest.raises(
                RuntimeError,
                match="platform init failed after partial bootstrap",
            ):
                await lifecycle.bootstrap_runtime()

        assert lifecycle.lifecycle_state.value == "runtime_failed"
        assert getattr(lifecycle, "runtime_failed", False) is True
        assert lifecycle.runtime_ready is False
        assert lifecycle.runtime_ready_event.is_set() is False
        assert lifecycle.runtime_failed_event.is_set() is True
        assert lifecycle.runtime_bootstrap_error is error
        assert lifecycle.event_bus is None
        assert lifecycle.pipeline_scheduler_mapping == {}
        assert lifecycle.start_time == 0
        provider_manager.terminate.assert_awaited_once()
        platform_manager.terminate.assert_awaited_once()
        kb_manager.terminate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bootstrap_failure_allows_safe_retry_after_cleanup(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test a failed runtime bootstrap can retry cleanly on the same lifecycle."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        mocks = build_initialize_test_mocks()
        pipeline_scheduler_mapping = {"default": MagicMock()}
        attempts = 0
        provider_manager = mocks["provider_manager"]
        platform_manager = mocks["platform_manager"]
        kb_manager = mocks["kb_manager"]

        mocks["provider_manager"].terminate = AsyncMock()
        mocks["platform_manager"].terminate = AsyncMock()
        mocks["kb_manager"].terminate = AsyncMock()

        async def platform_initialize() -> None:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise RuntimeError("retryable runtime bootstrap failure")

        mocks["platform_manager"].initialize.side_effect = platform_initialize

        with patch_initialize_test_mocks(mock_astrbot_config, mocks):
            await lifecycle.initialize_core()
            lifecycle.load_pipeline_scheduler = AsyncMock(
                return_value=pipeline_scheduler_mapping
            )

            with pytest.raises(
                RuntimeError,
                match="retryable runtime bootstrap failure",
            ):
                await lifecycle.bootstrap_runtime()

            await lifecycle.bootstrap_runtime()

        assert attempts == 2
        assert lifecycle.lifecycle_state == LifecycleState.RUNTIME_READY
        assert getattr(lifecycle, "runtime_failed", False) is False
        assert lifecycle.runtime_ready is True
        assert lifecycle.runtime_failed_event.is_set() is False
        assert lifecycle.runtime_bootstrap_error is None
        assert lifecycle.event_bus == mocks["event_bus"]
        assert lifecycle.pipeline_scheduler_mapping == pipeline_scheduler_mapping
        provider_manager.terminate.assert_awaited_once()
        platform_manager.terminate.assert_awaited_once()
        kb_manager.terminate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_bootstrap_failure_clears_context_runtime_registrations_before_retry(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test failed bootstrap clears stale runtime registrations before retry succeeds."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        mocks = build_initialize_test_mocks()
        attempts = 0
        task_names: list[str] = []

        async def plugin_reload() -> None:
            nonlocal attempts
            attempts += 1
            assert lifecycle.star_context is not None
            dummy_task = DummyAwaitable(f"task-{attempts}")
            task_names.append(dummy_task.name)
            lifecycle.star_context.registered_web_apis.append(
                (
                    f"/attempt-{attempts}",
                    MagicMock(),
                    ["GET"],
                    f"route-{attempts}",
                )
            )
            lifecycle.star_context._register_tasks.append(dummy_task)
            if attempts == 1:
                raise RuntimeError("plugin registration left stale runtime state")

        mocks["plugin_manager"].reload.side_effect = plugin_reload

        with patch_initialize_test_mocks(mock_astrbot_config, mocks):
            await lifecycle.initialize_core()
            lifecycle.load_pipeline_scheduler = AsyncMock(
                return_value={"default": MagicMock()}
            )

            with pytest.raises(
                RuntimeError,
                match="plugin registration left stale runtime state",
            ):
                await lifecycle.bootstrap_runtime()

            assert lifecycle.star_context is not None
            assert lifecycle.star_context.registered_web_apis == []
            assert lifecycle.star_context._register_tasks == []

            await lifecycle.bootstrap_runtime()

        assert lifecycle.star_context is not None
        assert len(lifecycle.star_context.registered_web_apis) == 1
        route, _, methods, desc = lifecycle.star_context.registered_web_apis[0]
        assert route == "/attempt-2"
        assert methods == ["GET"]
        assert desc == "route-2"
        assert [
            cast(DummyAwaitable, task).name
            for task in lifecycle.star_context._register_tasks
        ] == [task_names[-1]]

    @pytest.mark.asyncio
    async def test_initialize_sets_up_all_components(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that initialize sets up all required components in correct order."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Mock all the dependencies
        mock_db.initialize = AsyncMock()
        mock_html_renderer = MagicMock()
        mock_html_renderer.initialize = AsyncMock()

        mock_umop_config_router = MagicMock()
        mock_umop_config_router.initialize = AsyncMock()

        mock_astrbot_config_mgr = MagicMock()
        mock_astrbot_config_mgr.default_conf = {}
        mock_astrbot_config_mgr.confs = {}

        mock_persona_mgr = MagicMock()
        mock_persona_mgr.initialize = AsyncMock()

        mock_provider_manager = MagicMock()
        mock_provider_manager.initialize = AsyncMock()

        mock_platform_manager = MagicMock()
        mock_platform_manager.initialize = AsyncMock()

        mock_conversation_manager = MagicMock()

        mock_platform_message_history_manager = MagicMock()

        mock_kb_manager = MagicMock()
        mock_kb_manager.initialize = AsyncMock()

        mock_cron_manager = MagicMock()

        mock_star_context = MagicMock()
        mock_star_context._register_tasks = []

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.reload = AsyncMock()

        mock_pipeline_scheduler = MagicMock()
        mock_pipeline_scheduler.initialize = AsyncMock()

        mock_astrbot_updator = MagicMock()

        mock_event_bus = MagicMock()

        with (
            patch("astrbot.core.core_lifecycle.astrbot_config", mock_astrbot_config),
            patch("astrbot.core.core_lifecycle.html_renderer", mock_html_renderer),
            patch(
                "astrbot.core.core_lifecycle.UmopConfigRouter",
                return_value=mock_umop_config_router,
            ),
            patch(
                "astrbot.core.core_lifecycle.AstrBotConfigManager",
                return_value=mock_astrbot_config_mgr,
            ),
            patch(
                "astrbot.core.core_lifecycle.PersonaManager",
                return_value=mock_persona_mgr,
            ),
            patch(
                "astrbot.core.core_lifecycle.ProviderManager",
                return_value=mock_provider_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.PlatformManager",
                return_value=mock_platform_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.ConversationManager",
                return_value=mock_conversation_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.PlatformMessageHistoryManager",
                return_value=mock_platform_message_history_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.KnowledgeBaseManager",
                return_value=mock_kb_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.CronJobManager",
                return_value=mock_cron_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.Context", return_value=mock_star_context
            ),
            patch(
                "astrbot.core.core_lifecycle.PluginManager",
                return_value=mock_plugin_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.PipelineScheduler",
                return_value=mock_pipeline_scheduler,
            ),
            patch(
                "astrbot.core.core_lifecycle.AstrBotUpdator",
                return_value=mock_astrbot_updator,
            ),
            patch("astrbot.core.core_lifecycle.EventBus", return_value=mock_event_bus),
            patch("astrbot.core.core_lifecycle.migra", new_callable=AsyncMock),
            patch(
                "astrbot.core.core_lifecycle.update_llm_metadata",
                new_callable=AsyncMock,
            ),
        ):
            await lifecycle.initialize()

        # Verify database initialized
        mock_db.initialize.assert_awaited_once()

        # Verify html renderer initialized
        mock_html_renderer.initialize.assert_awaited_once()

        # Verify UMOP config router initialized
        mock_umop_config_router.initialize.assert_awaited_once()

        # Verify persona manager initialized
        mock_persona_mgr.initialize.assert_awaited_once()

        # Verify provider manager initialized
        mock_provider_manager.initialize.assert_awaited_once()

        # Verify platform manager initialized
        mock_platform_manager.initialize.assert_awaited_once()

        # Verify plugin manager reloaded
        mock_plugin_manager.reload.assert_awaited_once()

        # Verify knowledge base manager initialized
        mock_kb_manager.initialize.assert_awaited_once()

        # Verify pipeline scheduler loaded
        assert lifecycle.pipeline_scheduler_mapping is not None
        assert lifecycle.lifecycle_state == LifecycleState.RUNTIME_READY
        assert lifecycle.core_initialized is True
        assert lifecycle.runtime_ready is True


class TestAstrBotCoreLifecycleLoad:
    """Tests for AstrBotCoreLifecycle._load method."""

    def test_load_requires_runtime_ready_state(self, mock_log_broker, mock_db):
        """Test that _load rejects half-bootstrapped lifecycle state."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.event_bus = MagicMock()
        lifecycle.event_bus.dispatch = AsyncMock()
        lifecycle.star_context = MagicMock()
        lifecycle.star_context._register_tasks = []
        lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)

        with patch("astrbot.core.core_lifecycle.asyncio.create_task"):
            with pytest.raises(RuntimeError, match="RUNTIME_READY"):
                lifecycle._load()

    @pytest.mark.asyncio
    async def test_initialize_handles_migration_failure(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that initialize handles migration failures gracefully."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        mock_db.initialize = AsyncMock()

        mock_html_renderer = MagicMock()
        mock_html_renderer.initialize = AsyncMock()

        mock_umop_config_router = MagicMock()
        mock_umop_config_router.initialize = AsyncMock()

        mock_astrbot_config_mgr = MagicMock()
        mock_astrbot_config_mgr.default_conf = {}
        mock_astrbot_config_mgr.confs = {}

        # Mock components that need to be created for initialize to continue
        with (
            patch("astrbot.core.core_lifecycle.astrbot_config", mock_astrbot_config),
            patch("astrbot.core.core_lifecycle.html_renderer", mock_html_renderer),
            patch(
                "astrbot.core.core_lifecycle.UmopConfigRouter",
                return_value=mock_umop_config_router,
            ),
            patch(
                "astrbot.core.core_lifecycle.AstrBotConfigManager",
                return_value=mock_astrbot_config_mgr,
            ),
            patch(
                "astrbot.core.core_lifecycle.PersonaManager",
                return_value=MagicMock(initialize=AsyncMock()),
            ),
            patch(
                "astrbot.core.core_lifecycle.ProviderManager",
                return_value=MagicMock(initialize=AsyncMock()),
            ),
            patch(
                "astrbot.core.core_lifecycle.PlatformManager",
                return_value=MagicMock(initialize=AsyncMock()),
            ),
            patch(
                "astrbot.core.core_lifecycle.ConversationManager",
                return_value=MagicMock(),
            ),
            patch(
                "astrbot.core.core_lifecycle.PlatformMessageHistoryManager",
                return_value=MagicMock(),
            ),
            patch(
                "astrbot.core.core_lifecycle.KnowledgeBaseManager",
                return_value=MagicMock(initialize=AsyncMock()),
            ),
            patch(
                "astrbot.core.core_lifecycle.CronJobManager",
                return_value=MagicMock(),
            ),
            patch(
                "astrbot.core.core_lifecycle.Context",
                return_value=MagicMock(_register_tasks=[]),
            ),
            patch(
                "astrbot.core.core_lifecycle.PluginManager",
                return_value=MagicMock(reload=AsyncMock()),
            ),
            patch(
                "astrbot.core.core_lifecycle.PipelineScheduler",
                return_value=MagicMock(initialize=AsyncMock()),
            ),
            patch(
                "astrbot.core.core_lifecycle.AstrBotUpdator",
                return_value=MagicMock(),
            ),
            patch(
                "astrbot.core.core_lifecycle.EventBus",
                return_value=MagicMock(),
            ),
            patch(
                "astrbot.core.core_lifecycle.migra",
                AsyncMock(side_effect=Exception("Migration failed")),
            ),
            patch("astrbot.core.core_lifecycle.logger") as mock_logger,
            patch(
                "astrbot.core.core_lifecycle.update_llm_metadata",
                new_callable=AsyncMock,
            ),
        ):
            # Should not raise, just log the error
            await lifecycle.initialize()

            # Verify migration error was logged
            mock_logger.error.assert_called()


class TestAstrBotCoreLifecycleStart:
    """Tests for AstrBotCoreLifecycle.start method."""

    @pytest.mark.asyncio
    async def test_start_waits_for_runtime_ready_before_loading(
        self, mock_log_broker, mock_db
    ):
        """Test that start waits for deferred runtime bootstrap before loading."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)
        lifecycle.curr_tasks = []

        async def wait_for_runtime_ready() -> None:
            await lifecycle.runtime_ready_event.wait()

        lifecycle.runtime_bootstrap_task = asyncio.create_task(wait_for_runtime_ready())

        with (
            patch.object(lifecycle, "_load") as mock_load,
            patch(
                "astrbot.core.core_lifecycle.star_handlers_registry"
            ) as mock_registry,
            patch("astrbot.core.core_lifecycle.logger"),
        ):
            mock_registry.get_handlers_by_event_type = MagicMock(return_value=[])
            start_task = asyncio.create_task(lifecycle.start())

            await asyncio.sleep(0)
            mock_load.assert_not_called()

            lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)
            lifecycle.runtime_ready_event.set()

            await asyncio.wait_for(start_task, timeout=0.1)
            await asyncio.wait_for(lifecycle.runtime_bootstrap_task, timeout=0.1)

        mock_load.assert_called_once()

    @pytest.mark.asyncio
    async def test_start_runtime_failed_returns_cleanly(self, mock_log_broker, mock_db):
        """Test that start exits when deferred runtime bootstrap reports failure."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)
        lifecycle.curr_tasks = []
        error = RuntimeError("bootstrap exploded with detailed reason")

        async def wait_for_runtime_failure() -> None:
            await lifecycle.runtime_failed_event.wait()

        lifecycle.runtime_bootstrap_task = asyncio.create_task(
            wait_for_runtime_failure()
        )

        with (
            patch.object(lifecycle, "_load") as mock_load,
            patch(
                "astrbot.core.core_lifecycle.star_handlers_registry"
            ) as mock_registry,
            patch("astrbot.core.core_lifecycle.logger") as mock_logger,
        ):
            mock_registry.get_handlers_by_event_type = MagicMock(return_value=[])
            start_task = asyncio.create_task(lifecycle.start())

            await asyncio.sleep(0)
            mock_load.assert_not_called()

            lifecycle.runtime_bootstrap_error = error
            lifecycle.runtime_failed_event.set()

            await asyncio.wait_for(start_task, timeout=0.1)
            await asyncio.wait_for(lifecycle.runtime_bootstrap_task, timeout=0.1)

        mock_load.assert_not_called()
        assert any(
            "bootstrap exploded with detailed reason" in str(call)
            for call in mock_logger.error.call_args_list
        )

    @pytest.mark.asyncio
    async def test_start_runtime_failed_state_returns_cleanly_without_bootstrap_task(
        self, mock_log_broker, mock_db
    ):
        """Test explicit runtime failure state wins over missing bootstrap task errors."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.curr_tasks = []
        error = RuntimeError("bootstrap failed before retry")
        mark_runtime_failed(lifecycle, error)
        lifecycle.runtime_bootstrap_task = None

        with (
            patch.object(lifecycle, "_load") as mock_load,
            patch("astrbot.core.core_lifecycle.logger") as mock_logger,
        ):
            await asyncio.wait_for(lifecycle.start(), timeout=0.1)

        mock_load.assert_not_called()
        assert any(
            "bootstrap failed before retry" in str(call)
            for call in mock_logger.error.call_args_list
        )

    @pytest.mark.asyncio
    async def test_start_raises_when_runtime_bootstrap_task_missing(
        self, mock_log_broker, mock_db
    ):
        """Test that start fails fast when no runtime bootstrap task was scheduled."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)
        lifecycle.curr_tasks = []

        with patch("astrbot.core.core_lifecycle.logger"):
            with pytest.raises(RuntimeError, match="runtime bootstrap task"):
                await asyncio.wait_for(lifecycle.start(), timeout=0.1)

    @pytest.mark.asyncio
    async def test_start_returns_cleanly_when_stop_interrupts_runtime_wait(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test stop wakes start callers blocked on deferred runtime bootstrap."""
        lifecycle = await build_inflight_runtime_bootstrap_lifecycle(
            mock_log_broker,
            mock_db,
            mock_astrbot_config,
        )

        with (
            patch.object(lifecycle, "_load") as mock_load,
            patch(
                "astrbot.core.core_lifecycle.star_handlers_registry"
            ) as mock_registry,
            patch("astrbot.core.core_lifecycle.logger") as mock_logger,
        ):
            mock_registry.get_handlers_by_event_type = MagicMock(return_value=[])
            start_task = asyncio.create_task(lifecycle.start())

            await asyncio.sleep(0)
            mock_load.assert_not_called()

            await lifecycle.stop()
            await asyncio.wait_for(start_task, timeout=0.1)

        mock_load.assert_not_called()
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_returns_cleanly_when_restart_interrupts_runtime_wait(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test restart wakes start callers blocked on deferred runtime bootstrap."""
        lifecycle = await build_inflight_runtime_bootstrap_lifecycle(
            mock_log_broker,
            mock_db,
            mock_astrbot_config,
        )

        with (
            patch.object(lifecycle, "_load") as mock_load,
            patch(
                "astrbot.core.core_lifecycle.star_handlers_registry"
            ) as mock_registry,
            patch("astrbot.core.core_lifecycle.threading.Thread") as mock_thread,
            patch("astrbot.core.core_lifecycle.logger") as mock_logger,
        ):
            mock_registry.get_handlers_by_event_type = MagicMock(return_value=[])
            start_task = asyncio.create_task(lifecycle.start())

            await asyncio.sleep(0)
            mock_load.assert_not_called()

            await lifecycle.restart()
            await asyncio.wait_for(start_task, timeout=0.1)

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        mock_load.assert_not_called()
        mock_logger.error.assert_not_called()

    @pytest.mark.asyncio
    async def test_start_loads_event_bus_and_runs(self, mock_log_broker, mock_db):
        """Test that start loads event bus and runs tasks."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Set up minimal state
        lifecycle.event_bus = MagicMock()
        lifecycle.event_bus.dispatch = AsyncMock()

        lifecycle.cron_manager = None

        lifecycle.temp_dir_cleaner = None

        lifecycle.star_context = MagicMock()
        lifecycle.star_context._register_tasks = []

        lifecycle.plugin_manager = MagicMock()
        lifecycle.plugin_manager.context = MagicMock()
        lifecycle.plugin_manager.context.get_all_stars = MagicMock(return_value=[])

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle.dashboard_shutdown_event = asyncio.Event()

        lifecycle.curr_tasks = []
        lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)

        with (
            patch(
                "astrbot.core.core_lifecycle.star_handlers_registry"
            ) as mock_registry,
            patch("astrbot.core.core_lifecycle.logger"),
        ):
            mock_registry.get_handlers_by_event_type = MagicMock(return_value=[])
            await lifecycle.start()

    @pytest.mark.asyncio
    async def test_start_calls_on_astrbot_loaded_hook(self, mock_log_broker, mock_db):
        """Test that start calls the OnAstrBotLoadedEvent handlers."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Set up minimal state
        lifecycle.event_bus = MagicMock()
        lifecycle.event_bus.dispatch = AsyncMock()

        lifecycle.cron_manager = None
        lifecycle.temp_dir_cleaner = None

        lifecycle.star_context = MagicMock()
        lifecycle.star_context._register_tasks = []

        lifecycle.plugin_manager = MagicMock()
        lifecycle.plugin_manager.context = MagicMock()
        lifecycle.plugin_manager.context.get_all_stars = MagicMock(return_value=[])

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle.dashboard_shutdown_event = asyncio.Event()

        lifecycle.curr_tasks = []
        lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)

        # Create a mock handler
        mock_handler = MagicMock()
        mock_handler.handler = AsyncMock()
        mock_handler.handler_module_path = "test_module"
        mock_handler.handler_name = "test_handler"

        with (
            patch(
                "astrbot.core.core_lifecycle.star_handlers_registry"
            ) as mock_registry,
            patch(
                "astrbot.core.core_lifecycle.star_map",
                {"test_module": MagicMock(name="Test Handler")},
            ),
            patch("astrbot.core.core_lifecycle.logger"),
        ):
            mock_registry.get_handlers_by_event_type = MagicMock(
                return_value=[mock_handler]
            )
            await lifecycle.start()

            # Verify handler was called
            mock_handler.handler.assert_awaited_once()


class TestAstrBotCoreLifecycleStopAdditional:
    """Additional tests for AstrBotCoreLifecycle.stop method."""

    @pytest.mark.asyncio
    async def test_stop_cancels_all_tasks(self, mock_log_broker, mock_db):
        """Test that stop cancels all current tasks."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        lifecycle.temp_dir_cleaner = None
        lifecycle.cron_manager = None

        lifecycle.plugin_manager = MagicMock()
        lifecycle.plugin_manager.context = MagicMock()
        lifecycle.plugin_manager.context.get_all_stars = MagicMock(return_value=[])

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle.dashboard_shutdown_event = asyncio.Event()
        lifecycle.event_bus = MagicMock()
        lifecycle.pipeline_scheduler_mapping = {"default": MagicMock()}
        lifecycle.start_time = 123
        lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)

        # Create mock tasks
        mock_task1 = MagicMock(spec=asyncio.Task)
        mock_task1.cancel = MagicMock()
        mock_task1.get_name = MagicMock(return_value="task1")

        mock_task2 = MagicMock(spec=asyncio.Task)
        mock_task2.cancel = MagicMock()
        mock_task2.get_name = MagicMock(return_value="task2")

        lifecycle.curr_tasks = [mock_task1, mock_task2]

        await lifecycle.stop()

        # Verify tasks were cancelled
        mock_task1.cancel.assert_called_once()
        mock_task2.cancel.assert_called_once()
        assert lifecycle.curr_tasks == []
        assert lifecycle.event_bus is None
        assert lifecycle.pipeline_scheduler_mapping == {}
        assert lifecycle.start_time == 0

    @pytest.mark.asyncio
    async def test_stop_terminates_all_managers(self, mock_log_broker, mock_db):
        """Test that stop terminates all managers in correct order."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        lifecycle.temp_dir_cleaner = None
        lifecycle.cron_manager = None

        lifecycle.plugin_manager = MagicMock()
        lifecycle.plugin_manager.context = MagicMock()
        lifecycle.plugin_manager.context.get_all_stars = MagicMock(return_value=[])

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle.dashboard_shutdown_event = asyncio.Event()
        lifecycle.event_bus = MagicMock()
        lifecycle.pipeline_scheduler_mapping = {"default": MagicMock()}
        lifecycle.start_time = 123
        lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)

        lifecycle.curr_tasks = []

        await lifecycle.stop()

        # Verify all managers were terminated
        lifecycle.provider_manager.terminate.assert_awaited_once()
        lifecycle.platform_manager.terminate.assert_awaited_once()
        lifecycle.kb_manager.terminate.assert_awaited_once()
        assert lifecycle.event_bus is None
        assert lifecycle.pipeline_scheduler_mapping == {}
        assert lifecycle.curr_tasks == []
        assert lifecycle.start_time == 0

    @pytest.mark.asyncio
    async def test_stop_handles_plugin_termination_error(
        self, mock_log_broker, mock_db
    ):
        """Test that stop handles plugin termination errors gracefully."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        lifecycle.temp_dir_cleaner = None
        lifecycle.cron_manager = None

        # Create a mock plugin that raises exception on termination
        mock_plugin = MagicMock()
        mock_plugin.name = "test_plugin"

        lifecycle.plugin_manager = MagicMock()
        lifecycle.plugin_manager.context = MagicMock()
        lifecycle.plugin_manager.context.get_all_stars = MagicMock(
            return_value=[mock_plugin]
        )
        lifecycle.plugin_manager._terminate_plugin = AsyncMock(
            side_effect=Exception("Plugin termination failed")
        )

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle.dashboard_shutdown_event = asyncio.Event()
        lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)

        lifecycle.curr_tasks = []

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            # Should not raise
            await lifecycle.stop()

            # Verify warning was logged about plugin termination failure
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_stop_cancels_inflight_runtime_bootstrap_without_failure_state(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test stop clears cancelled runtime bootstrap failure markers."""
        lifecycle = await build_inflight_runtime_bootstrap_lifecycle(
            mock_log_broker,
            mock_db,
            mock_astrbot_config,
        )

        await lifecycle.stop()

        assert lifecycle.runtime_bootstrap_task is None
        assert lifecycle.runtime_failed_event.is_set() is False
        assert lifecycle.runtime_bootstrap_error is None


class TestAstrBotCoreLifecycleRestart:
    """Tests for AstrBotCoreLifecycle.restart method."""

    @pytest.mark.asyncio
    async def test_restart_in_core_ready_state_tolerates_missing_runtime_components(
        self, mock_log_broker, mock_db
    ):
        """Test restart works before deferred runtime bootstrap completes."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.astrbot_updator = MagicMock()
        lifecycle.dashboard_shutdown_event = asyncio.Event()
        lifecycle._set_lifecycle_state(LifecycleState.CORE_READY)

        with patch("astrbot.core.core_lifecycle.threading.Thread") as mock_thread:
            await lifecycle.restart()

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        assert lifecycle.lifecycle_state == LifecycleState.CREATED

    @pytest.mark.asyncio
    async def test_restart_terminates_managers_and_starts_thread(
        self, mock_log_broker, mock_db
    ):
        """Test that restart terminates managers and starts reboot thread."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle.dashboard_shutdown_event = asyncio.Event()

        lifecycle.astrbot_updator = MagicMock()
        lifecycle.event_bus = MagicMock()
        lifecycle.pipeline_scheduler_mapping = {"default": MagicMock()}
        lifecycle.start_time = 123
        lifecycle._set_lifecycle_state(LifecycleState.RUNTIME_READY)

        mock_task1 = MagicMock(spec=asyncio.Task)
        mock_task1.cancel = MagicMock()
        mock_task1.get_name = MagicMock(return_value="task1")

        mock_task2 = MagicMock(spec=asyncio.Task)
        mock_task2.cancel = MagicMock()
        mock_task2.get_name = MagicMock(return_value="task2")

        lifecycle.curr_tasks = [mock_task1, mock_task2]

        with patch("astrbot.core.core_lifecycle.threading.Thread") as mock_thread:
            await lifecycle.restart()

            # Verify managers were terminated
            lifecycle.provider_manager.terminate.assert_awaited_once()
            lifecycle.platform_manager.terminate.assert_awaited_once()
            lifecycle.kb_manager.terminate.assert_awaited_once()
            mock_task1.cancel.assert_called_once()
            mock_task2.cancel.assert_called_once()

            # Verify thread was started
            mock_thread.assert_called_once()
            mock_thread.return_value.start.assert_called_once()
            assert lifecycle.curr_tasks == []
            assert lifecycle.event_bus is None
            assert lifecycle.pipeline_scheduler_mapping == {}
            assert lifecycle.start_time == 0

    @pytest.mark.asyncio
    async def test_restart_cancels_inflight_runtime_bootstrap_without_failure_state(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test restart clears cancelled runtime bootstrap failure markers."""
        lifecycle = await build_inflight_runtime_bootstrap_lifecycle(
            mock_log_broker,
            mock_db,
            mock_astrbot_config,
        )

        with patch("astrbot.core.core_lifecycle.threading.Thread") as mock_thread:
            await lifecycle.restart()

        mock_thread.assert_called_once()
        mock_thread.return_value.start.assert_called_once()
        assert lifecycle.runtime_bootstrap_task is None
        assert lifecycle.runtime_failed_event.is_set() is False
        assert lifecycle.runtime_bootstrap_error is None


class TestAstrBotCoreLifecycleLoadPipelineScheduler:
    """Tests for AstrBotCoreLifecycle.load_pipeline_scheduler method."""

    @pytest.mark.asyncio
    async def test_load_pipeline_scheduler_creates_schedulers(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that load_pipeline_scheduler creates schedulers for each config."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        mock_astrbot_config_mgr = MagicMock()
        mock_astrbot_config_mgr.confs = {
            "config1": MagicMock(),
            "config2": MagicMock(),
        }

        mock_plugin_manager = MagicMock()

        mock_scheduler1 = MagicMock()
        mock_scheduler1.initialize = AsyncMock()

        mock_scheduler2 = MagicMock()
        mock_scheduler2.initialize = AsyncMock()

        with (
            patch(
                "astrbot.core.core_lifecycle.PipelineScheduler"
            ) as mock_scheduler_cls,
            patch("astrbot.core.core_lifecycle.PipelineContext"),
        ):
            # Configure mock to return different schedulers
            mock_scheduler_cls.side_effect = [mock_scheduler1, mock_scheduler2]

            lifecycle.astrbot_config_mgr = mock_astrbot_config_mgr
            lifecycle.plugin_manager = mock_plugin_manager

            result = await lifecycle.load_pipeline_scheduler()

            # Verify schedulers were created for each config
            assert len(result) == 2
            assert "config1" in result
            assert "config2" in result

    @pytest.mark.asyncio
    async def test_reload_pipeline_scheduler_updates_existing(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that reload_pipeline_scheduler updates existing scheduler."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        mock_astrbot_config_mgr = MagicMock()
        mock_astrbot_config_mgr.confs = {
            "config1": MagicMock(),
        }

        mock_plugin_manager = MagicMock()

        mock_new_scheduler = MagicMock()
        mock_new_scheduler.initialize = AsyncMock()

        lifecycle.astrbot_config_mgr = mock_astrbot_config_mgr
        lifecycle.plugin_manager = mock_plugin_manager
        lifecycle.pipeline_scheduler_mapping = {}

        with (
            patch(
                "astrbot.core.core_lifecycle.PipelineScheduler"
            ) as mock_scheduler_cls,
            patch("astrbot.core.core_lifecycle.PipelineContext"),
        ):
            mock_scheduler_cls.return_value = mock_new_scheduler

            await lifecycle.reload_pipeline_scheduler("config1")

            # Verify scheduler was added to mapping
            assert "config1" in lifecycle.pipeline_scheduler_mapping
            mock_new_scheduler.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reload_pipeline_scheduler_raises_for_missing_config(
        self, mock_log_broker, mock_db
    ):
        """Test that reload_pipeline_scheduler raises error for missing config."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        mock_astrbot_config_mgr = MagicMock()
        mock_astrbot_config_mgr.confs = {}

        lifecycle.astrbot_config_mgr = mock_astrbot_config_mgr

        with pytest.raises(ValueError, match="配置文件 .* 不存在"):
            await lifecycle.reload_pipeline_scheduler("nonexistent")
