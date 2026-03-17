from astrbot.core import logger
from astrbot.core.message.utils import (
    build_content_dedup_key,
    build_message_id_dedup_key,
)
from astrbot.core.utils.ttl_registry import TTLKeyRegistry

from .platform import AstrMessageEvent


class EventDeduplicator:
    def __init__(self, ttl_seconds: float = 0.5) -> None:
        self._registry = TTLKeyRegistry(ttl_seconds=ttl_seconds)

    def is_duplicate(self, event: AstrMessageEvent) -> bool:
        if self._registry.ttl_seconds == 0:
            return False

        message_id_key = self._build_message_id_key(event)
        if message_id_key is not None:
            if self._registry.contains(message_id_key):
                logger.debug(
                    "Skip duplicate event in event_bus (by message_id): umo=%s, sender=%s",
                    event.unified_msg_origin,
                    event.get_sender_id(),
                )
                return True
            self._registry.add(message_id_key)

        content_key = self._build_content_key(event)
        if self._registry.contains(content_key):
            logger.debug(
                "Skip duplicate event in event_bus (by content): umo=%s, sender=%s",
                event.unified_msg_origin,
                event.get_sender_id(),
            )
            if message_id_key is not None:
                self._registry.discard(message_id_key)
            return True

        self._registry.add(content_key)
        return False

    @staticmethod
    def _build_content_key(event: AstrMessageEvent) -> str:
        return build_content_dedup_key(
            platform_id=str(event.get_platform_id() or ""),
            unified_msg_origin=str(event.unified_msg_origin or ""),
            sender_id=str(event.get_sender_id() or ""),
            text=str(event.get_message_str() or ""),
            components=event.get_messages(),
        )

    @staticmethod
    def _build_message_id_key(event: AstrMessageEvent) -> str | None:
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
