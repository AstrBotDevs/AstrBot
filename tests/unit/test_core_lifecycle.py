"""Tests for AstrBotCoreLifecycle."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.follow_up import FollowUpCoordinator
from astrbot.core.core_lifecycle import AstrBotCoreLifecycle
from astrbot.core.log import LogBroker
from astrbot.core.runtime_catalogs import RuntimeCatalogs
from astrbot.core.star.star import StarMetadata
from astrbot.core.webchat.queue_manager import WebChatQueueManager
from astrbot.core.webchat.run_coordinator import WebChatRunCoordinator


@pytest.fixture
def mock_log_broker():
    """Create a mock log broker."""
    log_broker = MagicMock(spec=LogBroker)
    return log_broker


@pytest.fixture
def mock_db():
    """Create explicit lifecycle runtime services with a mock database."""
    db = MagicMock()
    db.initialize = AsyncMock()
    db.close = AsyncMock()
    config = MagicMock()
    config.get = MagicMock(return_value="")
    config.__getitem__ = MagicMock(return_value={})
    config.copy = MagicMock(return_value={})
    renderer = MagicMock()
    renderer.initialize = AsyncMock()
    renderer.terminate = AsyncMock()
    preferences = MagicMock()
    preferences.terminate = AsyncMock()
    computer_runtime = MagicMock()
    computer_runtime.terminate = AsyncMock()
    llm_metadata_catalog = MagicMock()
    llm_metadata_catalog.refresh = AsyncMock()
    metrics = MagicMock()
    metrics.shutdown = AsyncMock()
    webchat_queue_manager = WebChatQueueManager()
    follow_up_coordinator = FollowUpCoordinator()
    return SimpleNamespace(
        config=config,
        db=db,
        preferences=preferences,
        html_renderer=renderer,
        file_token_service=MagicMock(),
        pip_installer=MagicMock(),
        catalogs=RuntimeCatalogs(),
        webchat_queue_manager=webchat_queue_manager,
        webchat_run_coordinator=WebChatRunCoordinator(webchat_queue_manager),
        follow_up_coordinator=follow_up_coordinator,
        llm_metadata_catalog=llm_metadata_catalog,
        metrics=metrics,
        computer_runtime=computer_runtime,
        tool_image_cache=MagicMock(),
        demo_mode=False,
    )


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
        assert lifecycle.db == mock_db.db
        assert lifecycle.subagent_orchestrator is None
        assert lifecycle.cron_manager is None
        assert lifecycle.temp_dir_cleaner is None
        with pytest.raises(RuntimeError, match="not initialized"):
            _ = lifecycle.runtime

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

        mock_db.config = mock_astrbot_config
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        assert lifecycle.log_broker == mock_log_broker
        assert lifecycle.db == mock_db.db
        assert "http_proxy" not in os.environ
        assert "https_proxy" not in os.environ

    def test_init_does_not_inherit_or_clear_host_proxy(
        self,
        mock_log_broker,
        mock_db,
        mock_astrbot_config,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """Empty global proxy must not inherit or rewrite the host environment."""
        mock_astrbot_config.get = MagicMock(return_value="")
        monkeypatch.setenv("http_proxy", "http://old-proxy:8080")
        monkeypatch.setenv("https_proxy", "http://old-proxy:8080")

        mock_db.config = mock_astrbot_config
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        assert lifecycle.log_broker == mock_log_broker
        assert os.environ["http_proxy"] == "http://old-proxy:8080"
        assert os.environ["https_proxy"] == "http://old-proxy:8080"

    @pytest.mark.asyncio
    async def test_stop_restores_proxy_environment(
        self,
        mock_log_broker,
        mock_db,
        mock_astrbot_config,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """A stopped runtime must not rewrite the host proxy environment."""
        mock_astrbot_config.get = MagicMock(
            side_effect=lambda key, default="": {
                "http_proxy": "http://runtime-proxy.example:8080",
                "no_proxy": ["localhost"],
            }.get(key, default)
        )
        mock_db.config = mock_astrbot_config
        monkeypatch.setenv("http_proxy", "http://host-proxy.example:8080")
        monkeypatch.setenv("https_proxy", "http://host-proxy.example:8443")
        monkeypatch.setenv("no_proxy", "host.internal")

        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        assert os.environ["http_proxy"] == "http://host-proxy.example:8080"
        assert os.environ["https_proxy"] == "http://host-proxy.example:8443"
        assert os.environ["no_proxy"] == "host.internal"

        await lifecycle.stop()

        assert os.environ["http_proxy"] == "http://host-proxy.example:8080"
        assert os.environ["https_proxy"] == "http://host-proxy.example:8443"
        assert os.environ["no_proxy"] == "host.internal"


class TestAstrBotCoreLifecycleStop:
    """Tests for AstrBotCoreLifecycle.stop method."""

    @pytest.mark.asyncio
    async def test_stop_without_initialize(self, mock_log_broker, mock_db):
        """Test stop without initialize should not raise errors."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        await lifecycle.stop()
        await lifecycle.stop()

        mock_db.preferences.terminate.assert_not_awaited()
        mock_db.db.close.assert_not_awaited()
        mock_db.html_renderer.terminate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_stop_terminates_preferences_before_database(
        self, mock_log_broker, mock_db
    ):
        """Runtime-owned preferences must stop before their database is disposed."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        cleanup_order: list[str] = []

        async def terminate_preferences() -> None:
            cleanup_order.append("preferences")

        async def close_database() -> None:
            cleanup_order.append("database")

        mock_db.preferences.terminate.side_effect = terminate_preferences
        mock_db.db.close.side_effect = close_database
        lifecycle._register_cleanup("database", mock_db.db.close)
        lifecycle._register_cleanup("preferences", mock_db.preferences.terminate)

        await lifecycle.stop()

        assert cleanup_order == ["preferences", "database"]

    @pytest.mark.asyncio
    async def test_stopped_lifecycle_cannot_be_initialized_again(
        self,
        mock_log_broker,
        mock_db,
    ):
        """A closed cleanup stack must never accept another initialization."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        await lifecycle.stop()

        with pytest.raises(RuntimeError, match="already been stopped"):
            await lifecycle.initialize()

        mock_db.db.initialize.assert_not_awaited()


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

        # Cancellation must propagate so the lifecycle supervisor can finish
        # the matching cleanup path.
        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            with pytest.raises(asyncio.CancelledError):
                await lifecycle._task_wrapper(task)

            # CancelledError should be handled silently
            assert not any(
                "error" in str(call).lower()
                for call in mock_logger.error.call_args_list
            )


class TestAstrBotCoreLifecycleErrorHandling:
    """Tests for AstrBotCoreLifecycle error handling."""

    @pytest.mark.asyncio
    async def test_subagent_orchestrator_error_is_logged(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that subagent orchestrator init errors are logged."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.tool_manager = MagicMock()
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
            lifecycle.provider_manager.tool_manager,
            lifecycle.persona_mgr,
        )
        mock_subagent.reload_from_config.assert_awaited_once_with({})
        assert mock_logger.error.called
        assert any(
            "Subagent orchestrator init failed" in str(call)
            for call in mock_logger.error.call_args_list
        )


class TestAstrBotCoreLifecycleDefaultChatProviderWarning:
    """Tests for startup warning when default chat provider is unset."""

    @staticmethod
    def _make_provider(provider_id: str):
        provider = MagicMock()
        provider.provider_config = {"id": provider_id}
        return provider

    def test_warns_for_multiple_enabled_chat_providers_without_default(
        self, mock_log_broker, mock_db
    ):
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        provider_a = self._make_provider("openai_source/model-a")
        provider_b = self._make_provider("openai_source/model-b")
        lifecycle.provider_manager = MagicMock(
            default_chat_provider_id="",
            provider_insts=[provider_a, provider_b],
        )

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            lifecycle._warn_about_unset_default_chat_provider()

        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args[0][1] == 2
        assert mock_logger.warning.call_args[0][2] == "openai_source/model-a"

    def test_warns_only_once_per_lifecycle(self, mock_log_broker, mock_db):
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.provider_manager = MagicMock(
            default_chat_provider_id="",
            provider_insts=[
                self._make_provider("openai_source/model-a"),
                self._make_provider("openai_source/model-b"),
            ],
            curr_provider_inst=self._make_provider("openai_source/model-a"),
        )

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            lifecycle._warn_about_unset_default_chat_provider()
            lifecycle._warn_about_unset_default_chat_provider()

        mock_logger.warning.assert_called_once()

    def test_does_not_warn_with_single_enabled_chat_provider_without_default(
        self, mock_log_broker, mock_db
    ):
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.provider_manager = MagicMock(
            default_chat_provider_id="",
            provider_insts=[self._make_provider("openai_source/model-a")],
            curr_provider_inst=self._make_provider("openai_source/model-a"),
        )

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            lifecycle._warn_about_unset_default_chat_provider()

        mock_logger.warning.assert_not_called()

    def test_does_not_warn_when_default_chat_provider_is_set(
        self, mock_log_broker, mock_db
    ):
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.provider_manager = MagicMock(
            default_chat_provider_id="openai_source/model-a",
            provider_insts=[
                self._make_provider("openai_source/model-a"),
                self._make_provider("openai_source/model-b"),
            ],
            curr_provider_inst=self._make_provider("openai_source/model-a"),
        )

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            lifecycle._warn_about_unset_default_chat_provider()

        mock_logger.warning.assert_not_called()

    def test_warns_and_fallbacks_to_first_provider_when_curr_provider_inst_is_none(
        self, mock_log_broker, mock_db
    ):
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        provider_a = self._make_provider("openai_source/model-a")
        provider_b = self._make_provider("openai_source/model-b")
        lifecycle.provider_manager = MagicMock(
            default_chat_provider_id="",
            provider_insts=[provider_a, provider_b],
            curr_provider_inst=None,
        )

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            lifecycle._warn_about_unset_default_chat_provider()

        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args[0][1] == 2
        assert mock_logger.warning.call_args[0][2] == "openai_source/model-a"

    def test_warns_when_default_provider_id_does_not_match_any_enabled_provider(
        self, mock_log_broker, mock_db
    ):
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        lifecycle.provider_manager = MagicMock(
            default_chat_provider_id="non-existent-id",
            provider_insts=[
                self._make_provider("openai_source/model-a"),
                self._make_provider("openai_source/model-b"),
            ],
        )

        with patch("astrbot.core.core_lifecycle.logger") as mock_logger:
            lifecycle._warn_about_unset_default_chat_provider()

        mock_logger.warning.assert_called_once()
        assert mock_logger.warning.call_args[0][1] == "non-existent-id"
        assert mock_logger.warning.call_args[0][2] == "openai_source/model-a"


class TestAstrBotCoreLifecycleInitialize:
    """Tests for AstrBotCoreLifecycle.initialize method."""

    @pytest.mark.asyncio
    async def test_initialize_sets_up_all_components(
        self, mock_log_broker, mock_db, mock_astrbot_config
    ):
        """Test that initialize sets up all required components in correct order."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Mock all the dependencies
        mock_db.config = mock_astrbot_config
        mock_db.db.initialize = AsyncMock()
        mock_html_renderer = MagicMock()
        mock_html_renderer.initialize = AsyncMock()

        mock_umop_config_router = MagicMock()
        mock_umop_config_router.initialize = AsyncMock()

        mock_astrbot_config_mgr = MagicMock()
        mock_astrbot_config_mgr.default_conf = {}
        mock_astrbot_config_mgr.confs = {}
        mock_astrbot_config_mgr.initialize = AsyncMock()

        mock_persona_mgr = MagicMock()
        mock_persona_mgr.initialize = AsyncMock()

        mock_persona_runtime_manager = MagicMock()
        mock_persona_runtime_manager.initialize = AsyncMock()

        mock_memory_manager = MagicMock()
        mock_memory_manager.initialize = AsyncMock()

        mock_provider_manager = MagicMock()
        mock_provider_manager.initialize = AsyncMock()

        mock_platform_manager = MagicMock()
        mock_platform_manager.initialize = AsyncMock()

        mock_conversation_manager = MagicMock()

        mock_platform_message_history_manager = MagicMock()

        mock_kb_manager = MagicMock()
        mock_kb_manager.initialize = AsyncMock()

        mock_cron_manager = MagicMock()

        mock_execution_context = MagicMock()
        mock_execution_context._register_tasks = []
        mock_execution_context.background_tasks = set()
        mock_execution_context.session_waiter_registry = SimpleNamespace(
            terminate=AsyncMock()
        )

        mock_plugin_manager = MagicMock()
        mock_plugin_manager.catalog.plugins.all.return_value = []
        mock_plugin_manager.extensions.deactivate = AsyncMock()
        mock_plugin_manager.lifecycle.reload = AsyncMock()
        mock_plugin_manager.lifecycle.terminate_plugin = AsyncMock()
        mock_plugin_manager.lifecycle.stop = AsyncMock()

        mock_pipeline_scheduler = MagicMock()
        mock_pipeline_scheduler.initialize = AsyncMock()

        mock_astrbot_updator = MagicMock()

        mock_event_bus = MagicMock()

        with (
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
                "astrbot.core.core_lifecycle.PersonaRuntimeManager",
                return_value=mock_persona_runtime_manager,
            ),
            patch(
                "astrbot.core.core_lifecycle.MemoryManager",
                return_value=mock_memory_manager,
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
                "astrbot.core.core_lifecycle.CoreExecutionContext",
                return_value=mock_execution_context,
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
                "astrbot.core.core_lifecycle.ProcessRebooter",
                return_value=mock_astrbot_updator,
            ),
            patch("astrbot.core.core_lifecycle.EventBus", return_value=mock_event_bus),
        ):
            await lifecycle.initialize()

        # Verify database initialized
        mock_db.db.initialize.assert_awaited_once()

        # Verify html renderer initialized
        mock_db.html_renderer.initialize.assert_awaited_once()

        # Verify UMOP config router initialized
        mock_umop_config_router.initialize.assert_awaited_once()

        # Verify persona manager initialized
        mock_persona_mgr.initialize.assert_awaited_once()
        mock_persona_runtime_manager.initialize.assert_awaited_once()
        mock_memory_manager.initialize.assert_awaited_once()
        assert (
            lifecycle.execution_context.persona_runtime_manager
            is mock_persona_runtime_manager
        )
        assert lifecycle.execution_context.memory_manager is mock_memory_manager

        # Verify provider manager initialized
        mock_provider_manager.initialize.assert_awaited_once()

        # Verify platform manager initialized
        mock_platform_manager.initialize.assert_awaited_once()

        # Verify plugin manager reloaded
        mock_plugin_manager.lifecycle.reload.assert_awaited_once()

        # Verify knowledge base manager initialized
        mock_kb_manager.initialize.assert_awaited_once()

        # Verify pipeline scheduler loaded
        assert lifecycle.pipeline_scheduler_mapping is not None
        runtime = lifecycle.runtime
        assert runtime.provider_manager is mock_provider_manager
        assert runtime.platform_manager is mock_platform_manager
        assert runtime.plugin_manager is mock_plugin_manager
        assert runtime.pipeline_schedulers is lifecycle.pipeline_scheduler_mapping

    @pytest.mark.asyncio
    async def test_database_initialization_failure_stops_factory_owned_preferences(
        self,
        mock_log_broker,
        mock_db,
    ):
        """A database failure must not leak SharedPreferences' scheduler."""
        cleanup_order: list[str] = []

        async def fail_database_initialize() -> None:
            raise RuntimeError("database failed")

        async def record_cleanup(name: str) -> None:
            cleanup_order.append(name)

        async def cleanup_preferences() -> None:
            await record_cleanup("preferences")

        async def cleanup_metrics() -> None:
            await record_cleanup("metrics")

        async def cleanup_database() -> None:
            await record_cleanup("database")

        mock_db.db.initialize = AsyncMock(side_effect=fail_database_initialize)
        mock_db.preferences.terminate = AsyncMock(side_effect=cleanup_preferences)
        mock_db.metrics.shutdown = AsyncMock(side_effect=cleanup_metrics)
        mock_db.db.close = AsyncMock(side_effect=cleanup_database)
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        with pytest.raises(RuntimeError, match="database failed"):
            await lifecycle.initialize()

        assert cleanup_order == ["preferences", "metrics", "database"]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("failure_point", "expected_cleanup"),
        [
            ("database", ["database"]),
            ("html_renderer", ["html_renderer", "database"]),
            (
                "plugin_reload",
                ["plugin", "memory", "html_renderer", "database"],
            ),
            (
                "provider_initialize",
                ["provider", "plugin", "memory", "html_renderer", "database"],
            ),
            (
                "platform_initialize",
                [
                    "platform",
                    "knowledge_base",
                    "provider",
                    "plugin",
                    "memory",
                    "html_renderer",
                    "database",
                ],
            ),
        ],
    )
    async def test_initialize_failure_cleans_partial_resources_once_in_reverse_order(
        self,
        mock_log_broker,
        mock_db,
        monkeypatch: pytest.MonkeyPatch,
        failure_point: str,
        expected_cleanup: list[str],
    ):
        cleanup_order: list[str] = []

        async def initialize_or_fail(name: str) -> None:
            if failure_point == name:
                raise RuntimeError(f"{name} failed")

        async def record_cleanup(name: str) -> None:
            cleanup_order.append(name)

        def init_action(name: str):
            async def action(*_args) -> None:
                await initialize_or_fail(name)

            return action

        def cleanup_action(name: str):
            async def action(*_args) -> None:
                await record_cleanup(name)

            return action

        mock_db.db.initialize = AsyncMock(side_effect=init_action("database"))
        mock_db.db.close = AsyncMock(side_effect=cleanup_action("database"))
        mock_db.html_renderer.initialize = AsyncMock(
            side_effect=init_action("html_renderer")
        )
        mock_db.html_renderer.terminate = AsyncMock(
            side_effect=cleanup_action("html_renderer")
        )

        umop_router = SimpleNamespace(initialize=AsyncMock())
        config_manager = SimpleNamespace(
            initialize=AsyncMock(),
            default_conf={},
            confs={},
        )
        persona_manager = SimpleNamespace(initialize=AsyncMock())
        persona_runtime_manager = SimpleNamespace(initialize=AsyncMock())
        memory_manager = SimpleNamespace(
            initialize=AsyncMock(),
            terminate=AsyncMock(side_effect=cleanup_action("memory")),
        )
        provider_manager = SimpleNamespace(
            tool_manager=MagicMock(),
            provider_insts=[],
            provider_settings={},
            initialize=AsyncMock(side_effect=init_action("provider_initialize")),
            terminate=AsyncMock(side_effect=cleanup_action("provider")),
        )
        platform_manager = SimpleNamespace(
            initialize=AsyncMock(side_effect=init_action("platform_initialize")),
            terminate=AsyncMock(side_effect=cleanup_action("platform")),
        )
        knowledge_base_manager = SimpleNamespace(
            initialize=AsyncMock(),
            terminate=AsyncMock(side_effect=cleanup_action("knowledge_base")),
        )
        plugin = SimpleNamespace(name="partial-plugin")
        execution_context = SimpleNamespace(
            _register_tasks=[],
            background_tasks=set(),
            session_waiter_registry=SimpleNamespace(terminate=AsyncMock()),
        )
        plugin_manager = SimpleNamespace(
            catalog=SimpleNamespace(
                plugins=SimpleNamespace(all=MagicMock(return_value=[plugin])),
            ),
            extensions=SimpleNamespace(deactivate=AsyncMock()),
            lifecycle=SimpleNamespace(
                reload=AsyncMock(side_effect=init_action("plugin_reload")),
                terminate_plugin=AsyncMock(side_effect=cleanup_action("plugin")),
                stop=AsyncMock(),
            ),
        )
        subagent_orchestrator = SimpleNamespace(reload_from_config=AsyncMock())

        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.configure_trace", lambda _config: None
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.UmopConfigRouter",
            lambda **_kwargs: umop_router,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.AstrBotConfigManager",
            lambda **_kwargs: config_manager,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.PersonaManager",
            lambda *_args: persona_manager,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.PersonaRuntimeManager",
            lambda *_args: persona_runtime_manager,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.MemoryManager", lambda *_args: memory_manager
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.ProviderManager",
            lambda *_args: provider_manager,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.PlatformManager",
            lambda *_args: platform_manager,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.KnowledgeBaseManager",
            lambda *_args: knowledge_base_manager,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.CoreExecutionContext",
            lambda *_args, **_kwargs: execution_context,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.PluginManager",
            lambda *_args: plugin_manager,
        )
        monkeypatch.setattr(
            "astrbot.core.core_lifecycle.SubAgentOrchestrator",
            lambda *_args: subagent_orchestrator,
        )

        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)
        with pytest.raises(RuntimeError, match="failed"):
            await lifecycle.initialize()
        await lifecycle.stop()

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = lifecycle.runtime

        assert cleanup_order == expected_cleanup
        if "plugin" in expected_cleanup:
            plugin_manager.extensions.deactivate.assert_awaited_once_with(
                plugin,
                reason="shutdown",
            )
        assert mock_db.db.close.await_count == int("database" in expected_cleanup)
        assert mock_db.html_renderer.terminate.await_count == int(
            "html_renderer" in expected_cleanup
        )
        assert plugin_manager.lifecycle.terminate_plugin.await_count == int(
            "plugin" in expected_cleanup
        )
        assert provider_manager.terminate.await_count == int(
            "provider" in expected_cleanup
        )
        assert platform_manager.terminate.await_count == int(
            "platform" in expected_cleanup
        )


class TestAstrBotCoreLifecycleStart:
    """Tests for AstrBotCoreLifecycle.start method."""

    @pytest.mark.asyncio
    async def test_start_rejects_invalid_lifecycle_states(
        self,
        mock_log_broker,
        mock_db,
    ):
        """A lifecycle has one start transition after initialization only."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        with pytest.raises(RuntimeError, match="must be initialized"):
            await lifecycle.start()

        lifecycle._initialized = True
        lifecycle._started = True
        with pytest.raises(RuntimeError, match="already been started"):
            await lifecycle.start()

        lifecycle._started = False
        lifecycle._stopped = True
        with pytest.raises(RuntimeError, match="already been stopped"):
            await lifecycle.start()

    @pytest.mark.asyncio
    async def test_start_loads_event_bus_and_runs(self, mock_log_broker, mock_db):
        """Test that start loads event bus and runs tasks."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Set up minimal state
        lifecycle.event_bus = MagicMock()
        lifecycle.event_bus.dispatch = AsyncMock()

        lifecycle.cron_manager = None

        lifecycle.temp_dir_cleaner = None

        lifecycle.execution_context = MagicMock()
        lifecycle.execution_context._register_tasks = []
        lifecycle._initialized = True

        lifecycle.plugin_manager = SimpleNamespace(
            catalog=SimpleNamespace(
                plugins=SimpleNamespace(all=MagicMock(return_value=[])),
            ),
            extensions=SimpleNamespace(deactivate=AsyncMock()),
            lifecycle=SimpleNamespace(
                reload=AsyncMock(),
                terminate_plugin=AsyncMock(),
                stop=AsyncMock(),
            ),
        )

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle.dashboard_shutdown_event = asyncio.Event()

        lifecycle.curr_tasks = []

        with patch("astrbot.core.core_lifecycle.logger"):
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

        lifecycle.execution_context = MagicMock()
        lifecycle.execution_context._register_tasks = []
        lifecycle._initialized = True

        lifecycle.plugin_manager = SimpleNamespace(
            catalog=SimpleNamespace(
                plugins=SimpleNamespace(all=MagicMock(return_value=[])),
            ),
            extensions=SimpleNamespace(deactivate=AsyncMock()),
            lifecycle=SimpleNamespace(
                reload=AsyncMock(),
                terminate_plugin=AsyncMock(),
                stop=AsyncMock(),
            ),
        )

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
        mock_db.catalogs.plugins.publish(
            StarMetadata(name="Test Handler", module_path="test_module")
        )

        with (
            patch.object(
                mock_db.catalogs.handlers,
                "get_handlers_by_event_type",
                return_value=[mock_handler],
            ),
            patch("astrbot.core.core_lifecycle.logger"),
        ):
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

        async def wait_forever() -> None:
            await asyncio.Event().wait()

        task1 = asyncio.create_task(wait_forever(), name="task1")
        task2 = asyncio.create_task(wait_forever(), name="task2")
        lifecycle.curr_tasks = [task1, task2]

        await lifecycle.stop()

        assert task1.cancelled()
        assert task2.cancelled()

    @pytest.mark.asyncio
    async def test_stop_terminates_all_managers(self, mock_log_broker, mock_db):
        """Test that stop terminates all managers in correct order."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        mock_html_renderer = MagicMock()
        mock_html_renderer.terminate = AsyncMock()
        mock_db.html_renderer = mock_html_renderer
        lifecycle._register_cleanup("HTML renderer", mock_html_renderer.terminate)
        lifecycle._register_cleanup(
            "provider manager", lifecycle.provider_manager.terminate
        )
        lifecycle._register_cleanup(
            "knowledge base manager", lifecycle.kb_manager.terminate
        )
        lifecycle._register_cleanup(
            "platform manager", lifecycle.platform_manager.terminate
        )
        await lifecycle.stop()

        # Verify all managers were terminated
        lifecycle.provider_manager.terminate.assert_awaited_once()
        lifecycle.platform_manager.terminate.assert_awaited_once()
        lifecycle.kb_manager.terminate.assert_awaited_once()
        mock_html_renderer.terminate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_handles_plugin_termination_error(
        self, mock_log_broker, mock_db
    ):
        """Test that stop handles plugin termination errors gracefully."""
        lifecycle = AstrBotCoreLifecycle(mock_log_broker, mock_db)

        # Create a mock plugin that raises exception on termination
        mock_plugin = MagicMock()
        mock_plugin.name = "test_plugin"

        lifecycle.plugin_manager = SimpleNamespace(
            catalog=SimpleNamespace(
                plugins=SimpleNamespace(all=MagicMock(return_value=[mock_plugin])),
            ),
            extensions=SimpleNamespace(deactivate=AsyncMock()),
            lifecycle=SimpleNamespace(
                reload=AsyncMock(),
                terminate_plugin=AsyncMock(
                    side_effect=Exception("Plugin termination failed"),
                ),
                stop=AsyncMock(),
            ),
        )

        lifecycle.provider_manager = MagicMock()
        lifecycle.provider_manager.terminate = AsyncMock()

        lifecycle.platform_manager = MagicMock()
        lifecycle.platform_manager.terminate = AsyncMock()

        lifecycle.kb_manager = MagicMock()
        lifecycle.kb_manager.terminate = AsyncMock()

        lifecycle._register_cleanup("plugin manager", lifecycle._terminate_plugins)

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

        lifecycle.process_rebooter = MagicMock()
        mock_html_renderer = MagicMock()
        mock_html_renderer.terminate = AsyncMock()

        with (
            patch("astrbot.core.core_lifecycle.threading.Thread") as mock_thread,
        ):
            mock_db.html_renderer = mock_html_renderer
            await lifecycle.restart()

            # Verify managers were terminated
            lifecycle.provider_manager.terminate.assert_awaited_once()
            lifecycle.platform_manager.terminate.assert_awaited_once()
            lifecycle.kb_manager.terminate.assert_awaited_once()
            mock_html_renderer.terminate.assert_awaited_once()

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
            lifecycle.execution_context = MagicMock()

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
        lifecycle.execution_context = MagicMock()
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
