"""旧版事件结果兼容类型。"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any

from ..message.chain import MessageChain


class EventResultType(enum.Enum):
    CONTINUE = enum.auto()
    STOP = enum.auto()


class ResultContentType(enum.Enum):
    LLM_RESULT = enum.auto()
    GENERAL_RESULT = enum.auto()
    STREAMING_RESULT = enum.auto()
    STREAMING_FINISH = enum.auto()


@dataclass
class MessageEventResult(MessageChain):
    result_type: EventResultType | None = field(
        default_factory=lambda: EventResultType.CONTINUE
    )
    result_content_type: ResultContentType | None = field(
        default_factory=lambda: ResultContentType.GENERAL_RESULT
    )
    async_stream: Any | None = None

    def stop_event(self) -> "MessageEventResult":
        self.result_type = EventResultType.STOP
        return self

    def continue_event(self) -> "MessageEventResult":
        self.result_type = EventResultType.CONTINUE
        return self

    def is_stopped(self) -> bool:
        return self.result_type == EventResultType.STOP

    def set_async_stream(self, stream: Any) -> "MessageEventResult":
        self.async_stream = stream
        return self

    def set_result_content_type(self, typ: ResultContentType) -> "MessageEventResult":
        self.result_content_type = typ
        return self

    def is_llm_result(self) -> bool:
        return self.result_content_type == ResultContentType.LLM_RESULT


CommandResult = MessageEventResult
