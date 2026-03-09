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
import time
from asyncio import Queue
from collections import deque

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.pipeline.scheduler import PipelineScheduler

from .platform import AstrMessageEvent


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
        # 跨平台实例短窗去重（兜底）：处理同一消息在极短时间内重复入队。
        # 最近事件指纹，短窗去重（0.5s），单消费者线程内使用
        self._dedup_ttl_seconds = 0.5
        self._dedup_seen: set[tuple] = set()  # Set[Fingerprint]
        self._dedup_queue: deque[tuple[float, tuple]] = (
            deque()
        )  # deque[(timestamp, Fingerprint)]

    def _clean_expired_event_fingerprints(self) -> None:
        # Use monotonic clock to avoid issues with system clock changes
        now = time.monotonic()
        expire_before = now - self._dedup_ttl_seconds
        while self._dedup_queue and self._dedup_queue[0][0] < expire_before:
            _, fingerprint = self._dedup_queue.popleft()
            self._dedup_seen.discard(fingerprint)

    def _build_event_fingerprint(self, event: AstrMessageEvent) -> tuple:
        # 简单元组键即可，避免拼接和哈希
        return (
            event.get_platform_id() or "",
            event.unified_msg_origin or "",
            event.get_sender_id() or "",
            (event.get_message_str() or "").strip(),
        )

    def _is_duplicate_event(self, event: AstrMessageEvent) -> bool:
        # dispatch 是单消费者循环，未加锁是有意为之
        self._clean_expired_event_fingerprints()
        fingerprint = self._build_event_fingerprint(event)
        if fingerprint in self._dedup_seen:
            return True
        ts = time.monotonic()
        self._dedup_seen.add(fingerprint)
        self._dedup_queue.append((ts, fingerprint))
        return False

    async def dispatch(self) -> None:
        # event_queue 由单一消费者处理；去重结构不是线程安全的，按设计仅在此循环中使用。
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            if self._is_duplicate_event(event):
                logger.info(
                    "Skip duplicate event in event_bus, umo=%s, sender=%s",
                    event.unified_msg_origin,
                    event.get_sender_id(),
                )
                continue
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
