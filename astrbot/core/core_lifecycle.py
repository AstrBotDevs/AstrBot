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
from collections.abc import Awaitable
from enum import Enum
from inspect import iscoroutine
from pathlib import Path

from astrbot.core import LogBroker, LogManager, logger, sp
from astrbot.core.agent.config_store import AgentConfigStore
from astrbot.core.agent.runtime import AgentRuntime
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
from astrbot.core.astr_agent_runtime.subagents.store import SubAgentStore
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.config.default import VERSION
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.cron import CronJobManager
from astrbot.core.db import BaseDatabase
from astrbot.core.knowledge_base.kb_mgr import KnowledgeBaseManager
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.pipeline.scheduler import PipelineContext, PipelineScheduler
from astrbot.core.platform.button_interaction import (
    configure_button_callback_registry,
)
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.process_restart import restart_process
from astrbot.core.provider.manager import ProviderManager
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import EventType, star_handlers_registry, star_map
from astrbot.core.star.star_manager import PluginManager
from astrbot.core.umop_config_router import UmopConfigRouter
from astrbot.core.updater import AstrBotUpdater
from astrbot.core.utils.event_loop_diagnostics import (
    create_event_loop_diagnostic_tasks,
)
from astrbot.core.utils.llm_metadata import update_llm_metadata
from astrbot.core.utils.migra_helper import migra
from astrbot.core.utils.temp_dir_cleaner import TempDirCleaner

from . import astrbot_config, html_renderer
from .event_bus import EventBus


class LifecycleState(Enum):
    CREATED = "created"
    CORE_READY = "core_ready"
    RUNTIME_READY = "runtime_ready"
    RUNTIME_FAILED = "runtime_failed"


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

        self.subagents: SubAgentService | None = None
        self.agent_configs = AgentConfigStore(db)
        self.agent_runtimes: dict[str, AgentRuntime] = {}
        self.cron_manager: CronJobManager | None = None
        self.temp_dir_cleaner: TempDirCleaner | None = None
        self._default_chat_provider_warning_emitted = False

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
            # Clear system proxy variables to avoid interfering with localhost requests.
            has_system_proxy = "https_proxy" in os.environ or "http_proxy" in os.environ
            if has_system_proxy:
                logger.warning(
                    "System http_proxy/https_proxy environment variables were detected, "
                    "but AstrBot has no proxy configured. Clearing the proxy variables "
                    "and setting no_proxy to localhost,127.0.0.1,::1 so local API "
                    "requests bypass the proxy. Configure http_proxy in AstrBot if a "
                    "proxy is required."
                )
            if "https_proxy" in os.environ:
                del os.environ["https_proxy"]
            if "http_proxy" in os.environ:
                del os.environ["http_proxy"]
            if "no_proxy" in os.environ:
                del os.environ["no_proxy"]
            # Always bypass proxies for loopback addresses used by local APIs.
            os.environ["no_proxy"] = "localhost,127.0.0.1,::1"
            logger.debug("HTTP proxy cleared, no_proxy set to localhost")

        # Lifecycle compatibility fields
        # Expose lifecycle state and event flags expected by tests and older consumers.
        self.lifecycle_state = LifecycleState.CREATED
        self.core_initialized = False
        self.runtime_ready = False
        self.runtime_failed = False
        self.runtime_request_ready = False
        self.runtime_ready_event = asyncio.Event()
        self.runtime_failed_event = asyncio.Event()
        self.runtime_bootstrap_error = None
        self.start_time = 0
        self.runtime_bootstrap_task: asyncio.Task | None = None
        self.metadata_update_task: asyncio.Task | None = None

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
        self.runtime_request_ready = state == LifecycleState.RUNTIME_READY

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
        """初始化 AstrBot 核心生命周期管理类.

        负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus、AstrBotUpdater等。
        """
        # 初始化日志代理
        logger.info("AstrBot v" + VERSION)
        if os.environ.get("TESTING", ""):
            LogManager.configure_logger(
                logger, self.astrbot_config, override_level="DEBUG"
            )
        else:
            LogManager.configure_logger(
                logger,
                self.astrbot_config,
                override_level=os.getenv("ASTRBOT_LOG_LEVEL"),
            )

        LogManager.configure_trace_logger(self.astrbot_config)

        await self.db.initialize()
        button_callback_db_path = getattr(self.db, "db_path", None)
        if isinstance(button_callback_db_path, (str, Path)):
            configure_button_callback_registry(button_callback_db_path)
        if sp.db_helper is self.db:
            await sp.initialize()

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
        await self.astrbot_config_mgr.initialize()
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
        self.conversation_manager = ConversationManager(
            self.db, self.astrbot_config_mgr
        )

        # 初始化平台消息历史管理器
        self.platform_message_history_manager = PlatformMessageHistoryManager(self.db)

        # 初始化知识库管理器
        self.kb_manager = KnowledgeBaseManager(self.provider_manager)

        # 初始化 CronJob 管理器
        self.cron_manager = CronJobManager(self.db)

        # 初始化提供给插件的上下文
        self.subagents = SubAgentService(SubAgentStore(self.db), self.agent_runtimes)
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
            agent_runtimes=self.agent_runtimes,
        )
        runtime = AstrAgentRuntime(
            self.star_context,
            agent_configs=self.agent_configs,
            subagents=self.subagents,
        )
        self.star_context.agent.register_runtime("astrbot", runtime)
        await runtime.initialize()
        self.star_context.html_renderer = html_renderer

        # 初始化插件管理器
        self.plugin_manager = PluginManager(self.star_context, self.astrbot_config)

        self.astrbot_updater = AstrBotUpdater()
        self.dashboard_shutdown_event = asyncio.Event()
        self._set_lifecycle_state(LifecycleState.CORE_READY)

    async def bootstrap_runtime(self) -> None:
        """Initialize providers, plugins and platforms after the core is ready."""
        if self.lifecycle_state not in (
            LifecycleState.CORE_READY,
            LifecycleState.RUNTIME_FAILED,
        ):
            raise RuntimeError("bootstrap_runtime must be called after initialize_core")
        self._set_lifecycle_state(LifecycleState.CORE_READY)
        self.runtime_bootstrap_error = None
        self.event_bus = None
        self.pipeline_scheduler_mapping = {}
        try:
            await self.plugin_manager.reload()

            # 根据配置实例化各个 Provider
            self._default_chat_provider_warning_emitted = False
            await self.provider_manager.initialize()
            self._warn_about_unset_default_chat_provider()

            await self.kb_manager.initialize()
            from astrbot.core.db.migration.migra_session_overrides import (
                migrate_session_overrides,
            )

            await migrate_session_overrides(self.astrbot_config_mgr, self.db)

            # 初始化消息事件流水线调度器
            self.pipeline_scheduler_mapping = await self.load_pipeline_scheduler()

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

            if self.subagents is None:
                raise RuntimeError("The subagent service has not been initialized.")
            await self.subagents.start(self.star_context)

            self.metadata_update_task = asyncio.create_task(
                update_llm_metadata(), name="metadata_update"
            )

            self._set_lifecycle_state(LifecycleState.RUNTIME_READY)
            self.runtime_bootstrap_error = None
        except asyncio.CancelledError:
            await self._cleanup_partial_runtime_bootstrap()
            self.runtime_bootstrap_error = None
            self._set_lifecycle_state(LifecycleState.CORE_READY)
            raise
        except Exception as error:
            self.runtime_bootstrap_error = error
            self._set_lifecycle_state(LifecycleState.RUNTIME_FAILED)
            await self._cleanup_partial_runtime_bootstrap()
            raise

    async def _cleanup_partial_runtime_bootstrap(self) -> None:
        """Release partially initialized runtime resources before shutdown or retry."""
        self.start_time = 0
        self.event_bus = None
        self.pipeline_scheduler_mapping = {}
        try:
            await self.plugin_manager.cleanup_loaded_plugins()
        except Exception:
            logger.exception(
                "Failed cleaning up plugins after runtime bootstrap failure"
            )
        self.star_context.reset_runtime_registrations()
        try:
            await self.star_context.agent.close()
        except Exception:
            logger.exception("Failed closing agent runtime after bootstrap failure")
        if self.subagents is not None:
            try:
                await self.subagents.close()
            except Exception:
                logger.exception("Failed closing subagents after bootstrap failure")
        for manager in (
            self.provider_manager,
            self.platform_manager,
            self.kb_manager,
        ):
            try:
                await manager.terminate()
            except Exception:
                logger.exception(
                    "Failed terminating %s after runtime bootstrap failure",
                    type(manager).__name__,
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
        fallback = pm.curr_provider_inst or providers[0]
        fallback_id = fallback.provider_config.get("id") or "unknown"

        if not default_id:
            if len(providers) <= 1:
                return
            self._default_chat_provider_warning_emitted = True
            logger.warning(
                "Detected %d enabled chat providers but `agent.config.model.provider_id` is empty. "
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
        """Initialize the core and await its tracked runtime bootstrap."""
        await self.initialize_core()
        self.runtime_bootstrap_task = asyncio.create_task(
            self.bootstrap_runtime(), name="runtime_bootstrap"
        )
        await self.runtime_bootstrap_task

    def _load(self) -> None:
        """Start dispatch and owned tasks after the runtime is ready.

        Raises:
            RuntimeError: If the runtime has not completed initialization.
        """
        if self.lifecycle_state != LifecycleState.RUNTIME_READY:
            raise RuntimeError("Lifecycle must be RUNTIME_READY before loading tasks")
        # 创建一个异步任务来执行事件总线的 dispatch() 方法
        # dispatch是一个无限循环的协程, 从事件队列中获取事件并处理
        event_bus_task = None
        if self.event_bus:
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
        diagnostic_tasks = create_event_loop_diagnostic_tasks()

        # 把插件中注册的所有协程函数注册到事件总线中并执行
        extra_tasks = []
        for task in self.star_context._register_tasks:
            coroutine = task if iscoroutine(task) else self._await_registered_task(task)
            extra_tasks.append(
                asyncio.create_task(
                    coroutine,
                    name=getattr(task, "__name__", type(task).__name__),
                )
            )

        tasks_ = []
        if event_bus_task:
            tasks_.append(event_bus_task)
        tasks_.extend(diagnostic_tasks)
        tasks_.extend(extra_tasks or [])
        if cron_task:
            tasks_.append(cron_task)
        if temp_dir_cleaner_task:
            tasks_.append(temp_dir_cleaner_task)
        for task in tasks_:
            self.curr_tasks.append(
                asyncio.create_task(self._task_wrapper(task), name=task.get_name()),
            )

        self.start_time = int(time.time())

    @staticmethod
    async def _await_registered_task(task: Awaitable[None]) -> None:
        """Adapt registered awaitables to the coroutine required by create_task."""
        await task

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
        """Start dispatch only after the runtime bootstrap has finished.

        Raises:
            RuntimeError: If runtime initialization has not been scheduled.
        """
        bootstrap_task = self.runtime_bootstrap_task
        if bootstrap_task is not None:
            try:
                await bootstrap_task
            except asyncio.CancelledError:
                current = asyncio.current_task()
                if current is not None and current.cancelling():
                    raise
                return
            except Exception as error:
                self.runtime_bootstrap_error = error
                self._set_lifecycle_state(LifecycleState.RUNTIME_FAILED)
        if self.runtime_failed or self.runtime_failed_event.is_set():
            logger.error("Runtime bootstrap failed: %s", self.runtime_bootstrap_error)
            return
        if not self.runtime_ready:
            raise RuntimeError("A runtime bootstrap task must finish before start")

        self._load()
        logger.info("AstrBot started.")
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnAstrBotLoadedEvent,
        )
        for handler in handlers:
            try:
                logger.info(
                    "hook(on_astrbot_loaded) -> %s - %s",
                    star_map[handler.handler_module_path].name,
                    handler.handler_name,
                )
                await handler.handler()
            except Exception:
                logger.error(traceback.format_exc())
        await asyncio.gather(*self.curr_tasks, return_exceptions=True)

    async def stop(self) -> None:
        """停止 AstrBot 核心生命周期管理类, 取消所有当前任务并终止各个管理器.

        This method is defensive: not all attributes may exist if only a partial
        initialization was performed (tests construct lifecycle objects and call
        stop() in different phases). Guard attribute accesses and log failures
        instead of raising AttributeError.
        """
        self.runtime_request_ready = False
        current_task = asyncio.current_task()
        owned_tasks = [task for task in self.curr_tasks if task is not current_task]
        for task in (self.runtime_bootstrap_task, self.metadata_update_task):
            if (
                task is not None
                and task is not current_task
                and task not in owned_tasks
            ):
                owned_tasks.append(task)
        for task in owned_tasks:
            if not task.done() and not task.cancelling():
                task.cancel()
        if owned_tasks:
            await asyncio.gather(*owned_tasks, return_exceptions=True)
        self.runtime_bootstrap_task = None
        self.metadata_update_task = None
        self.runtime_bootstrap_error = None
        self.curr_tasks = []
        self.event_bus = None
        self.pipeline_scheduler_mapping = {}
        self.start_time = 0
        self._set_lifecycle_state(LifecycleState.CREATED)

        # Stop temp dir cleaner if present
        if self.temp_dir_cleaner is not None:
            try:
                await self.temp_dir_cleaner.stop()
            except Exception:
                logger.exception("Error stopping temp_dir_cleaner")

        # Shutdown cron manager if present
        if self.cron_manager is not None:
            try:
                await self.cron_manager.shutdown()
            except Exception:
                logger.exception("Error shutting down cron_manager")

        context = getattr(self, "star_context", None)
        if isinstance(context, Context):
            try:
                await context.agent.close()
            except Exception:
                logger.exception("Error closing agent runtime")
        if self.subagents is not None:
            try:
                await self.subagents.close()
            except Exception:
                logger.exception("Error closing subagents")

        # Terminate plugins if plugin_manager and context exist
        if getattr(self, "plugin_manager", None) and getattr(
            self.plugin_manager,
            "context",
            None,
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

        if sp.db_helper is self.db:
            await sp.close()

        # Signal dashboard shutdown if event exists
        if self.dashboard_shutdown_event is not None:
            try:
                self.dashboard_shutdown_event.set()
            except Exception:
                logger.exception("Error setting dashboard_shutdown_event")

        # 释放数据库引擎连接池
        from astrbot.core.utils.trace_store import close_trace_store

        await asyncio.to_thread(close_trace_store)
        try:
            await self.db.engine.dispose()
        except Exception as e:
            logger.warning(f"释放数据库引擎失败: {e}")

    async def restart(self) -> None:
        """Drain the running lifecycle before starting a replacement process."""
        await self.stop()
        threading.Thread(
            target=restart_process,
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
                PipelineContext(
                    ab_config,
                    self.plugin_manager,
                    conf_id,
                    self.db,
                    agent_runtimes=self.agent_runtimes,
                ),
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
            PipelineContext(
                ab_config,
                self.plugin_manager,
                conf_id,
                self.db,
                agent_runtimes=self.agent_runtimes,
            ),
        )
        await scheduler.initialize()
        self.pipeline_scheduler_mapping[conf_id] = scheduler
