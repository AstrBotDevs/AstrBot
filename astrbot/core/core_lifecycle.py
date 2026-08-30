"""Astrbot 核心生命周期管理类, 负责管理 AstrBot 的启动、停止、重启等操作.

该类负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus等。
该类还负责加载和执行插件, 以及处理事件总线的分发。

工作流程:
1. 初始化所有组件
2. 启动事件总线和任务, 所有任务都在这里运行
3. 执行启动完成事件钩子
"""

import asyncio
import os
import threading
import time
import traceback
from asyncio import Queue
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from pathlib import Path

from astrbot import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.auth.service import AuthorizationService
from astrbot.core.config.default import VERSION
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.core_runtime import CoreRuntime
from astrbot.core.cron import CronJobManager
from astrbot.core.db.sqlite import SQLiteDatabase
from astrbot.core.execution_context import CoreExecutionContext
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.log import LogBroker, LogManager
from astrbot.core.memory import MemoryManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.persona_runtime import PersonaRuntimeManager
from astrbot.core.pipeline.scheduler import PipelineContext, PipelineScheduler
from astrbot.core.pipeline.turn_window import TurnWindowManager
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.process_reboot import ProcessRebooter
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.runtime_services import RuntimeServices
from astrbot.core.skills.skill_manager import SkillManager
from astrbot.core.star.star_handler import EventType
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.utils.astrbot_path import get_astrbot_path
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.event_loop_diagnostics import (
    create_event_loop_diagnostic_tasks,
)
from astrbot.core.utils.task_utils import cancel_tracked_tasks, create_tracked_task
from astrbot.core.utils.temp_dir_cleaner import TempDirCleaner
from astrbot.core.utils.trace import configure_trace

from .event_bus import EventBus

EVENT_QUEUE_MAXSIZE = 1024
_PROXY_ENVIRONMENT_KEYS = ("https_proxy", "http_proxy", "no_proxy")


class AstrBotCoreLifecycle:
    """AstrBot 核心生命周期管理类, 负责管理 AstrBot 的启动、停止、重启等操作.

    该类负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、
    EventBus 等。
    该类还负责加载和执行插件, 以及处理事件总线的分发。
    """

    def __init__(self, log_broker: LogBroker, services: RuntimeServices) -> None:
        self.log_broker = log_broker  # 初始化日志代理
        self.services = services
        self.astrbot_config = services.config
        self.db: SQLiteDatabase = services.db

        self.subagent_orchestrator: SubAgentOrchestrator | None = None
        self.cron_manager: CronJobManager | None = None
        self.temp_dir_cleaner: TempDirCleaner | None = None
        self.umop_config_router: UmopConfigRouter | None = None
        self.astrbot_config_mgr: AstrBotConfigManager | None = None
        self.persona_mgr: PersonaManager | None = None
        self.persona_runtime_manager: PersonaRuntimeManager | None = None
        self.memory_manager: MemoryManager | None = None
        self.provider_manager: ProviderManager | None = None
        self.platform_manager: PlatformManager | None = None
        self.conversation_manager: ConversationManager | None = None
        self.platform_message_history_manager: PlatformMessageHistoryManager | None = (
            None
        )
        self.kb_manager: KnowledgeBaseManager | None = None
        self.execution_context: CoreExecutionContext | None = None
        self.plugin_manager: PluginManager | None = None
        self.event_bus: EventBus | None = None
        self.dashboard_shutdown_event: asyncio.Event | None = None
        self.pipeline_scheduler_mapping: dict[str, PipelineScheduler] = {}
        self.curr_tasks: list[asyncio.Task] = []
        self._default_chat_provider_warning_emitted = False
        self._background_tasks: set[asyncio.Task] = set()
        self._stop_lock = asyncio.Lock()
        self._cleanup_stack = AsyncExitStack()
        self._cleanup_stack_closed = False
        self._runtime: CoreRuntime | None = None
        self._initializing = False
        self._initialized = False
        self._started = False
        self._stopped = False

        # Proxy variables are process-wide, but the lifecycle is their owner in
        # this process.  Preserve the prior values so that stopping an embedded
        # runtime does not silently alter its host's network configuration.
        self._proxy_environment_before = {
            name: os.environ.get(name) for name in _PROXY_ENVIRONMENT_KEYS
        }
        self._proxy_environment_after: dict[str, str | None] = {}
        self._apply_proxy_environment()
        self._register_cleanup(
            "HTTP proxy environment",
            self._restore_proxy_environment,
        )

    def _set_proxy_environment_value(self, name: str, value: str | None) -> None:
        """Set one owned proxy value and remember the state we installed."""
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value
        self._proxy_environment_after[name] = value

    def _apply_proxy_environment(self) -> None:
        """Do not publish configured proxies through process environment variables.

        Provider and platform clients now receive an explicit ``ProxyRoute``.
        Leaving the host ``HTTP_PROXY`` untouched avoids leaking AstrBot's
        route into unrelated libraries, and an empty global proxy no longer
        inherits the developer's shell proxy.
        """
        from astrbot.core.utils.proxy_route import set_global_network_config

        set_global_network_config(
            http_proxy=str(self.astrbot_config.get("http_proxy", "") or ""),
            no_proxy=self.astrbot_config.get("no_proxy", []),
        )
        logger.debug(
            "Skipping process HTTP_PROXY export; clients use explicit ProxyRoute"
        )

    async def _restore_proxy_environment(self) -> None:
        """Restore proxy variables only when they still hold our values."""
        for name in _PROXY_ENVIRONMENT_KEYS:
            if os.environ.get(name) != self._proxy_environment_after.get(name):
                continue
            previous_value = self._proxy_environment_before[name]
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value

    @property
    def runtime(self) -> CoreRuntime:
        """Return the completed runtime after successful initialization.

        Raises:
            RuntimeError: If initialization has not completed successfully.
        """

        if self._runtime is None:
            raise RuntimeError("AstrBot core runtime is not initialized")
        return self._runtime

    def _register_cleanup(
        self,
        label: str,
        action: Callable[[], Awaitable[None]],
    ) -> None:
        """Add an idempotent best-effort resource cleanup to the LIFO stack."""

        async def cleanup() -> None:
            try:
                await action()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to clean up %s: %s",
                    label,
                    safe_error("", exc),
                )

        self._cleanup_stack.push_async_callback(cleanup)

    async def _terminate_plugins(self) -> None:
        """Terminate every plugin that was published before shutdown began."""

        plugin_manager = self.plugin_manager
        if plugin_manager is None:
            return
        try:
            await plugin_manager.lifecycle.stop()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Failed to stop plugin lifecycle tasks during shutdown: %s",
                safe_error("", exc),
            )
        try:
            plugins = list(plugin_manager.catalog.plugins.all())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                "Failed to enumerate plugins during shutdown: %s",
                safe_error("", exc),
            )
            return

        for plugin in plugins:
            try:
                await plugin_manager.extensions.deactivate(
                    plugin,
                    reason="shutdown",
                )
                await plugin_manager.lifecycle.terminate_plugin(plugin)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Plugin %s failed to terminate: %s",
                    plugin.name,
                    safe_error("", exc),
                )

    async def _init_or_reload_subagent_orchestrator(self) -> None:
        """Create (if needed) and reload the subagent orchestrator from config.

        This keeps lifecycle wiring in one place while allowing the orchestrator
        to manage enable/disable and tool registration details.
        """
        provider_manager = self.provider_manager
        persona_mgr = self.persona_mgr
        if provider_manager is None or persona_mgr is None:
            raise RuntimeError(
                "Subagent orchestrator requires initialized provider and persona managers"
            )

        try:
            orchestrator = self.subagent_orchestrator
            if orchestrator is None:
                orchestrator = SubAgentOrchestrator(
                    provider_manager.tool_manager,
                    persona_mgr,
                )
                self.subagent_orchestrator = orchestrator
            await orchestrator.reload_from_config(
                self.astrbot_config.get("subagent_orchestrator", {}),
            )
        except Exception as e:
            logger.error(
                "Subagent orchestrator init failed: %s",
                safe_error("", e),
            )

    def _warn_about_unset_default_chat_provider(self) -> None:
        if self._default_chat_provider_warning_emitted:
            return

        pm = getattr(self, "provider_manager", None)
        if not pm:
            return

        providers = pm.provider_insts
        if len(providers) == 0:
            return

        default_id = getattr(pm, "default_chat_provider_id", "")
        fallback = providers[0]
        fallback_id = fallback.provider_config.get("id") or "unknown"

        if not default_id:
            if len(providers) <= 1:
                return
            self._default_chat_provider_warning_emitted = True
            logger.warning(
                "Detected %d enabled chat providers but `agent_runner.config.model.provider_id` is empty. "
                "AstrBot will use `%s` as the startup fallback chat provider. "
                "Set a default chat model in the WebUI configuration page to avoid unexpected provider switching.",
                len(providers),
                fallback_id,
            )
            return

        found = any((p.provider_config.get("id") == default_id) for p in providers)
        if not found:
            self._default_chat_provider_warning_emitted = True
            logger.warning(
                "Configured Agent Runner model provider ID `%s` does not match an enabled provider. "
                "AstrBot will use `%s` as the fallback chat provider. "
                "Please check the WebUI configuration page.",
                default_id,
                fallback_id,
            )

    async def initialize(self) -> None:
        """初始化 AstrBot 核心生命周期管理类.

        负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus、ProcessRebooter等。
        """
        if self._stopped:
            raise RuntimeError(
                "AstrBot core lifecycle has already been stopped and cannot be reused"
            )
        if self._initialized:
            return
        if self._initializing:
            raise RuntimeError(
                "AstrBot core lifecycle initialization is already running"
            )

        self._initializing = True
        try:
            await self._initialize()
        except BaseException:
            await self.stop()
            raise
        finally:
            self._initializing = False
        self._initialized = True

    async def _initialize(self) -> None:
        """Initialize core resources in dependency order."""
        if getattr(self.services, "authorization", None) is None:
            self.services.authorization = AuthorizationService(self.db)
        # 初始化日志代理
        logger.info("AstrBot v" + VERSION)
        if os.environ.get("TESTING", ""):
            LogManager.configure_logger(
                logger, self.astrbot_config, override_level="DEBUG"
            )
            LogManager.configure_trace_logger(self.astrbot_config)
        else:
            LogManager.configure_logger(logger, self.astrbot_config)
            LogManager.configure_trace_logger(self.astrbot_config)

        self._register_cleanup("database", self.db.close)
        authorization = self.services.authorization
        if authorization is None:
            raise RuntimeError("AuthorizationService is required")
        if isinstance(self.db, SQLiteDatabase):
            self._register_cleanup("authorization", authorization.close)
        self._register_cleanup(
            "file token artifacts",
            self.services.file_token_service.shutdown,
        )
        self._register_cleanup("metrics", self.services.metrics.shutdown)
        self._register_cleanup(
            "shared preferences",
            self.services.preferences.terminate,
        )
        await self.db.initialize()
        if isinstance(self.db, SQLiteDatabase):
            await authorization.start()
        self.services.catalogs.tools.bind_authorization(authorization)
        configure_trace(self.astrbot_config)

        self._register_cleanup(
            "HTML renderer",
            self.services.html_renderer.terminate,
        )
        await self.services.html_renderer.initialize()

        # 初始化 UMOP 配置路由器
        self.umop_config_router = UmopConfigRouter(sp=self.services.preferences)
        await self.umop_config_router.initialize()

        # 初始化 AstrBot 配置管理器
        config_manager = AstrBotConfigManager(
            default_config=self.astrbot_config,
            ucr=self.umop_config_router,
            sp=self.services.preferences,
        )
        self.astrbot_config_mgr = config_manager
        await config_manager.initialize()
        self.temp_dir_cleaner = TempDirCleaner(
            max_size_getter=lambda: config_manager.default_conf.get(
                TempDirCleaner.CONFIG_KEY,
                TempDirCleaner.DEFAULT_MAX_SIZE,
            ),
        )

        # 初始化事件队列
        self.event_queue = Queue(maxsize=EVENT_QUEUE_MAXSIZE)
        self.turn_window_manager = TurnWindowManager(self._enqueue_turn_event)

        # 初始化人格管理器
        self.persona_mgr = PersonaManager(
            self.db,
            self.astrbot_config_mgr,
            self.services.preferences,
        )
        await self.persona_mgr.initialize()

        self.persona_runtime_manager = PersonaRuntimeManager(self.db)
        await self.persona_runtime_manager.initialize()

        self.memory_manager = MemoryManager(self.db)
        self._register_cleanup("memory manager", self.memory_manager.terminate)
        await self.memory_manager.initialize()

        # 初始化供应商管理器
        self.provider_manager = ProviderManager(
            self.astrbot_config_mgr,
            self.persona_mgr,
            self.services.preferences,
            self.services.catalogs.providers,
            self.services.catalogs.tools,
        )

        # 初始化平台管理器
        self.platform_manager = PlatformManager(
            self.astrbot_config,
            self.event_queue,
            self.services.webchat_queue_manager,
            self.services.catalogs.platforms,
            self.services.catalogs.handlers,
            self.services.catalogs.plugins,
            self.services.metrics,
        )
        self.platform_manager.database = self.db
        self.platform_manager.preferences = self.services.preferences

        # 初始化对话管理器
        self.conversation_manager = ConversationManager(
            self.db,
            self.services.preferences,
        )

        # 初始化平台消息历史管理器
        self.platform_message_history_manager = PlatformMessageHistoryManager(self.db)

        # 初始化知识库管理器
        self.kb_manager = KnowledgeBaseManager(self.provider_manager)

        # 初始化 CronJob 管理器
        self.cron_manager = CronJobManager(self.db)

        # Dynamic subagents (handoff tools) from config.
        await self._init_or_reload_subagent_orchestrator()

        # Initialize runtime-owned execution dependencies.
        execution_context = CoreExecutionContext(
            self.event_queue,
            self.astrbot_config,
            self.db,
            self.provider_manager,
            self.platform_manager,
            self.conversation_manager,
            self.platform_message_history_manager,
            self.persona_mgr,
            self.astrbot_config_mgr,
            self.kb_manager,
            self.cron_manager,
            self.services.preferences,
            self.services.html_renderer,
            self.services.file_token_service,
            self.services.catalogs,
            self.services.computer_runtime,
            self.services.tool_image_cache,
            self.subagent_orchestrator,
            demo_mode=self.services.demo_mode,
            follow_up_coordinator=self.services.follow_up_coordinator,
            llm_metadata_catalog=self.services.llm_metadata_catalog,
            metrics=self.services.metrics,
            authorization=self.services.authorization,
        )
        self.execution_context = execution_context
        execution_context.persona_runtime_manager = self.persona_runtime_manager
        execution_context.memory_manager = self.memory_manager
        execution_context.turn_window_manager = self.turn_window_manager
        self.platform_manager.typing_signal = self._on_typing_signal
        self._register_cleanup(
            "turn window manager",
            self.turn_window_manager.terminate,
        )
        self._register_cleanup(
            "follow-up coordinator",
            self.services.follow_up_coordinator.terminate,
        )
        self._register_cleanup(
            "execution context background tasks",
            lambda: cancel_tracked_tasks(execution_context.background_tasks),
        )
        self._register_cleanup(
            "session waiter registry",
            execution_context.session_waiter_registry.terminate,
        )

        # 初始化插件管理器
        self.plugin_manager = PluginManager(
            execution_context,
            self.astrbot_config,
            self.services.preferences,
            self.services.pip_installer,
            self.services.catalogs,
        )

        # 扫描、注册插件、实例化插件类
        self._register_cleanup("plugin manager", self._terminate_plugins)
        await self.plugin_manager.lifecycle.reload()
        self.services.catalogs.builtin_skills.bind(
            self.services.catalogs.plugins,
            Path(get_astrbot_path()) / "astrbot" / "builtin_stars",
        )
        skill_manager = SkillManager(
            builtin_skill_catalog=self.services.catalogs.builtin_skills,
        )
        execution_context.skill_manager = skill_manager
        self.services.computer_runtime.bind_skill_manager(
            skill_manager,
            self.services.catalogs.plugins,
        )
        # 根据配置实例化各个 Provider
        self._default_chat_provider_warning_emitted = False
        self._register_cleanup("provider manager", self.provider_manager.terminate)
        await self.provider_manager.initialize()
        self._warn_about_unset_default_chat_provider()

        self._register_cleanup("knowledge base manager", self.kb_manager.terminate)
        await self.kb_manager.initialize()

        # 初始化消息事件流水线调度器
        self.pipeline_scheduler_mapping = await self.load_pipeline_scheduler()

        self.process_rebooter = ProcessRebooter()

        # 初始化事件总线
        self.event_bus = EventBus(
            self.event_queue,
            self.pipeline_scheduler_mapping,
            self.astrbot_config_mgr,
        )

        # 记录启动时间
        self.start_time = int(time.time())

        # 初始化当前任务列表
        self.curr_tasks: list[asyncio.Task] = []

        # 根据配置实例化各个平台适配器
        self._register_cleanup(
            "WebChat run coordinator",
            self.services.webchat_run_coordinator.terminate,
        )
        self._register_cleanup(
            "computer runtime",
            self.services.computer_runtime.terminate,
        )
        self._register_cleanup("platform manager", self.platform_manager.terminate)
        await self.platform_manager.initialize()

        # 初始化关闭控制面板的事件
        self.dashboard_shutdown_event = asyncio.Event()

        create_tracked_task(
            self._background_tasks,
            self.services.llm_metadata_catalog.refresh(),
            name="update_llm_metadata",
        )

        assert self.astrbot_config_mgr is not None
        assert self.provider_manager is not None
        assert self.platform_manager is not None
        assert self.conversation_manager is not None
        assert self.platform_message_history_manager is not None
        assert self.persona_mgr is not None
        assert self.persona_runtime_manager is not None
        assert self.memory_manager is not None
        assert self.kb_manager is not None
        assert self.cron_manager is not None
        assert self.plugin_manager is not None
        assert self.execution_context is not None
        assert self.umop_config_router is not None
        assert self.subagent_orchestrator is not None
        assert self.event_bus is not None
        assert self.dashboard_shutdown_event is not None
        self._runtime = CoreRuntime(
            services=self.services,
            log_broker=self.log_broker,
            catalogs=self.services.catalogs,
            webchat_run_coordinator=self.services.webchat_run_coordinator,
            astrbot_config=self.astrbot_config,
            astrbot_config_mgr=self.astrbot_config_mgr,
            provider_manager=self.provider_manager,
            platform_manager=self.platform_manager,
            conversation_manager=self.conversation_manager,
            platform_message_history_manager=self.platform_message_history_manager,
            persona_mgr=self.persona_mgr,
            persona_runtime_manager=self.persona_runtime_manager,
            memory_manager=self.memory_manager,
            knowledge_base_manager=self.kb_manager,
            cron_manager=self.cron_manager,
            plugin_manager=self.plugin_manager,
            execution_context=self.execution_context,
            umop_config_router=self.umop_config_router,
            subagent_orchestrator=self.subagent_orchestrator,
            pipeline_schedulers=self.pipeline_scheduler_mapping,
            event_queue=self.event_queue,
            event_bus=self.event_bus,
            dashboard_shutdown_event=self.dashboard_shutdown_event,
            start_time=self.start_time,
        )

    def _load(self) -> None:
        """加载事件总线和任务并初始化."""
        event_bus = self.event_bus
        execution_context = self.execution_context
        if event_bus is None or execution_context is None:
            raise RuntimeError("AstrBot core lifecycle is not initialized")

        # 创建一个异步任务来执行事件总线的 dispatch() 方法
        # dispatch是一个无限循环的协程, 从事件队列中获取事件并处理
        event_bus_task = asyncio.create_task(
            event_bus.dispatch(),
            name="event_bus",
        )
        cron_manager = self.cron_manager
        cron_task = None
        if cron_manager is not None:
            cron_task = asyncio.create_task(
                cron_manager.start(execution_context),
                name="cron_manager",
            )
        temp_dir_cleaner = self.temp_dir_cleaner
        temp_dir_cleaner_task = None
        if temp_dir_cleaner is not None:
            temp_dir_cleaner_task = asyncio.create_task(
                temp_dir_cleaner.run(),
                name="temp_dir_cleaner",
            )
        diagnostic_tasks = create_event_loop_diagnostic_tasks()

        # 把插件中注册的所有协程函数注册到事件总线中并执行
        extra_tasks = []
        for task in execution_context._register_tasks:
            extra_tasks.append(asyncio.create_task(task, name=task.__name__))  # type: ignore

        tasks_ = [
            event_bus_task,
            *diagnostic_tasks,
            *(extra_tasks if extra_tasks else []),
        ]
        if cron_task:
            tasks_.append(cron_task)
        if temp_dir_cleaner_task:
            tasks_.append(temp_dir_cleaner_task)
        for task in tasks_:
            self.curr_tasks.append(
                asyncio.create_task(self._task_wrapper(task), name=task.get_name()),
            )

        if cron_manager is not None:
            self._register_cleanup("cron manager", cron_manager.shutdown)
        self._register_cleanup("event bus", event_bus.shutdown)
        if temp_dir_cleaner is not None:
            self._register_cleanup(
                "temporary directory cleaner",
                temp_dir_cleaner.stop,
            )

    async def _task_wrapper(self, task: asyncio.Task) -> None:
        """异步任务包装器, 用于处理异步任务执行中出现的各种异常.

        Args:
            task (asyncio.Task): 要执行的异步任务

        """
        try:
            await task
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # 获取完整的异常堆栈信息, 按行分割并记录到日志中
            logger.error(f"------- 任务 {task.get_name()} 发生错误: {e}")
            for line in traceback.format_exc().split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

    async def start(self) -> None:
        """启动 AstrBot 核心生命周期管理类.

        用load加载事件总线和任务并初始化, 执行启动完成事件钩子
        """
        if self._stopped:
            raise RuntimeError("AstrBot core lifecycle has already been stopped")
        if not self._initialized:
            raise RuntimeError(
                "AstrBot core lifecycle must be initialized before it can start"
            )
        if self._started:
            raise RuntimeError("AstrBot core lifecycle has already been started")
        self._started = True
        self._load()
        logger.info("AstrBot started.")

        # 执行启动完成事件钩子
        handlers = self.services.catalogs.handlers.get_handlers_by_event_type(
            EventType.OnAstrBotLoadedEvent,
        )
        for handler in handlers:
            try:
                plugin = self.services.catalogs.plugins.get_by_module(
                    handler.handler_module_path
                )
                logger.info(
                    "hook(on_astrbot_loaded) -> %s - %s",
                    plugin.name if plugin else handler.handler_module_path,
                    handler.handler_name,
                )
                await handler.handler()
            except asyncio.CancelledError:
                raise
            except KeyboardInterrupt, SystemExit:
                raise
            except Exception:
                logger.error(traceback.format_exc())

        # 同时运行curr_tasks中的所有任务
        await asyncio.gather(*self.curr_tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Stop initialized resources once, including partially initialized state."""

        async with self._stop_lock:
            if self._stopped:
                return

            tasks = self.curr_tasks
            self.curr_tasks = []
            for task in tasks:
                task.cancel()

            if self.dashboard_shutdown_event is not None:
                self.dashboard_shutdown_event.set()

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

            await cancel_tracked_tasks(self._background_tasks)

            if not self._cleanup_stack_closed:
                self._cleanup_stack_closed = True
                await self._cleanup_stack.aclose()

            self._initialized = False
            self._stopped = True

    async def restart(self) -> None:
        """重启 AstrBot 核心生命周期管理类, 终止各个管理器并重新加载平台实例"""
        provider_manager = self.provider_manager
        platform_manager = self.platform_manager
        knowledge_base_manager = self.kb_manager
        dashboard_shutdown_event = self.dashboard_shutdown_event
        if (
            provider_manager is None
            or platform_manager is None
            or knowledge_base_manager is None
            or dashboard_shutdown_event is None
        ):
            raise RuntimeError("AstrBot core lifecycle is not initialized")

        await provider_manager.terminate()
        await platform_manager.terminate()
        await knowledge_base_manager.terminate()
        await self.services.html_renderer.terminate()
        dashboard_shutdown_event.set()
        threading.Thread(
            target=self.process_rebooter.reboot,
            name="restart",
            daemon=True,
        ).start()

    async def load_pipeline_scheduler(self) -> dict[str, PipelineScheduler]:
        """加载消息事件流水线调度器.

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射

        """
        config_manager = self.astrbot_config_mgr
        plugin_manager = self.plugin_manager
        execution_context = self.execution_context
        if (
            config_manager is None
            or plugin_manager is None
            or execution_context is None
        ):
            raise RuntimeError("Pipeline dependencies are not initialized")

        mapping = {}
        for conf_id, ab_config in config_manager.confs.items():
            scheduler = PipelineScheduler(
                PipelineContext(
                    ab_config,
                    plugin_manager.catalog,
                    execution_context,
                    self.services.catalogs.handlers,
                    self.services.catalogs.plugins,
                    conf_id,
                    self.services.html_renderer,
                    self.services.file_token_service,
                    self.services.preferences,
                    getattr(self.services, "authorization", None),
                ),
            )
            await scheduler.initialize()
            mapping[conf_id] = scheduler
        return mapping

    def _on_typing_signal(self, key: str, event_type: int) -> None:
        """Pause or resume turn flush from an adapter typing notice."""
        if event_type == 1:
            self.turn_window_manager.pause_typing(key)
            return
        self.turn_window_manager.resume_typing(key)

    def _enqueue_turn_event(self, event) -> bool:
        """Requeue a manager-built flush event from the waking stage."""
        try:
            self.event_queue.put_nowait(event)
        except Exception:
            return False
        return True

    async def reload_pipeline_scheduler(self, conf_id: str) -> None:
        """重新加载消息事件流水线调度器.

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射

        """
        config_manager = self.astrbot_config_mgr
        if config_manager is None:
            raise RuntimeError("Configuration manager is not initialized")
        ab_config = config_manager.confs.get(conf_id)
        if not ab_config:
            raise ValueError(f"配置文件 {conf_id} 不存在")

        plugin_manager = self.plugin_manager
        execution_context = self.execution_context
        if plugin_manager is None or execution_context is None:
            raise RuntimeError("Pipeline dependencies are not initialized")

        scheduler = PipelineScheduler(
            PipelineContext(
                ab_config,
                plugin_manager.catalog,
                execution_context,
                self.services.catalogs.handlers,
                self.services.catalogs.plugins,
                conf_id,
                self.services.html_renderer,
                self.services.file_token_service,
                self.services.preferences,
                getattr(self.services, "authorization", None),
            ),
        )
        await scheduler.initialize()
        self.pipeline_scheduler_mapping[conf_id] = scheduler
        manager = getattr(self, "turn_window_manager", None)
        if manager is not None:
            manager.discard_all(f"reload pipeline {conf_id}")

    async def remove_pipeline_scheduler(self, conf_id: str) -> None:
        """Remove the scheduler associated with a deleted configuration profile."""
        self.pipeline_scheduler_mapping.pop(conf_id, None)
