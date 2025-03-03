import traceback
import asyncio
import time
import threading
import os
from .event_bus import EventBus
from . import astrbot_config
from asyncio import Queue
from typing import List
from astrbot.core.pipeline.scheduler import PipelineScheduler, PipelineContext
from astrbot.core.star import PluginManager
from astrbot.core.platform.manager import PlatformManager
from astrbot.core.star.context import Context
from astrbot.core.provider.manager import ProviderManager
from astrbot.core import LogBroker
from astrbot.core.db import BaseDatabase
from astrbot.core.updator import AstrBotUpdator
from astrbot.core import logger
from astrbot.core.config.default import VERSION
from astrbot.core.rag.knowledge_db_mgr import KnowledgeDBManager
from astrbot.core.conversation_mgr import ConversationManager
from astrbot.core.star.star_handler import star_handlers_registry, EventType
from astrbot.core.star.star_handler import star_map


class AstrBotCoreLifecycle:
    def __init__(self, log_broker: LogBroker, db: BaseDatabase):
        self.log_broker = log_broker
        self.astrbot_config = astrbot_config
        self.db = db

        os.environ["https_proxy"] = self.astrbot_config["http_proxy"]
        os.environ["http_proxy"] = self.astrbot_config["http_proxy"]
        os.environ["no_proxy"] = "localhost"

    async def initialize(self):
        logger.info("AstrBot v" + VERSION)
        if os.environ.get("TESTING", ""):
            logger.setLevel("DEBUG")
        else:
            logger.setLevel(self.astrbot_config["log_level"])
        self.event_queue = Queue()
        self.event_queue.closed = False

        self.provider_manager = ProviderManager(self.astrbot_config, self.db)

        self.platform_manager = PlatformManager(self.astrbot_config, self.event_queue)

        self.knowledge_db_manager = KnowledgeDBManager(self.astrbot_config)

        self.conversation_manager = ConversationManager(self.db)

        self.star_context = Context(
            self.event_queue,
            self.astrbot_config,
            self.db,
            self.provider_manager,
            self.platform_manager,
            self.conversation_manager,
            self.knowledge_db_manager,
        )
        self.plugin_manager = PluginManager(self.star_context, self.astrbot_config)

        await self.plugin_manager.reload()
        """扫描、注册插件、实例化插件类"""

        await self.provider_manager.initialize()
        """根据配置实例化各个 Provider"""

        self.pipeline_scheduler = PipelineScheduler(
            PipelineContext(self.astrbot_config, self.plugin_manager)
        )
        await self.pipeline_scheduler.initialize()
        """初始化消息事件流水线调度器"""

        self.astrbot_updator = AstrBotUpdator(self.astrbot_config["plugin_repo_mirror"])
        self.event_bus = EventBus(self.event_queue, self.pipeline_scheduler)
        self.start_time = int(time.time())
        self.curr_tasks: List[asyncio.Task] = []

        await self.platform_manager.initialize()
        """根据配置实例化各个平台适配器"""

    def _load(self):
        event_bus_task = asyncio.create_task(
            self.event_bus.dispatch(), name="event_bus"
        )

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
        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"------- 任务 {task.get_name()} 发生错误: {e}")
            for line in traceback.format_exc().split("\n"):
                logger.error(f"|    {line}")
            logger.error("-------")

    async def start(self):
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

        await asyncio.gather(*self.curr_tasks, return_exceptions=True)

    async def stop(self):
        self.event_queue.closed = True
        for task in self.curr_tasks:
            task.cancel()

        await self.provider_manager.terminate()

        for task in self.curr_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"任务 {task.get_name()} 发生错误: {e}")

    def restart(self):
        self.event_queue.closed = True
        threading.Thread(
            target=self.astrbot_updator._reboot, name="restart", daemon=True
        ).start()

    def load_platform(self) -> List[asyncio.Task]:
        tasks = []
        platform_insts = self.platform_manager.get_insts()
        for platform_inst in platform_insts:
            tasks.append(
                asyncio.create_task(platform_inst.run(), name=platform_inst.meta().name)
            )
        return tasks
