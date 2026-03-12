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
import time
from asyncio import Queue

from astrbot.core import logger
from astrbot.core.astrbot_config_mgr import AstrBotConfigManager
from astrbot.core.message.components import File, Image
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.utils.number_utils import safe_positive_float

from .platform import AstrMessageEvent


class EventDeduplicator:
    _MAX_RAW_TEXT_FINGERPRINT_LEN = 256

    def __init__(self, ttl_seconds: float = 0.5) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen: dict[tuple[str, ...], float] = {}

    def _clean_expired(self) -> None:
        now = time.monotonic()
        expire_before = now - self._ttl_seconds
        for fingerprint, timestamp in list(self._seen.items()):
            if timestamp < expire_before:
                del self._seen[fingerprint]

    def _build_attachment_signature(self, event: AstrMessageEvent) -> str:
        signatures: list[str] = []
        for component in event.get_messages():
            if isinstance(component, Image):
                image_ref = component.url or component.file or component.file_unique or ""
                if image_ref:
                    signatures.append(f"img:{image_ref}")
            elif isinstance(component, File):
                file_ref = component.url or component.file_ or component.name or ""
                if file_ref:
                    signatures.append(f"file:{file_ref}")

        if not signatures:
            return ""

        payload = "|".join(signatures)
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

    def _build_content_fingerprint(
        self,
        event: AstrMessageEvent,
    ) -> tuple[str, ...]:
        message_text = (event.get_message_str() or "").strip()
        if len(message_text) <= self._MAX_RAW_TEXT_FINGERPRINT_LEN:
            message_signature = message_text
        else:
            message_hash = hashlib.sha1(message_text.encode("utf-8")).hexdigest()[:16]
            message_signature = f"h:{len(message_text)}:{message_hash}"

        attachment_signature = self._build_attachment_signature(event)
        return (
            "content",
            event.get_platform_id() or "",
            event.unified_msg_origin or "",
            event.get_sender_id() or "",
            message_signature,
            attachment_signature,
        )

    def _build_message_id_fingerprint(self, event: AstrMessageEvent) -> tuple[str, ...] | None:
        message_id = str(getattr(event.message_obj, "message_id", "") or "")
        if not message_id:
            return None
        return (
            "message_id",
            event.get_platform_id() or "",
            event.unified_msg_origin or "",
            message_id,
        )

    def is_duplicate(self, event: AstrMessageEvent) -> bool:
        self._clean_expired()
        fingerprints = [self._build_content_fingerprint(event)]
        message_id_fingerprint = self._build_message_id_fingerprint(event)
        if message_id_fingerprint is not None:
            fingerprints.append(message_id_fingerprint)

        for fingerprint in fingerprints:
            if fingerprint in self._seen:
                return True

        ts = time.monotonic()
        for fingerprint in fingerprints:
            self._seen[fingerprint] = ts
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
