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
from enum import Enum


class LifecycleState(Enum):
    CREATED = "created"
    CORE_READY = "core_ready"
    RUNTIME_READY = "runtime_ready"
    RUNTIME_FAILED = "runtime_failed"


from astrbot.api import logger, sp
from astrbot.core import LogBroker, LogManager
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.default import VERSION
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron import CronJobManager
from astrbot.core.db import BaseDatabase
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.pipeline.scheduler import PipelineContext, PipelineScheduler
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import EventType, star_handlers_registry, star_map
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.subagent_orchestrator import SubAgentOrchestrator
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.updator import AstrBotUpdator
from astrbot.core.utils.llm_metadata import update_llm_metadata
from astrbot.core.utils.migra_helper import migra
from astrbot.core.utils.temp_dir_cleaner import TempDirCleaner

from . import astrbot_config, html_renderer
from .event_bus import EventBus


class AstrBotCoreLifecycle:
    """AstrBot 核心生命周期管理类, 负责管理 AstrBot 的启动、停止、重启等操作.

    该类负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、
    EventBus 等。
    该类还负责加载和执行插件, 以及处理事件总线的分发。
    """

    def __init__(self, log_broker: LogBroker, db: BaseDatabase) -> None:
        self.log_broker = log_broker  # 初始化日志代理
        self.astrbot_config = astrbot_config  # 初始化配置
        self.db = db  # 初始化数据库

        self.subagent_orchestrator: SubAgentOrchestrator | None = None
        self.cron_manager: CronJobManager | None = None
        self.temp_dir_cleaner: TempDirCleaner | None = None

        # 设置代理
        proxy_config = self.astrbot_config.get("http_proxy", "")
        if proxy_config != "":
            os.environ["https_proxy"] = proxy_config
            os.environ["http_proxy"] = proxy_config
            logger.debug(f"Using proxy: {proxy_config}")
            # 设置 no_proxy
            no_proxy_list = self.astrbot_config.get("no_proxy", [])
            os.environ["no_proxy"] = ",".join(no_proxy_list)
        else:
            # 清空代理环境变量
            if "https_proxy" in os.environ:
                del os.environ["https_proxy"]
            if "http_proxy" in os.environ:
                del os.environ["http_proxy"]
            if "no_proxy" in os.environ:
                del os.environ["no_proxy"]
            logger.debug("HTTP proxy cleared")

        # Lifecycle compatibility fields
        # Expose lifecycle state and event flags expected by tests and older consumers.
        self.lifecycle_state = LifecycleState.CREATED
        self.core_initialized = False
        self.runtime_ready = False
        self.runtime_failed = False
        self.runtime_ready_event = asyncio.Event()
        self.runtime_failed_event = asyncio.Event()
        self.runtime_bootstrap_error = None
        self.start_time = 0
        self.runtime_bootstrap_task = None

        # runtime placeholders and defaults expected by tests and runtime code.
        # These used to be set later in the full initialize() path; tests and some
        # callers expect these attributes to exist even when only the core phase
        # was performed. Initialize them conservatively here.
        self.curr_tasks: list[asyncio.Task] = []
        self.dashboard_shutdown_event: asyncio.Event | None = None
        self.event_bus = None
        self.pipeline_scheduler_mapping: dict = {}

    def _set_lifecycle_state(self, state: LifecycleState) -> None:
        """Set lifecycle state and maintain compatibility flags/events.

        This method keeps the simple compatibility surface used by tests that
        expect boolean flags and asyncio Events alongside the enum state.
        """
        self.lifecycle_state = state

        if state == LifecycleState.CREATED:
            self.core_initialized = False
            self.runtime_ready = False
            self.runtime_failed = False
            try:
                self.runtime_ready_event.clear()
            except Exception:
                pass
            try:
                self.runtime_failed_event.clear()
            except Exception:
                pass
        elif state == LifecycleState.CORE_READY:
            self.core_initialized = True
            self.runtime_ready = False
            self.runtime_failed = False
            try:
                self.runtime_ready_event.clear()
            except Exception:
                pass
            try:
                self.runtime_failed_event.clear()
            except Exception:
                pass
        elif state == LifecycleState.RUNTIME_READY:
            self.core_initialized = True
            self.runtime_ready = True
            self.runtime_failed = False
            try:
                self.runtime_ready_event.set()
            except Exception:
                pass
            try:
                self.runtime_failed_event.clear()
            except Exception:
                pass
        elif state == LifecycleState.RUNTIME_FAILED:
            self.core_initialized = True
            self.runtime_ready = False
            self.runtime_failed = True
            try:
                self.runtime_ready_event.clear()
            except Exception:
                pass
            try:
                self.runtime_failed_event.set()
            except Exception:
                pass

    async def initialize_core(self) -> None:
        """Compatibility method for older 'initialize_core' split-phase initialization.

        This performs the fast/core initialization phase only (sufficient to get
        the process started and to schedule the runtime bootstrap later). It is
        intentionally a subset of the full `initialize` method so tests and
        older callers that expect a split initialization can rely on it.
        """
        # Logging and configuration
        logger.info("AstrBot v" + VERSION)
        if os.environ.get("TESTING", ""):
            LogManager.configure_logger(
                logger,
                self.astrbot_config,
                override_level="DEBUG",
            )
            LogManager.configure_trace_logger(self.astrbot_config)
        else:
            LogManager.configure_logger(logger, self.astrbot_config)
            LogManager.configure_trace_logger(self.astrbot_config)

        # Core quick initializations
        await self.db.initialize()

        await html_renderer.initialize()

        # Initialize UMOP config router (fast)
        self.umop_config_router = UmopConfigRouter(sp=sp)
        await self.umop_config_router.initialize()

        # AstrBot config manager
        self.astrbot_config_mgr = AstrBotConfigManager(
            default_config=self.astrbot_config,
            ucr=self.umop_config_router,
            sp=sp,
        )
        self.temp_dir_cleaner = TempDirCleaner(
            max_size_getter=lambda: self.astrbot_config_mgr.default_conf.get(
                TempDirCleaner.CONFIG_KEY,
                TempDirCleaner.DEFAULT_MAX_SIZE,
            ),
        )

        # Apply migrations (keep same behavior)
        try:
            await migra(
                self.db,
                self.astrbot_config_mgr,
                self.umop_config_router,
                self.astrbot_config_mgr,
            )
        except Exception as e:
            logger.error(f"AstrBot migration failed: {e!s}")
            logger.error(traceback.format_exc())

        # Initialize event queue
        self.event_queue = Queue()

        # Initialize persona manager (fast)
        self.persona_mgr = PersonaManager(self.db, self.astrbot_config_mgr)
        await self.persona_mgr.initialize()

        # Instantiate provider manager (don't run .initialize() here)
        self.provider_manager = ProviderManager(
            self.astrbot_config_mgr,
            self.db,
            self.persona_mgr,
        )

        # Instantiate platform manager (don't run .initialize() here)
        self.platform_manager = PlatformManager(self.astrbot_config, self.event_queue)

        # Instantiate conversation manager and other lightweight managers
        self.conversation_manager = ConversationManager(self.db)
        self.platform_message_history_manager = PlatformMessageHistoryManager(self.db)

        # Instantiate KB manager but defer initialize()
        self.kb_manager = KnowledgeBaseManager(self.provider_manager)

        # Instantiate CronJob manager
        self.cron_manager = CronJobManager(self.db)

        # Dynamic subagents orchestrator (may be patched in tests)
        await self._init_or_reload_subagent_orchestrator()

        # Prepare star/plugin context (without reloading plugins)
        self.star_context = Context(
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
            self.subagent_orchestrator,
        )

        # Instantiate plugin manager (do not reload here)
        self.plugin_manager = PluginManager(self.star_context, self.astrbot_config)

        # Record that we finished the core phase
        self._set_lifecycle_state(LifecycleState.CORE_READY)

        # Prepare updater instance as in original initialize (constructor call)
        self.astrbot_updator = AstrBotUpdator()

        # Leave other runtime initializations (plugin reload, provider init, etc.)
        # to `bootstrap_runtime`.

    async def bootstrap_runtime(self) -> None:
        """Compatibility method for runtime bootstrap (deferred initialization).

        This completes the remaining initialization steps that were deferred by
        `initialize_core`, such as plugin reloads, provider initialization, KB init,
        pipeline scheduler loading and platform initialization.
        """
        # Guard: require core phase completed
        if getattr(self, "lifecycle_state", None) != LifecycleState.CORE_READY:
            raise RuntimeError("bootstrap_runtime must be called after initialize_core")

        # Reset runtime artifacts if re-attempting bootstrap after a failure
        self.event_bus = None
        self.pipeline_scheduler_mapping = {}

        try:
            # Reload plugins (this may register runtime routes/tasks)
            await self.plugin_manager.reload()

            # Initialize providers and KB (deferred heavy work)
            await self.provider_manager.initialize()
            await self.kb_manager.initialize()

            # Load pipeline schedulers (may be async and expensive)
            self.pipeline_scheduler_mapping = await self.load_pipeline_scheduler()

            # Create event bus now that pipeline schedulers exist
            self.event_bus = EventBus(
                self.event_queue,
                self.pipeline_scheduler_mapping,
                self.astrbot_config_mgr,
            )

            # Initialize platform adapters (deferred)
            await self.platform_manager.initialize()

            # Schedule auxiliary background tasks (metadata/task creation)
            asyncio.create_task(update_llm_metadata())

            # All runtime initialization complete
            self._set_lifecycle_state(LifecycleState.RUNTIME_READY)
            self.runtime_bootstrap_error = None
            return
        except Exception as e:
            # Mark runtime failed for compatibility and rethrow so callers can react
            self.runtime_bootstrap_error = e
            self._set_lifecycle_state(LifecycleState.RUNTIME_FAILED)

            # Attempt to run cleanup similar to original initialize() error paths
            try:
                # attempt graceful termination of partial runtime subsystems
                if getattr(self, "plugin_manager", None) and hasattr(
                    self.plugin_manager, "cleanup_loaded_plugins",
                ):
                    await self.plugin_manager.cleanup_loaded_plugins()
            except Exception:
                logger.error(
                    "Failed cleaning up plugins after runtime bootstrap failure",
                )

            try:
                if getattr(self, "provider_manager", None) and hasattr(
                    self.provider_manager, "terminate",
                ):
                    await self.provider_manager.terminate()
            except Exception:
                logger.error(
                    "Failed terminating provider_manager after runtime bootstrap failure",
                )

            try:
                if getattr(self, "platform_manager", None) and hasattr(
                    self.platform_manager, "terminate",
                ):
                    await self.platform_manager.terminate()
            except Exception:
                logger.error(
                    "Failed terminating platform_manager after runtime bootstrap failure",
                )

            try:
                if getattr(self, "kb_manager", None) and hasattr(
                    self.kb_manager, "terminate",
                ):
                    await self.kb_manager.terminate()
            except Exception:
                logger.error(
                    "Failed terminating kb_manager after runtime bootstrap failure",
                )

            raise

    async def _init_or_reload_subagent_orchestrator(self) -> None:
        """Create (if needed) and reload the subagent orchestrator from config.

        This keeps lifecycle wiring in one place while allowing the orchestrator
        to manage enable/disable and tool registration details.
        """
        try:
            if self.subagent_orchestrator is None:
                self.subagent_orchestrator = SubAgentOrchestrator(
                    self.provider_manager.llm_tools,
                    self.persona_mgr,
                )
            await self.subagent_orchestrator.reload_from_config(
                self.astrbot_config.get("subagent_orchestrator", {}),
            )
        except Exception as e:
            logger.error(f"Subagent orchestrator init failed: {e}", exc_info=True)

    async def initialize(self) -> None:
        """初始化 AstrBot 核心生命周期管理类.

        负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus、AstrBotUpdator等。
        """
        # 初始化日志代理
        logger.info("AstrBot v" + VERSION)
        if os.environ.get("TESTING", ""):
            LogManager.configure_logger(
                logger,
                self.astrbot_config,
                override_level="DEBUG",
            )
            LogManager.configure_trace_logger(self.astrbot_config)
        else:
            LogManager.configure_logger(logger, self.astrbot_config)
            LogManager.configure_trace_logger(self.astrbot_config)

        await self.db.initialize()

        await html_renderer.initialize()

        # 初始化 UMOP 配置路由器
        self.umop_config_router = UmopConfigRouter(sp=sp)
        await self.umop_config_router.initialize()

        # 初始化 AstrBot 配置管理器
        self.astrbot_config_mgr = AstrBotConfigManager(
            default_config=self.astrbot_config,
            ucr=self.umop_config_router,
            sp=sp,
        )
        self.temp_dir_cleaner = TempDirCleaner(
            max_size_getter=lambda: self.astrbot_config_mgr.default_conf.get(
                TempDirCleaner.CONFIG_KEY,
                TempDirCleaner.DEFAULT_MAX_SIZE,
            ),
        )

        # apply migration
        try:
            await migra(
                self.db,
                self.astrbot_config_mgr,
                self.umop_config_router,
                self.astrbot_config_mgr,
            )
        except Exception as e:
            logger.error(f"AstrBot migration failed: {e!s}")
            logger.error(traceback.format_exc())

        # 初始化事件队列
        self.event_queue = Queue()

        # 初始化人格管理器
        self.persona_mgr = PersonaManager(self.db, self.astrbot_config_mgr)
        await self.persona_mgr.initialize()

        # 初始化供应商管理器
        self.provider_manager = ProviderManager(
            self.astrbot_config_mgr,
            self.db,
            self.persona_mgr,
        )

        # 初始化平台管理器
        self.platform_manager = PlatformManager(self.astrbot_config, self.event_queue)

        # 初始化对话管理器
        self.conversation_manager = ConversationManager(self.db)

        # 初始化平台消息历史管理器
        self.platform_message_history_manager = PlatformMessageHistoryManager(self.db)

        # 初始化知识库管理器
        self.kb_manager = KnowledgeBaseManager(self.provider_manager)

        # 初始化 CronJob 管理器
        self.cron_manager = CronJobManager(self.db)

        # Dynamic subagents (handoff tools) from config.
        await self._init_or_reload_subagent_orchestrator()

        # 初始化提供给插件的上下文
        self.star_context = Context(
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
            self.subagent_orchestrator,
        )

        # 初始化插件管理器
        self.plugin_manager = PluginManager(self.star_context, self.astrbot_config)

        # 扫描、注册插件、实例化插件类
        await self.plugin_manager.reload()

        # 根据配置实例化各个 Provider
        await self.provider_manager.initialize()

        await self.kb_manager.initialize()

        # 初始化消息事件流水线调度器
        self.pipeline_scheduler_mapping = await self.load_pipeline_scheduler()

        # 初始化更新器
        self.astrbot_updator = AstrBotUpdator()

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
        await self.platform_manager.initialize()

        # 初始化关闭控制面板的事件
        self.dashboard_shutdown_event = asyncio.Event()

        asyncio.create_task(update_llm_metadata())

    def _load(self) -> None:
        """加载事件总线和任务并初始化."""
        # 创建一个异步任务来执行事件总线的 dispatch() 方法
        # dispatch是一个无限循环的协程, 从事件队列中获取事件并处理
        event_bus_task = asyncio.create_task(
            self.event_bus.dispatch(),
            name="event_bus",
        )
        cron_task = None
        if self.cron_manager:
            cron_task = asyncio.create_task(
                self.cron_manager.start(self.star_context),
                name="cron_manager",
            )
        temp_dir_cleaner_task = None
        if self.temp_dir_cleaner:
            temp_dir_cleaner_task = asyncio.create_task(
                self.temp_dir_cleaner.run(),
                name="temp_dir_cleaner",
            )

        # 把插件中注册的所有协程函数注册到事件总线中并执行
        extra_tasks = []
        for task in self.star_context._register_tasks:
            extra_tasks.append(asyncio.create_task(task, name=task.__name__))  # type: ignore

        tasks_ = [event_bus_task, *(extra_tasks or [])]
        if cron_task:
            tasks_.append(cron_task)
        if temp_dir_cleaner_task:
            tasks_.append(temp_dir_cleaner_task)
        for task in tasks_:
            self.curr_tasks.append(
                asyncio.create_task(self._task_wrapper(task), name=task.get_name()),
            )

        self.start_time = int(time.time())

    async def _task_wrapper(self, task: asyncio.Task) -> None:
        """异步任务包装器, 用于处理异步任务执行中出现的各种异常.

        Args:
            task (asyncio.Task): 要执行的异步任务

        """
        try:
            await task
        except asyncio.CancelledError:
            pass  # 任务被取消, 静默处理
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
        self._load()
        logger.info("AstrBot 启动完成。")

        # 执行启动完成事件钩子
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnAstrBotLoadedEvent,
        )
        for handler in handlers:
            try:
                logger.info(
                    f"hook(on_astrbot_loaded) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}",
                )
                await handler.handler()
            except BaseException:
                logger.error(traceback.format_exc())

        # 同时运行curr_tasks中的所有任务
        await asyncio.gather(*self.curr_tasks, return_exceptions=True)

    async def stop(self) -> None:
        """停止 AstrBot 核心生命周期管理类, 取消所有当前任务并终止各个管理器.

        This method is defensive: not all attributes may exist if only a partial
        initialization was performed (tests construct lifecycle objects and call
        stop() in different phases). Guard attribute accesses and log failures
        instead of raising AttributeError.
        """
        # Stop temp dir cleaner if present
        if getattr(self, "temp_dir_cleaner", None):
            try:
                await self.temp_dir_cleaner.stop()
            except Exception:
                logger.exception("Error stopping temp_dir_cleaner")

        # Cancel currently tracked tasks if any
        curr_tasks = getattr(self, "curr_tasks", None)
        if curr_tasks:
            for task in list(curr_tasks):
                try:
                    task.cancel()
                except Exception:
                    logger.exception("Error cancelling task")

        # Shutdown cron manager if present
        if getattr(self, "cron_manager", None):
            try:
                await self.cron_manager.shutdown()
            except Exception:
                logger.exception("Error shutting down cron_manager")

        # Terminate plugins if plugin_manager and context exist
        if getattr(self, "plugin_manager", None) and getattr(
            self.plugin_manager, "context", None,
        ):
            try:
                for plugin in self.plugin_manager.context.get_all_stars():
                    try:
                        await self.plugin_manager._terminate_plugin(plugin)
                    except Exception:
                        logger.exception("Failed to terminate plugin")
            except Exception:
                logger.exception(
                    "Error iterating plugin_manager.context.get_all_stars()",
                )

        # Terminate other managers if present
        if getattr(self, "provider_manager", None):
            try:
                await self.provider_manager.terminate()
            except Exception:
                logger.exception("Error terminating provider_manager")

        if getattr(self, "platform_manager", None):
            try:
                await self.platform_manager.terminate()
            except Exception:
                logger.exception("Error terminating platform_manager")

        if getattr(self, "kb_manager", None):
            try:
                await self.kb_manager.terminate()
            except Exception:
                logger.exception("Error terminating kb_manager")

        # Signal dashboard shutdown if event exists
        if getattr(self, "dashboard_shutdown_event", None):
            try:
                self.dashboard_shutdown_event.set()
            except Exception:
                logger.exception("Error setting dashboard_shutdown_event")

        # Await tasks to finish (if any)
        if curr_tasks:
            for task in list(curr_tasks):
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    name = task.get_name() if hasattr(task, "get_name") else str(task)
                    logger.error(f"任务 {name} 发生错误: {e}")

    async def restart(self) -> None:
        """重启 AstrBot 核心生命周期管理类, 终止各个管理器并重新加载平台实例"""
        await self.provider_manager.terminate()
        await self.platform_manager.terminate()
        await self.kb_manager.terminate()
        self.dashboard_shutdown_event.set()
        threading.Thread(
            target=self.astrbot_updator._reboot,
            name="restart",
            daemon=True,
        ).start()

    def load_platform(self) -> list[asyncio.Task]:
        """加载平台实例并返回所有平台实例的异步任务列表"""
        tasks = []
        platform_insts = self.platform_manager.get_insts()
        for platform_inst in platform_insts:
            tasks.append(
                asyncio.create_task(
                    platform_inst.run(),
                    name=f"{platform_inst.meta().id}({platform_inst.meta().name})",
                ),
            )
        return tasks

    async def load_pipeline_scheduler(self) -> dict[str, PipelineScheduler]:
        """加载消息事件流水线调度器.

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射

        """
        mapping = {}
        for conf_id, ab_config in self.astrbot_config_mgr.confs.items():
            scheduler = PipelineScheduler(
                PipelineContext(ab_config, self.plugin_manager, conf_id),
            )
            await scheduler.initialize()
            mapping[conf_id] = scheduler
        return mapping

    async def reload_pipeline_scheduler(self, conf_id: str) -> None:
        """重新加载消息事件流水线调度器.

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射

        """
        ab_config = self.astrbot_config_mgr.confs.get(conf_id)
        if not ab_config:
            raise ValueError(f"配置文件 {conf_id} 不存在")
        scheduler = PipelineScheduler(
            PipelineContext(ab_config, self.plugin_manager, conf_id),
        )
        await scheduler.initialize()
        self.pipeline_scheduler_mapping[conf_id] = scheduler
