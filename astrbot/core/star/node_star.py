"""NodeStar base class for pipeline nodes."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from .star_base import Star

if TYPE_CHECKING:
    from astrbot.core.message.message_event_result import MessageEventResult
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.star.star import StarMetadata


class NodeResult(Enum):
    CONTINUE = "continue"
    STOP = "stop"
    WAIT = "wait"
    SKIP = "skip"


def is_node_star_metadata(metadata: StarMetadata) -> bool:
    """Return whether metadata represents a NodeStar plugin."""
    if metadata.star_cls_type:
        try:
            return issubclass(metadata.star_cls_type, NodeStar)
        except TypeError:
            return False
    return isinstance(metadata.star_cls, NodeStar)


class NodeStar(Star):
    """Star subclass that can be mounted into pipeline chains."""

    def __init__(self, context, config: dict | None = None):
        super().__init__(context, config)
        self.initialized_node_keys: set[tuple[str, str]] = set()

    async def node_initialize(self) -> None:
        pass

    async def process(
        self,
        event: AstrMessageEvent,
    ) -> NodeResult:
        raise NotImplementedError

    @staticmethod
    async def collect_stream(
        event: AstrMessageEvent,
        result: MessageEventResult | None = None,
    ) -> str | None:
        from astrbot.core.message.components import Plain
        from astrbot.core.message.message_event_result import (
            ResultContentType,
            collect_streaming_result,
        )

        if result is None:
            result = event.get_result()
        if not result:
            return None

        if result.result_content_type != ResultContentType.STREAMING_RESULT:
            return None

        if result.async_stream is None:
            return None

        await collect_streaming_result(result)

        parts: list[str] = [
            comp.text for comp in result.chain if isinstance(comp, Plain)
        ]
        return "".join(parts)
