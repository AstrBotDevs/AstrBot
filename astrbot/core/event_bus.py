"""事件总线, 用于处理事件的分发和处理
事件总线是一个异步队列, 用于接收各种消息事件, 并将其发送到Scheduler调度器进行处理
其中包含了一个无限循环的调度函数, 用于从事件队列中获取新的事件, 并创建一个新的异步任务来执行管道调度器的处理逻辑

class:
    EventBus: 事件总线, 用于处理事件的分发和处理
    DebounceManager: 消息防抖管理器, 短时间内的同会话消息合并为一条再调度

工作流程:
1. 维护一个异步队列, 来接受各种消息事件
2. 无限循环的调度函数, 从事件队列中获取新的事件, 打印日志并创建一个新的异步任务来执行管道调度器的处理逻辑
   - 若启用了消息防抖, 则交由 DebounceManager 聚合后统一执行
"""

import asyncio
import copy
from asyncio import Queue

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.message.components import At, Reply
from astrbot.core.pipeline.scheduler import PipelineScheduler

from .platform import AstrMessageEvent


class DebounceManager:
    """消息防抖管理器：短时间内的同会话消息合并为一条再调度。

    当 message_debounce.enable = true 时，
    同一 unified_msg_origin 的连续消息会在 interval 秒内聚合，
    计时器被新消息重置，超时后合并所有消息一次性交给 scheduler 执行。
    """

    def __init__(
        self,
        config_mgr: AstrBotConfigManager,
        scheduler_mapping: dict[str, PipelineScheduler],
    ) -> None:
        self._config_mgr = config_mgr
        self._scheduler_mapping = scheduler_mapping
        self._tasks: dict[str, asyncio.Task] = {}
        self._buffers: dict[str, list[AstrMessageEvent]] = {}

    async def push(self, event: AstrMessageEvent) -> None:
        """推送事件到防抖管理器。若同会话已有等待计时器则重置, 否则创建新计时器。"""
        origin = event.unified_msg_origin

        # Cancel existing timer if any
        existing = self._tasks.get(origin)
        if existing is not None and not existing.done():
            existing.cancel()
            logger.debug(f"[Debounce] 重置计时器: {origin}")

        # Get interval from config
        conf = self._config_mgr.get_conf(origin)
        debounce_cfg = conf.get("platform_settings", {}).get("message_debounce", {})
        interval: int = max(1, int(debounce_cfg.get("interval", 2)))

        # Buffer
        if origin not in self._buffers:
            self._buffers[origin] = []
        self._buffers[origin].append(event)

        # Start new timer
        self._tasks[origin] = asyncio.create_task(
            self._flush_after_delay(origin, interval),
        )

    async def _flush_after_delay(self, origin: str, interval: int) -> None:
        """等待 interval 秒后刷新缓冲区。被取消则静默退出（有新消息重置了计时器）。"""
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return

        events = self._buffers.pop(origin, [])
        self._tasks.pop(origin, None)

        if not events:
            return

        # Find scheduler
        conf_info = self._config_mgr.get_conf_info(origin)
        conf_id = conf_info["id"]
        scheduler = self._scheduler_mapping.get(conf_id)
        if not scheduler:
            logger.error(
                f"[Debounce] PipelineScheduler not found for id: {conf_id}, events discarded."
            )
            return

        # Merge if multiple
        merged = events[0] if len(events) == 1 else self._merge_events(events)

        logger.info(
            f"[Debounce] 合并 {len(events)} 条消息后执行调度: {origin}"
        )
        await scheduler.execute(merged)

    @staticmethod
    def _merge_events(events: list[AstrMessageEvent]) -> AstrMessageEvent:
        """将多条消息合并为一条, 保留第一条的会话信息, 追加文本和组件。"""
        # Copy the first event's message data to avoid mutating the original
        base = events[0]

        # Guard against None message_str
        merged_str = (base.message_str or "") + "".join(
            "\n" + (ev.message_str or "")
            for ev in events[1:]
            if ev.message_str
        )

        # Guard against None message_obj
        merged_components = list(base.message_obj.message) if base.message_obj and base.message_obj.message else []
        for ev in events[1:]:
            if ev.message_obj and ev.message_obj.message:
                for comp in ev.message_obj.message:
                    if not isinstance(comp, (At, Reply)):
                        merged_components.append(comp)

        # Apply merged data to base (shallow copy of components already done above)
        base.message_str = merged_str
        if base.message_obj:
            base.message_obj.message = merged_components

        return base


class EventBus:
    """用于处理事件的分发和处理"""

    def __init__(
        self,
        event_queue: Queue,
        pipeline_scheduler_mapping: dict[str, PipelineScheduler],
        astrbot_config_mgr: AstrBotConfigManager,
    ) -> None:
        self.event_queue = event_queue  # 事件队列
        # abconf uuid -> scheduler
        self.pipeline_scheduler_mapping = pipeline_scheduler_mapping
        self.astrbot_config_mgr = astrbot_config_mgr
        self._debounce_mgr = DebounceManager(
            astrbot_config_mgr, pipeline_scheduler_mapping
        )

    async def dispatch(self) -> None:
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            conf_info = self.astrbot_config_mgr.get_conf_info(event.unified_msg_origin)
            conf_id = conf_info["id"]
            conf_name = conf_info.get("name") or conf_id
            self._print_event(event, conf_name)

            # Check if debounce is enabled for this session
            conf = self.astrbot_config_mgr.get_conf(event.unified_msg_origin)
            debounce_cfg = conf.get("platform_settings", {}).get(
                "message_debounce", {}
            )
            if debounce_cfg.get("enable", False):
                logger.debug(
                    f"[Debounce] 消息进入防抖队列: {event.get_message_outline()}"
                )
                await self._debounce_mgr.push(event)
                continue

            scheduler = self.pipeline_scheduler_mapping.get(conf_id)
            if not scheduler:
                logger.error(
                    f"PipelineScheduler not found for id: {conf_id}, event ignored."
                )
                continue
            asyncio.create_task(scheduler.execute(event))

    def _print_event(self, event: AstrMessageEvent, conf_name: str) -> None:
        """用于记录事件信息

        Args:
            event (AstrMessageEvent): 事件对象

        """
        # 如果有发送者名称: [平台名] 发送者名称/发送者ID: 消息概要
        if event.get_sender_name():
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_name()}/{event.get_sender_id()}: {event.get_message_outline()}",
            )
        # 没有发送者名称: [平台名] 发送者ID: 消息概要
        else:
            logger.info(
                f"[{conf_name}] [{event.get_platform_id()}({event.get_platform_name()})] {event.get_sender_id()}: {event.get_message_outline()}",
            )
