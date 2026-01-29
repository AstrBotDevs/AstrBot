import time
import uuid
from typing import Any

from astrbot import logger
from astrbot.core.log import LogQueueHandler

_cached_log_broker = None


def _get_log_broker():
    global _cached_log_broker
    if _cached_log_broker is not None:
        return _cached_log_broker
    for handler in logger.handlers:
        if isinstance(handler, LogQueueHandler):
            _cached_log_broker = handler.log_broker
            return _cached_log_broker
    return None


class TraceSpan:
    def __init__(
        self,
        name: str,
        umo: str | None = None,
        sender_name: str | None = None,
        message_outline: str | None = None,
    ) -> None:
        self.span_id = str(uuid.uuid4())
        self.name = name
        self.umo = umo
        self.sender_name = sender_name
        self.message_outline = message_outline
        self.started_at = time.time()

    def record(self, action: str, **fields: Any) -> None:
        payload = {
            "type": "trace",
            "level": "TRACE",
            "time": time.time(),
            "span_id": self.span_id,
            "name": self.name,
            "umo": self.umo,
            "sender_name": self.sender_name,
            "message_outline": self.message_outline,
            "action": action,
            "fields": fields,
        }
        log_broker = _get_log_broker()
        if log_broker:
            log_broker.publish(payload)
            return
        logger.info(f"[trace] {payload}")
