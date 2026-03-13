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
import hashlib
from asyncio import Queue

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.message.utils import build_component_dedup_signature
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.utils.number_utils import safe_positive_float
from astrbot.core.utils.ttl_registry import TTLKeyRegistry

from .platform import AstrMessageEvent


class EventDeduplicator:
    """Event deduplicator using TTL-based registry.

    This class handles deduplication of events based on content fingerprint
    and message ID, with configurable TTL window.
    """

    _MAX_RAW_TEXT_FINGERPRINT_LEN = 256

    def __init__(self, ttl_seconds: float = 0.5) -> None:
        self._registry = TTLKeyRegistry(ttl_seconds)

    def _build_attachment_signature(self, event: AstrMessageEvent) -> str:
        """Build attachment signature for deduplication."""
        return build_component_dedup_signature(event.get_messages())

    def _build_content_key(self, event: AstrMessageEvent) -> str:
        """Build content-based deduplication key."""
        msg_text = (event.get_message_str() or "").strip()
        if len(msg_text) <= self._MAX_RAW_TEXT_FINGERPRINT_LEN:
            msg_sig = msg_text
        else:
            msg_hash = hashlib.sha1(msg_text.encode("utf-8")).hexdigest()[:16]
            msg_sig = f"h:{len(msg_text)}:{msg_hash}"

        attach_sig = self._build_attachment_signature(event)
        return "|".join([
            "content",
            event.get_platform_id() or "",
            event.unified_msg_origin or "",
            event.get_sender_id() or "",
            msg_sig,
            attach_sig,
        ])

    def _build_message_id_key(self, event: AstrMessageEvent) -> str | None:
        """Build message ID-based deduplication key.

        Falls back to message_obj.id if message_id is not available.
        """
        # Try message_id first
        message_id = str(getattr(event.message_obj, "message_id", "") or "")
        # Fallback to id if message_id is not available
        if not message_id:
            message_id = str(getattr(event.message_obj, "id", "") or "")
        if not message_id:
            return None
        return "|".join([
            "message_id",
            event.get_platform_id() or "",
            event.unified_msg_origin or "",
            message_id,
        ])

    def is_duplicate(self, event: AstrMessageEvent) -> bool:
        """Check if the event is a duplicate.

        Returns False immediately if TTL is 0 (deduplication disabled).
        Short-circuits on message_id key to avoid expensive attachment signature computation.
        """
        # TTL of 0 means deduplication is disabled
        if self._registry.ttl_seconds == 0:
            return False

        # Short-circuit: check message_id first (cheap) before computing full content key (expensive)
        message_id_key = self._build_message_id_key(event)
        if message_id_key is not None:
            if self._registry.contains(message_id_key):
                logger.debug(
                    "Skip duplicate event in event_bus (by message_id): umo=%s, sender=%s",
                    event.unified_msg_origin,
                    event.get_sender_id(),
                )
                return True
            # Register message_id key since we'll process the event
            self._registry.add(message_id_key)

        # Only compute full content key if we get past message_id check
        content_key = self._build_content_key(event)
        if self._registry.contains(content_key):
            logger.debug(
                "Skip duplicate event in event_bus (by content): umo=%s, sender=%s",
                event.unified_msg_origin,
                event.get_sender_id(),
            )
            # If content duplicate, also remove message_id to preserve existing behavior
            if message_id_key is not None:
                self._registry.discard(message_id_key)
            return True

        # Register content key
        self._registry.add(content_key)
        return False


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
        self._deduplicator = EventDeduplicator(ttl_seconds=dedup_ttl_seconds)

    async def dispatch(self) -> None:
        # event_queue 由单一消费者处理；去重结构不是线程安全的，按设计仅在此循环中使用。
        while True:
            event: AstrMessageEvent = await self.event_queue.get()
            if self._deduplicator.is_duplicate(event):
                logger.debug(
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
