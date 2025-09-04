"""
Astrbot 核心生命周期管理类, 负责管理 AstrBot 的启动、停止、重启等操作。
该类负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus等。
该类还负责加载和执行插件, 以及处理事件总线的分发。

工作流程:
1. 初始化所有组件
2. 启动事件总线和任务, 所有任务都在这里运行
3. 执行启动完成事件钩子
"""

import traceback
import asyncio
import time
import threading
import os
from .event_bus import EventBus
from . import astrbot_config, html_renderer
from asyncio import Queue
from typing import List
from astrbot.core.pipeline.scheduler import PipelineScheduler, PipelineContext
from astrbot.core.star import PluginManager
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.star.context import Context
from astrbot.core.persona_mgr import PersonaManager
from astrbot.core.provider.manager import ProviderManager
from astrbot.core import LogBroker
from astrbot.core.db import BaseDatabase
from astrbot.core.updator import AstrBotUpdator
from astrbot.core import logger, sp
from astrbot.core.config.default import VERSION
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.platform_message_history_mgr import PlatformMessageHistoryManager
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.core.star.star_handler import star_map


class AstrBotCoreLifecycle:
    """
    AstrBot 核心生命周期管理类, 负责管理 AstrBot 的启动、停止、重启等操作。
    该类负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、
    EventBus 等。
    该类还负责加载和执行插件, 以及处理事件总线的分发。
    """

    def __init__(self, log_broker: LogBroker, db: BaseDatabase):
        self.log_broker = log_broker  # 初始化日志代理
        self.astrbot_config = astrbot_config  # 初始化配置
        self.db = db  # 初始化数据库

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

    async def initialize(self):
        """
        初始化 AstrBot 核心生命周期管理类, 负责初始化各个组件, 包括 ProviderManager、PlatformManager、ConversationManager、PluginManager、PipelineScheduler、EventBus、AstrBotUpdator等。
        """

        # 初始化日志代理
        logger.info("AstrBot v" + VERSION)
        if os.environ.get("TESTING", ""):
            logger.setLevel("DEBUG")  # 测试模式下设置日志级别为 DEBUG
        else:
            logger.setLevel(self.astrbot_config["log_level"])  # 设置日志级别

        await self.db.initialize()

        await html_renderer.initialize()

        # 初始化 AstrBot 配置管理器
        self.astrbot_config_mgr = AstrBotConfigManager(
            default_config=self.astrbot_config, sp=sp
        )

        # 初始化事件队列
        self.event_queue = Queue()

        # 初始化人格管理器
        self.persona_mgr = PersonaManager(self.db, self.astrbot_config_mgr)
        await self.persona_mgr.initialize()

        # 初始化供应商管理器
        self.provider_manager = ProviderManager(
            self.astrbot_config_mgr, self.db, self.persona_mgr
        )

        # 初始化平台管理器
        self.platform_manager = PlatformManager(self.astrbot_config, self.event_queue)

        # 初始化对话管理器
        self.conversation_manager = ConversationManager(self.db)

        # 初始化平台消息历史管理器
        self.platform_message_history_manager = PlatformMessageHistoryManager(self.db)

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
        )

        # 初始化插件管理器
        self.plugin_manager = PluginManager(self.star_context, self.astrbot_config)

        # 扫描、注册插件、实例化插件类
        await self.plugin_manager.reload()

        # 根据配置实例化各个 Provider
        await self.provider_manager.initialize()

        # 初始化消息事件流水线调度器

        self.pipeline_scheduler_mapping = await self.load_pipeline_scheduler()

        # 初始化更新器
        self.astrbot_updator = AstrBotUpdator()

        # 初始化事件总线
        self.event_bus = EventBus(
            self.event_queue, self.pipeline_scheduler_mapping, self.astrbot_config_mgr
        )

        # 记录启动时间
        self.start_time = int(time.time())

        # 初始化当前任务列表
        self.curr_tasks: List[asyncio.Task] = []

        # 根据配置实例化各个平台适配器
        await self.platform_manager.initialize()

        # 初始化关闭控制面板的事件
        self.dashboard_shutdown_event = asyncio.Event()

    def _load(self):
        """加载事件总线和任务并初始化"""

        # 创建一个异步任务来执行事件总线的 dispatch() 方法
        # dispatch是一个无限循环的协程, 从事件队列中获取事件并处理
        event_bus_task = asyncio.create_task(
            self.event_bus.dispatch(), name="event_bus"
        )

        # 把插件中注册的所有协程函数注册到事件总线中并执行
        extra_tasks = []
        for task in self.star_context._register_tasks:
            extra_tasks.append(asyncio.create_task(task, name=task.__name__))

        tasks_ = [event_bus_task, *extra_tasks]
        for task in tasks_:
            self.curr_tasks.append(
                asyncio.create_task(self._task_wrapper(task), name=task.get_name())
            )

        self.start_time = int(time.time())

    async def _task_wrapper(self, task: asyncio.Task):
        """异步任务包装器, 用于处理异步任务执行中出现的各种异常

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

    async def start(self):
        """启动 AstrBot 核心生命周期管理类, 用load加载事件总线和任务并初始化, 执行启动完成事件钩子"""
        self._load()
        logger.info("AstrBot 启动完成。")

        # 执行启动完成事件钩子
        handlers = star_handlers_registry.get_handlers_by_event_type(
            EventType.OnAstrBotLoadedEvent
        )
        for handler in handlers:
            try:
                logger.info(
                    f"hook(on_astrbot_loaded) -> {star_map[handler.handler_module_path].name} - {handler.handler_name}"
                )
                await handler.handler()
            except BaseException:
                logger.error(traceback.format_exc())

        # 同时运行curr_tasks中的所有任务
        await asyncio.gather(*self.curr_tasks, return_exceptions=True)

    async def stop(self):
        """停止 AstrBot 核心生命周期管理类, 取消所有当前任务并终止各个管理器"""
        # 请求停止所有正在运行的异步任务
        for task in self.curr_tasks:
            task.cancel()

        for plugin in self.plugin_manager.context.get_all_stars():
            try:
                await self.plugin_manager._terminate_plugin(plugin)
            except Exception as e:
                logger.warning(traceback.format_exc())
                logger.warning(
                    f"插件 {plugin.name} 未被正常终止 {e!s}, 可能会导致资源泄露等问题。"
                )

        await self.provider_manager.terminate()
        await self.platform_manager.terminate()
        self.dashboard_shutdown_event.set()

        # 再次遍历curr_tasks等待每个任务真正结束
        for task in self.curr_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"任务 {task.get_name()} 发生错误: {e}")

    async def restart(self):
        """重启 AstrBot 核心生命周期管理类, 终止各个管理器并重新加载平台实例"""
        await self.provider_manager.terminate()
        await self.platform_manager.terminate()
        self.dashboard_shutdown_event.set()
        threading.Thread(
            target=self.astrbot_updator._reboot, name="restart", daemon=True
        ).start()

    def load_platform(self) -> List[asyncio.Task]:
        """加载平台实例并返回所有平台实例的异步任务列表"""
        tasks = []
        platform_insts = self.platform_manager.get_insts()
        for platform_inst in platform_insts:
            tasks.append(
                asyncio.create_task(
                    platform_inst.run(),
                    name=f"{platform_inst.meta().id}({platform_inst.meta().name})",
                )
            )
        return tasks

    async def load_pipeline_scheduler(self) -> dict[str, PipelineScheduler]:
        """加载消息事件流水线调度器

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射
        """
        mapping = {}
        for conf_id, ab_config in self.astrbot_config_mgr.confs.items():
            scheduler = PipelineScheduler(
                PipelineContext(ab_config, self.plugin_manager, conf_id)
            )
            await scheduler.initialize()
            mapping[conf_id] = scheduler
        return mapping

    async def reload_pipeline_scheduler(self, conf_id: str):
        """重新加载消息事件流水线调度器

        Returns:
            dict[str, PipelineScheduler]: 平台 ID 到流水线调度器的映射
        """
        ab_config = self.astrbot_config_mgr.confs.get(conf_id)
        if not ab_config:
            raise ValueError(f"配置文件 {conf_id} 不存在")
        scheduler = PipelineScheduler(
            PipelineContext(ab_config, self.plugin_manager, conf_id)
        )
        await scheduler.initialize()
        self.pipeline_scheduler_mapping[conf_id] = scheduler
