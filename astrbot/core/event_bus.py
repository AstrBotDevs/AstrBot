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

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.message.utils import (
    build_content_dedup_key,
    build_message_id_dedup_key,
)
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.utils.number_utils import safe_positive_float
from astrbot.core.utils.ttl_registry import TTLKeyRegistry

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
        dedup_ttl_seconds = safe_positive_float(
            self.astrbot_config_mgr.g(
                None,
                "event_bus_dedup_ttl_seconds",
                0.5,
            ),
            default=0.5,
        )
        self._dedup_registry = TTLKeyRegistry(ttl_seconds=dedup_ttl_seconds)

    @staticmethod
    def _build_event_content_key(event: AstrMessageEvent) -> str:
        return build_content_dedup_key(
            platform_id=str(event.get_platform_id() or ""),
            unified_msg_origin=str(event.unified_msg_origin or ""),
            sender_id=str(event.get_sender_id() or ""),
            text=str(event.get_message_str() or ""),
            components=event.get_messages(),
        )

    @staticmethod
    def _build_event_message_id_key(event: AstrMessageEvent) -> str | None:
        message_id = getattr(event.message_obj, "message_id", "") or getattr(
            event.message_obj,
            "id",
            "",
        )
        return build_message_id_dedup_key(
            platform_id=str(event.get_platform_id() or ""),
            unified_msg_origin=str(event.unified_msg_origin or ""),
            message_id=str(message_id or ""),
        )

    def _is_duplicate(self, event: AstrMessageEvent) -> bool:
        if self._dedup_registry.ttl_seconds == 0:
            return False

        message_id_key = self._build_event_message_id_key(event)
        if message_id_key is not None:
            if self._dedup_registry.contains(message_id_key):
                logger.debug(
                    "Skip duplicate event in event_bus (by message_id): umo=%s, sender=%s",
                    event.unified_msg_origin,
                    event.get_sender_id(),
                )
                return True
            self._dedup_registry.add(message_id_key)

        content_key = self._build_event_content_key(event)
        if self._dedup_registry.contains(content_key):
            logger.debug(
                "Skip duplicate event in event_bus (by content): umo=%s, sender=%s",
                event.unified_msg_origin,
                event.get_sender_id(),
            )
            if message_id_key is not None:
                self._dedup_registry.discard(message_id_key)
            return True

        self._dedup_registry.add(content_key)
        return False

    async def dispatch(self) -> None:
        # event_queue 由单一消费者处理；去重结构不是线程安全的，按设计仅在此循环中使用。
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            if self._is_duplicate(event):
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
