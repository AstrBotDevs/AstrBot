"""Tests for AstrBotCoreLifecycle."""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.log import LogBroker


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


class TestAstrBotCoreLifecycleInit:
    """Tests for AstrBotCoreLifecycle initialization."""

    def test_init(self, mock_log_broker, mock_db):
        """Test AstrBotCoreLifecycle initialization."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        assert lifecycle.log_broker == mock_log_broker
        assert lifecycle.db == mock_db
        assert lifecycle.subagent_orchestrator is None
        assert lifecycle.cron_manager is None
        assert lifecycle.temp_dir_cleaner is None

    def test_init_with_proxy(self, mock_log_broker, mock_db, mock_astrbot_config):
        """Test initialization with proxy settings."""
        mock_astrbot_config.get = MagicMock(
            side_effect=lambda key, default="": {
                "http_proxy": "http://proxy.example.com:8080",
                "no_proxy": ["localhost", "127.0.0.1"],
            }.get(key, default)
        )

        with patch("astrbot.core.core_lifecycle.astrbot_config", mock_astrbot_config):
            lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

            assert lifecycle.log_broker == mock_log_broker
            assert lifecycle.db == mock_db
            # Verify proxy environment variables are set
            assert os.environ.get("http_proxy") == "http://proxy.example.com:8080"
            assert os.environ.get("https_proxy") == "http://proxy.example.com:8080"
            assert "localhost" in os.environ.get("no_proxy", "")
            assert "127.0.0.1" in os.environ.get("no_proxy", "")

            # Clean up environment variables
            del os.environ["http_proxy"]
            del os.environ["https_proxy"]
            del os.environ["no_proxy"]

    def test_init_clears_proxy(self, mock_log_broker, mock_db, mock_astrbot_config):
        """Test initialization clears proxy settings when configured."""
        mock_astrbot_config.get = MagicMock(return_value="")
        # Set proxy in environment to test clearing
        os.environ["http_proxy"] = "http://old-proxy:8080"
        os.environ["https_proxy"] = "http://old-proxy:8080"

        with patch("astrbot.core.core_lifecycle.astrbot_config", mock_astrbot_config):
            lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

            assert lifecycle.log_broker == mock_log_broker
            # Verify proxy environment variables are cleared
            assert "http_proxy" not in os.environ
            assert "https_proxy" not in os.environ


class TestAstrBotCoreLifecycleStop:
    """Tests for AstrBotCoreLifecycle.stop method."""

    @pytest.mark.asyncio
    async def test_stop_without_initialize(self, mock_log_broker, mock_db):
        """Test stop without initialize should not raise errors."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Set up minimal state to avoid None attribute errors
        lifecycle.temp_dir_cleaner = None
        lifecycle.cron_manager = None
        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()
        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()
        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()
        lifecycle.plugin_manager = MagicMock()
        lifecycle.plugin_manager.context = MagicMock()
        lifecycle.plugin_manager.context.get_all_stars = MagicMock(return_value=[])
        lifecycle.curr_tasks = []
        lifecycle.dashboard_shutdown_event = asyncio.Event()

        # Should not raise
        await lifecycle.stop()


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

        with (
            patch(
                "astrbot.core.core_lifecycle.star_handlers_registry"
            ) as mock_registry,
            patch("astrbot.core.core_lifecycle.logger"),
        ):
            mock_registry.get_handlers_by_event_type = MagicMock(return_value=[])

            # Create a task that completes quickly for testing
            async def quick_task():
                return

            # Run start but cancel after a brief moment to avoid hanging
            start_task = asyncio.create_task(lifecycle.start())

            # Give it a moment to start
            await asyncio.sleep(0.01)

            # Cancel the start task
            start_task.cancel()

            try:
                await start_task
            except asyncio.CancelledError:
                pass

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

            # Run start but cancel after a brief moment
            start_task = asyncio.create_task(lifecycle.start())
            await asyncio.sleep(0.01)
            start_task.cancel()

            try:
                await start_task
            except asyncio.CancelledError:
                pass

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

        lifecycle.curr_tasks = []

        await lifecycle.stop()

        # Verify all managers were terminated
        lifecycle.provider_manager.terminate.assert_awaited_once()
        lifecycle.platform_manager.terminate.assert_awaited_once()
        lifecycle.kb_manager.terminate.assert_awaited_once()

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

        lifecycle.curr_tasks = []

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            # Should not raise
            await lifecycle.stop()

            # Verify warning was logged about plugin termination failure
            mock_logger.warning.assert_called()


class TestAstrBotCoreLifecycleRestart:
    """Tests for AstrBotCoreLifecycle.restart method."""

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

        with patch("astrbot.core.core_lifecycle.threading.Thread") as mock_thread:
            await lifecycle.restart()

            # Verify managers were terminated
            lifecycle.provider_manager.terminate.assert_awaited_once()
            lifecycle.platform_manager.terminate.assert_awaited_once()
            lifecycle.kb_manager.terminate.assert_awaited_once()

            # Verify thread was started
            mock_thread.assert_called_once()
            mock_thread.return_value.start.assert_called_once()


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
