"""Astrbot 核心生命周期管理类, 负责管理 AstrBot 的启动､停止､重启等操作.

该类负责初始化各个组件, 包括 ProviderManager､PlatformManager､ConversationManager､PluginManager､PipelineScheduler､EventBus等｡
该类还负责加载和执行插件, 以及处理事件总线的分发｡

工作流程:
1. 初始化所有组件
2. 启动事件总线和任务, 所有任务都在这里运行
3. 执行启动完成事件钩子
"""

import asyncio
import inspect
import os
import threading
import time
import traceback
from asyncio import Queue
from enum import Enum
from typing import Any

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


class LifecycleState(str, Enum):
    """Minimal lifecycle contract for split initialization."""

    CREATED = "created"
    CORE_READY = "core_ready"
    RUNTIME_FAILED = "runtime_failed"
    RUNTIME_READY = "runtime_ready"


class AstrBotCoreLifecycle:
    """AstrBot 核心生命周期管理类, 负责管理 AstrBot 的启动､停止､重启等操作.

    该类负责初始化各个组件, 包括 ProviderManager､PlatformManager､ConversationManager､PluginManager､PipelineScheduler､
    EventBus 等｡
    该类还负责加载和执行插件, 以及处理事件总线的分发｡
    """

    def __init__(self, log_broker: LogBroker, db: BaseDatabase) -> None:
        self.log_broker = log_broker  # 初始化日志代理
        self.astrbot_config = astrbot_config  # 初始化配置
        self.db = db  # 初始化数据库

        self.umop_config_router: UmopConfigRouter | None = None
        self.astrbot_config_mgr: AstrBotConfigManager | None = None
        self.event_queue: Queue | None = None
        self.persona_mgr: PersonaManager | None = None
        self.provider_manager: ProviderManager | None = None
        self.platform_manager: PlatformManager | None = None
        self.conversation_manager: ConversationManager | None = None
        self.platform_message_history_manager: PlatformMessageHistoryManager | None = (
            None
        )
        self.kb_manager: KnowledgeBaseManager | None = None
        self.subagent_orchestrator: SubAgentOrchestrator | None = None
        self.cron_manager: CronJobManager | None = None
        self.temp_dir_cleaner: TempDirCleaner | None = None
        self.star_context: Context | None = None
        self.plugin_manager: PluginManager | None = None
        self.pipeline_scheduler_mapping: dict[str, PipelineScheduler] = {}
        self.astrbot_updator: AstrBotUpdator | None = None
        self.event_bus: EventBus | None = None
        self.dashboard_shutdown_event: asyncio.Event | None = None
        self.curr_tasks: list[asyncio.Task] = []
        self.metadata_update_task: asyncio.Task[None] | None = None
        self.start_time = 0
        self.runtime_bootstrap_task: asyncio.Task[None] | None = None
        self.runtime_bootstrap_error: BaseException | None = None
        self.runtime_ready_event = asyncio.Event()
        self.runtime_failed_event = asyncio.Event()
        self.runtime_request_ready = False
        self._runtime_wait_interrupted = False
        self._set_lifecycle_state(LifecycleState.CREATED)

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

    @property
    def core_initialized(self) -> bool:
        return self.lifecycle_state is not LifecycleState.CREATED

    @property
    def runtime_ready(self) -> bool:
        return self.lifecycle_state is LifecycleState.RUNTIME_READY

    @property
    def runtime_failed(self) -> bool:
        return self.lifecycle_state is LifecycleState.RUNTIME_FAILED

    async def _init_or_reload_subagent_orchestrator(self) -> None:
        """Create (if needed) and reload the subagent orchestrator from config.

        This keeps lifecycle wiring in one place while allowing the orchestrator
        to manage enable/disable and tool registration details.
        """
        try:
            if self.provider_manager is None or self.persona_mgr is None:
                raise RuntimeError("core dependencies are not initialized")
            provider_manager = self.provider_manager
            persona_mgr = self.persona_mgr
            if self.subagent_orchestrator is None:
                self.subagent_orchestrator = SubAgentOrchestrator(
                    provider_manager.llm_tools,
                    persona_mgr,
                )
            await self.subagent_orchestrator.reload_from_config(
                self.astrbot_config.get("subagent_orchestrator", {}),
            )
        except Exception as e:
            logger.error(f"Subagent orchestrator init failed: {e}", exc_info=True)

    def _set_lifecycle_state(self, state: LifecycleState) -> None:
        """Update lifecycle state and keep readiness events in sync."""
        self.lifecycle_state = state
        if state is LifecycleState.RUNTIME_READY:
            self.runtime_ready_event.set()
            self.runtime_failed_event.clear()
        elif state is LifecycleState.RUNTIME_FAILED:
            self.runtime_ready_event.clear()
            self.runtime_failed_event.set()
        else:
            self.runtime_ready_event.clear()
            self.runtime_failed_event.clear()

    def _clear_runtime_failure_for_retry(self) -> None:
        if self.lifecycle_state is LifecycleState.RUNTIME_FAILED:
            self._set_lifecycle_state(LifecycleState.CORE_READY)

    async def _cleanup_partial_runtime_bootstrap(self) -> None:
        if self.star_context is not None and hasattr(
            self.star_context,
            "reset_runtime_registrations",
        ):
            self.star_context.reset_runtime_registrations()
        if self.plugin_manager is not None and hasattr(
            self.plugin_manager,
            "cleanup_loaded_plugins",
        ):
            try:
                cleanup_loaded_plugins = getattr(
                    self.plugin_manager,
                    "cleanup_loaded_plugins",
                )
                result = cleanup_loaded_plugins()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning(
                    f"Failed to clean up loaded plugin state: {exc}",
                    exc_info=True,
                )
        for manager in (self.platform_manager, self.kb_manager, self.provider_manager):
            if manager is None:
                continue
            try:
                terminate = getattr(manager, "terminate", None)
                if not callable(terminate):
                    continue
                result = terminate()
                if inspect.isawaitable(result):
                    await result
            except Exception as exc:
                logger.warning(
                    f"Failed to clean up partial runtime bootstrap state: {exc}",
                    exc_info=True,
                )
        self._clear_runtime_artifacts()

    def _reset_runtime_bootstrap_state(self) -> None:
        self.runtime_bootstrap_task = None
        self.runtime_bootstrap_error = None

    def _interrupt_runtime_bootstrap_waiters(self) -> None:
        self._runtime_wait_interrupted = True
        self.runtime_bootstrap_error = None
        self.runtime_failed_event.set()

    async def _consume_completed_bootstrap_task(self) -> None:
        task = self.runtime_bootstrap_task
        if task is None or not task.done():
            return
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    async def _wait_for_runtime_ready(self) -> bool:
        if self.runtime_ready:
            return True
        if self._runtime_wait_interrupted:
            return False
        if self.runtime_failed or self.runtime_bootstrap_error is not None:
            await self._consume_completed_bootstrap_task()
            return False

        runtime_bootstrap_task = self.runtime_bootstrap_task
        if runtime_bootstrap_task is None:
            raise RuntimeError(
                "runtime bootstrap task was not scheduled before start",
            )

        try:
            await runtime_bootstrap_task
        except asyncio.CancelledError:
            return False
        except BaseException as exc:
            if self.runtime_bootstrap_error is None:
                self.runtime_bootstrap_error = exc
            if not self.runtime_failed:
                self._set_lifecycle_state(LifecycleState.RUNTIME_FAILED)
            return False

        if self._runtime_wait_interrupted:
            return False

        return self.runtime_ready

    def _collect_runtime_bootstrap_task(self) -> list[asyncio.Task]:
        task = self.runtime_bootstrap_task
        self.runtime_bootstrap_task = None
        if task is None:
            return []
        if not task.done():
            task.cancel()
        return [task]

    def _collect_metadata_update_task(self) -> list[asyncio.Task]:
        task = self.metadata_update_task
        self.metadata_update_task = None
        if task is None:
            return []
        if not task.done():
            task.cancel()
        return [task]

    async def _await_tasks(self, tasks: list[asyncio.Task]) -> None:
        for task in tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"任务 {task.get_name()} 发生错误: {e}")

    def _require_runtime_bootstrap_components(
        self,
    ) -> tuple[PluginManager, ProviderManager, KnowledgeBaseManager, PlatformManager]:
        if (
            self.plugin_manager is None
            or self.provider_manager is None
            or self.kb_manager is None
            or self.platform_manager is None
        ):
            raise RuntimeError("initialize_core must complete before runtime bootstrap")
        return (
            self.plugin_manager,
            self.provider_manager,
            self.kb_manager,
            self.platform_manager,
        )

    def _require_runtime_started_components(self) -> tuple[EventBus, Context]:
        if self.lifecycle_state is not LifecycleState.RUNTIME_READY:
            raise RuntimeError("LifecycleState.RUNTIME_READY required before start")
        if self.event_bus is None or self.star_context is None:
            raise RuntimeError("runtime bootstrap must complete before start")
        return self.event_bus, self.star_context

    def _cancel_current_tasks(self) -> list[asyncio.Task]:
        tasks_to_wait: list[asyncio.Task] = []
        for task in self.curr_tasks:
            task.cancel()
            if isinstance(task, asyncio.Task):
                tasks_to_wait.append(task)
        self.curr_tasks = []
        return tasks_to_wait

    def _clear_runtime_artifacts(self) -> None:
        self.metadata_update_task = None
        self.runtime_request_ready = False
        self.event_bus = None
        self.pipeline_scheduler_mapping = {}
        self.curr_tasks = []
        self.start_time = 0

    def _require_core_ready(self) -> None:
        if not self.core_initialized:
            raise RuntimeError("initialize_core must complete before this operation")

    def _require_platform_manager(self) -> PlatformManager:
        if self.platform_manager is None:
            raise RuntimeError("platform manager is not initialized")
        return self.platform_manager

    async def initialize_core(self) -> None:
        """Initialize the fast core phase without runtime bootstrap."""
        if self.core_initialized:
            return

        self._runtime_wait_interrupted = False
        self._reset_runtime_bootstrap_state()

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
        if self.astrbot_config_mgr is None:
            raise RuntimeError("config manager initialization failed")
        astrbot_config_mgr = self.astrbot_config_mgr
        self.temp_dir_cleaner = TempDirCleaner(
            max_size_getter=lambda: astrbot_config_mgr.default_conf.get(
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

        # 为提前启动 Dashboard 准备核心依赖
        self.astrbot_updator = AstrBotUpdator()
        self.dashboard_shutdown_event = asyncio.Event()

        self._set_lifecycle_state(LifecycleState.CORE_READY)

    async def bootstrap_runtime(self) -> None:
        """Complete deferred runtime bootstrap after core initialization."""
        if not self.core_initialized:
            raise RuntimeError(
                "initialize_core must be called before bootstrap_runtime",
            )
        if self.runtime_ready:
            return

        self._clear_runtime_failure_for_retry()
        self.runtime_bootstrap_error = None
        self.runtime_ready_event.clear()
        self.runtime_failed_event.clear()

        try:
            plugin_manager, provider_manager, kb_manager, platform_manager = (
                self._require_runtime_bootstrap_components()
            )

            # 扫描、注册插件、实例化插件类
            await plugin_manager.reload()

            # 根据配置实例化各个 Provider
            await provider_manager.initialize()

            await kb_manager.initialize()

            # 初始化消息事件流水线调度器
            self.pipeline_scheduler_mapping = await self.load_pipeline_scheduler()

            if self.event_queue is None or self.astrbot_config_mgr is None:
                raise RuntimeError(
                    "initialize_core must complete before runtime bootstrap",
                )

            # 初始化事件总线
            self.event_bus = EventBus(
                self.event_queue,
                self.pipeline_scheduler_mapping,
                self.astrbot_config_mgr,
            )

            # 记录启动时间
            self.start_time = int(time.time())

            # 初始化当前任务列表
            self.curr_tasks = []

            # 根据配置实例化各个平台适配器
            await platform_manager.initialize()

            self.metadata_update_task = asyncio.create_task(update_llm_metadata())

            self._set_lifecycle_state(LifecycleState.RUNTIME_READY)
        except asyncio.CancelledError:
            await self._cleanup_partial_runtime_bootstrap()
            self._set_lifecycle_state(LifecycleState.CORE_READY)
            self.runtime_bootstrap_error = None
            raise
        except BaseException as exc:
            await self._cleanup_partial_runtime_bootstrap()
            self._set_lifecycle_state(LifecycleState.RUNTIME_FAILED)
            self.runtime_bootstrap_error = exc
            raise

    async def initialize(self) -> None:
        """初始化 AstrBot 核心生命周期管理类.

        负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus、AstrBotUpdator等。
        """
        await self.initialize_core()
        await self.bootstrap_runtime()
        self.runtime_request_ready = True

    def _load(self) -> None:
        """加载事件总线和任务并初始化."""
        event_bus, star_context = self._require_runtime_started_components()

        # 创建一个异步任务来执行事件总线的 dispatch() 方法
        # dispatch是一个无限循环的协程, 从事件队列中获取事件并处理
        event_bus_task = asyncio.create_task(
            event_bus.dispatch(),
            name="event_bus",
        )
        cron_task = None
        if self.cron_manager:
            cron_task = asyncio.create_task(
                self.cron_manager.start(star_context),
                name="cron_manager",
            )
        temp_dir_cleaner_task = None
        if self.temp_dir_cleaner:
            temp_dir_cleaner_task = asyncio.create_task(
                self.temp_dir_cleaner.run(),
                name="temp_dir_cleaner",
            )

        # 把插件中注册的所有协程函数注册到事件总线中并执行
        extra_tasks: list[asyncio.Task[Any]] = []
        if star_context._register_tasks is not None:
            for task in star_context._register_tasks:
                task_name = getattr(task, "__name__", task.__class__.__name__)
                extra_tasks.append(asyncio.create_task(task, name=task_name))

        tasks_ = [event_bus_task, *(extra_tasks if extra_tasks else [])]
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
        if not await self._wait_for_runtime_ready():
            if self._runtime_wait_interrupted:
                return
            error = self.runtime_bootstrap_error
            if error is None:
                logger.error("AstrBot runtime bootstrap failed before start completed.")
            else:
                logger.error(
                    f"AstrBot runtime bootstrap failed before start completed: {error}",
                )
            return

        self._load()
        logger.info("AstrBot 启动完成｡")

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

        self.runtime_request_ready = True

        # 同时运行curr_tasks中的所有任务
        await asyncio.gather(*self.curr_tasks, return_exceptions=True)

    async def _shutdown_runtime(self) -> None:
        self.runtime_request_ready = False
        self._interrupt_runtime_bootstrap_waiters()

        tasks_to_wait = self._cancel_current_tasks()
        await self._await_tasks(self._collect_metadata_update_task())
        runtime_bootstrap_tasks = self._collect_runtime_bootstrap_task()
        await self._await_tasks(runtime_bootstrap_tasks)
        tasks_to_wait.extend(runtime_bootstrap_tasks)

        if self.cron_manager:
            await self.cron_manager.shutdown()

        if self.plugin_manager and self.plugin_manager.context:
            for plugin in self.plugin_manager.context.get_all_stars():
                try:
                    await self.plugin_manager._terminate_plugin(plugin)
                except Exception as e:
                    logger.warning(traceback.format_exc())
                    logger.warning(
                        f"插件 {plugin.name} 未被正常终止 {e!s}, 可能会导致资源泄露等问题。",
                    )

        if self.provider_manager:
            await self.provider_manager.terminate()
        if self.platform_manager:
            await self.platform_manager.terminate()
        if self.kb_manager:
            await self.kb_manager.terminate()
        if self.dashboard_shutdown_event:
            self.dashboard_shutdown_event.set()

        self._clear_runtime_artifacts()
        self._set_lifecycle_state(LifecycleState.CREATED)
        self._reset_runtime_bootstrap_state()
        await self._await_tasks(tasks_to_wait)

    async def stop(self) -> None:
        """停止 AstrBot 核心生命周期管理类, 取消所有当前任务并终止各个管理器."""
        if self.temp_dir_cleaner:
            await self.temp_dir_cleaner.stop()
        await self._shutdown_runtime()

    async def restart(self) -> None:
        """重启 AstrBot 核心生命周期管理类, 终止各个管理器并重新加载平台实例"""
        await self._shutdown_runtime()
        if self.astrbot_updator is None:
            return
        threading.Thread(
            target=self.astrbot_updator._reboot,
            name="restart",
            daemon=True,
        ).start()

    def load_platform(self) -> list[asyncio.Task]:
        """加载平台实例并返回所有平台实例的异步任务列表"""
        tasks = []
        platform_insts = self._require_platform_manager().get_insts()
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
        self._require_core_ready()
        assert self.astrbot_config_mgr is not None
        assert self.plugin_manager is not None
        astrbot_config_mgr = self.astrbot_config_mgr
        plugin_manager = self.plugin_manager
        for conf_id, ab_config in astrbot_config_mgr.confs.items():
            scheduler = PipelineScheduler(
                PipelineContext(ab_config, plugin_manager, conf_id),
            )
            await scheduler.initialize()
            mapping[conf_id] = scheduler
        return mapping

    async def reload_pipeline_scheduler(self, conf_id: str) -> None:
        """重新加载消息事件流水线调度器.

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射

        """
        self._require_core_ready()
        assert self.astrbot_config_mgr is not None
        astrbot_config_mgr = self.astrbot_config_mgr
        ab_config = astrbot_config_mgr.confs.get(conf_id)
        if not ab_config:
            raise ValueError(f"配置文件 {conf_id} 不存在")
        assert self.plugin_manager is not None
        plugin_manager = self.plugin_manager
        scheduler = PipelineScheduler(
            PipelineContext(ab_config, plugin_manager, conf_id),
        )
        await scheduler.initialize()
        self.pipeline_scheduler_mapping[conf_id] = scheduler
