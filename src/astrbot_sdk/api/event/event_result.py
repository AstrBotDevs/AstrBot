from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import AsyncGenerator
from ..message.chain import MessageChain


class EventResultType(enum.Enum):
    """用于描述事件处理的结果类型。

    Attributes:
        CONTINUE: 事件将会继续传播
        STOP: 事件将会终止传播

    """

    CONTINUE = enum.auto()
    STOP = enum.auto()


class ResultContentType(enum.Enum):
    """用于描述事件结果的内容的类型。"""

    LLM_RESULT = enum.auto()
    """调用 LLM 产生的结果"""
    GENERAL_RESULT = enum.auto()
    """普通的消息结果"""
    STREAMING_RESULT = enum.auto()
    """调用 LLM 产生的流式结果"""
    STREAMING_FINISH = enum.auto()
    """流式输出完成"""


@dataclass
class MessageEventResult(MessageChain):
    """MessageEventResult 描述了一整条消息中带有的所有组件以及事件处理的结果。
    现代消息平台的一条富文本消息中可能由多个组件构成，如文本、图片、At 等，并且保留了顺序。

    Attributes:
        `chain` (list): 用于顺序存储各个组件。
        `use_t2i_` (bool): 用于标记是否使用文本转图片服务。默认为 None，即跟随用户的设置。当设置为 True 时，将会使用文本转图片服务。
        `result_type` (EventResultType): 事件处理的结果类型。

    """

    result_type: EventResultType | None = field(
        default_factory=lambda: EventResultType.CONTINUE,
    )

    result_content_type: ResultContentType | None = field(
        default_factory=lambda: ResultContentType.GENERAL_RESULT,
    )

    # async_stream: AsyncGenerator | None = None
    # """异步流"""

    def stop_event(self) -> MessageEventResult:
        """终止事件传播。"""
        self.result_type = EventResultType.STOP
        return self

    def continue_event(self) -> MessageEventResult:
        """继续事件传播。"""
        self.result_type = EventResultType.CONTINUE
        return self

    def is_stopped(self) -> bool:
        """是否终止事件传播。"""
        return self.result_type == EventResultType.STOP

    def set_async_stream(self, stream: AsyncGenerator) -> MessageEventResult:
        """设置异步流。"""
        self.async_stream = stream
        return self

    def set_result_content_type(self, typ: ResultContentType) -> MessageEventResult:
        """设置事件处理的结果类型。

        Args:
            result_type (EventResultType): 事件处理的结果类型。

        """
        self.result_content_type = typ
        return self

    def is_llm_result(self) -> bool:
        """是否为 LLM 结果。"""
        return self.result_content_type == ResultContentType.LLM_RESULT


# 为了兼容旧版代码，保留 CommandResult 的别名
CommandResult = MessageEventResult
