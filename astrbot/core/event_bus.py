"""事件总线, 用于处理事件的分发和处理
事件总线是一个异步队列, 用于接收各种消息事件, 并将其发送到Scheduler调度器进行处理
其中包含了一个无限循环的调度函数, 用于从事件队列中获取新的事件, 并创建一个新的异步任务来执行管道调度器的处理逻辑

class:
    EventBus: 事件总线, 用于处理事件的分发和处理

工作流程:
1. 维护一个异步队列, 来接受各种消息事件
2. 无限循环的调度函数, 从事件队列中获取新的事件, 打印日志并创建一个新的异步任务来执行管道调度器的处理逻辑
"""

import asyncio
from asyncio import Queue
from collections import OrderedDict

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.db import BaseDatabase
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.umo_alias import get_event_auto_name

from .platform import AstrMessageEvent

MAX_UMO_AUTO_NAME_CACHE_SIZE = 10_000


class EventBus:
    """用于处理事件的分发和处理"""

    def __init__(
        self,
        event_queue: Queue,
        pipeline_scheduler_mapping: dict[str, PipelineScheduler],
        astrbot_config_mgr: AstrBotConfigManager,
        db_helper: BaseDatabase | None = None,
    ) -> None:
        self.event_queue = event_queue  # 事件队列
        # abconf uuid -> scheduler
        self.pipeline_scheduler_mapping = pipeline_scheduler_mapping
        self.astrbot_config_mgr = astrbot_config_mgr
        self.db_helper = db_helper
        self._umo_auto_name_cache: OrderedDict[str, str] = OrderedDict()
        self._pending_umo_auto_names: OrderedDict[str, tuple[str, str]] = OrderedDict()
        self._umo_auto_name_writer_task: asyncio.Task[None] | None = None
        # 持有正在执行的 pipeline 任务的强引用, 防止 task 在 pending 状态被 GC 回收
        self._pending_tasks: set[asyncio.Task] = set()

    async def dispatch(self) -> None:
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            conf_info = self.astrbot_config_mgr.get_conf_info(event.unified_msg_origin)
            conf_id = conf_info["id"]
            conf_name = conf_info.get("name") or conf_id
            self._print_event(event, conf_name)
            scheduler = self.pipeline_scheduler_mapping.get(conf_id)
            if not scheduler:
                logger.error(
                    f"PipelineScheduler not found for id: {conf_id}, event ignored."
                )
                continue
            task = asyncio.create_task(self._execute_pipeline(scheduler, event))
            self._pending_tasks.add(task)
            task.add_done_callback(self._on_task_done)

    async def _execute_pipeline(
        self,
        scheduler: PipelineScheduler,
        event: AstrMessageEvent,
    ) -> None:
        """Execute the pipeline and record the UMO name after a successful wake.

        Args:
            scheduler: Pipeline scheduler selected for the event configuration.
            event: Inbound platform event to process.
        """
        await scheduler.execute(event)
        if event.is_wake:
            self._schedule_umo_auto_name_recording(event)

    def _schedule_umo_auto_name_recording(self, event: AstrMessageEvent) -> None:
        """Queue a changed automatic UMO name for background persistence.

        Args:
            event: Inbound platform event containing the UMO and display metadata.
        """
        if self.db_helper is None:
            return

        umo = event.unified_msg_origin
        auto_name = get_event_auto_name(event, fallback_to_id=False)
        if not auto_name:
            return
        if self._umo_auto_name_cache.get(umo) == auto_name:
            self._umo_auto_name_cache.move_to_end(umo)
            return

        self._umo_auto_name_cache[umo] = auto_name
        self._umo_auto_name_cache.move_to_end(umo)
        if len(self._umo_auto_name_cache) > MAX_UMO_AUTO_NAME_CACHE_SIZE:
            self._umo_auto_name_cache.popitem(last=False)

        self._pending_umo_auto_names[umo] = (
            str(event.get_sender_id() or ""),
            auto_name,
        )
        self._pending_umo_auto_names.move_to_end(umo)
        if len(self._pending_umo_auto_names) > MAX_UMO_AUTO_NAME_CACHE_SIZE:
            dropped_umo, (_, dropped_name) = self._pending_umo_auto_names.popitem(
                last=False
            )
            if self._umo_auto_name_cache.get(dropped_umo) == dropped_name:
                self._umo_auto_name_cache.pop(dropped_umo, None)

        if (
            self._umo_auto_name_writer_task is None
            or self._umo_auto_name_writer_task.done()
        ):
            task = asyncio.create_task(
                self._flush_umo_auto_names(),
                name="umo_auto_name_writer",
            )
            self._umo_auto_name_writer_task = task
            self._pending_tasks.add(task)
            task.add_done_callback(self._on_task_done)

    async def _flush_umo_auto_names(self) -> None:
        """Persist queued UMO names sequentially, coalescing changes per UMO."""
        if self.db_helper is None:
            return

        try:
            while self._pending_umo_auto_names:
                umo, (creator_sender_id, auto_name) = (
                    self._pending_umo_auto_names.popitem(last=False)
                )
                try:
                    await self.db_helper.upsert_umo_auto_name(
                        umo=umo,
                        creator_sender_id=creator_sender_id,
                        auto_name=auto_name,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to persist automatic UMO name for %s: %s",
                        umo,
                        exc,
                    )
                    if (
                        umo not in self._pending_umo_auto_names
                        and self._umo_auto_name_cache.get(umo) == auto_name
                    ):
                        self._umo_auto_name_cache.pop(umo, None)
        finally:
            self._umo_auto_name_writer_task = None

    def _on_task_done(self, task: asyncio.Task) -> None:
        """pipeline 任务结束回调: 移除强引用并暴露未捕获的异常"""
        self._pending_tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("Pipeline task failed.", exc_info=exc)

    def _print_event(self, event: AstrMessageEvent, conf_name: str) -> None:
        """用于记录事件信息

        Args:
            event (AstrMessageEvent): 事件对象

        """
        # 如果有发送者名称: [平台名] 发送者名称/发送者ID: 消息概要
        if event.get_sender_name():
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_name()}/{event.get_sender_id()}: {event.get_message_outline()}",
                extra={"category": "user_chat"},
            )
        # 没有发送者名称: [平台名] 发送者ID: 消息概要
        else:
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_id()}: {event.get_message_outline()}",
                extra={"category": "user_chat"},
            )
