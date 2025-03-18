import enum

from typing import List, Optional
from dataclasses import dataclass, field
from astrbot.core.message.components import BaseMessageComponent, Plain, Image
from typing_extensions import deprecated


@dataclass
class MessageChain:
    """MessageChain 描述了一整条消息中带有的所有组件。
    现代消息平台的一条富文本消息中可能由多个组件构成，如文本、图片、At 等，并且保留了顺序。

    Attributes:
        `chain` (list): 用于顺序存储各个组件。
        `use_t2i_` (bool): 用于标记是否使用文本转图片服务。默认为 None，即跟随用户的设置。当设置为 True 时，将会使用文本转图片服务。
    """

    chain: List[BaseMessageComponent] = field(default_factory=list)
    use_t2i_: Optional[bool] = None  # None 为跟随用户设置

    def message(self, message: str):
        """添加一条文本消息到消息链 `chain` 中。

        Example:

            CommandResult().message("Hello ").message("world!")
            # 输出 Hello world!

        """
        self.chain.append(Plain(message))
        return self

    @deprecated("请使用 message 方法代替。")
    def error(self, message: str):
        """添加一条错误消息到消息链 `chain` 中

        Example:

            CommandResult().error("解析失败")

        """
        self.chain.append(Plain(message))
        return self

    def url_image(self, url: str):
        """添加一条图片消息（https 链接）到消息链 `chain` 中。

        Note:
            如果需要发送本地图片，请使用 `file_image` 方法。

        Example:

            CommandResult().image("https://example.com/image.jpg")

        """
        self.chain.append(Image.fromURL(url))
        return self

    def file_image(self, path: str):
        """添加一条图片消息（本地文件路径）到消息链 `chain` 中。

        Note:
            如果需要发送网络图片，请使用 `url_image` 方法。

        CommandResult().image("image.jpg")
        """
        self.chain.append(Image.fromFileSystem(path))
        return self

    def use_t2i(self, use_t2i: bool):
        """设置是否使用文本转图片服务。

        Args:
            use_t2i (bool): 是否使用文本转图片服务。默认为 None，即跟随用户的设置。当设置为 True 时，将会使用文本转图片服务。
        """
        self.use_t2i_ = use_t2i
        return self

    def get_plain_text(self) -> str:
        """获取纯文本消息。这个方法将获取 chain 中所有 Plain 组件的文本并拼接成一条消息。空格分隔。"""
        return " ".join([comp.text for comp in self.chain if isinstance(comp, Plain)])


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


@dataclass
class MessageEventResult(MessageChain):
    """MessageEventResult 描述了一整条消息中带有的所有组件以及事件处理的结果。
    现代消息平台的一条富文本消息中可能由多个组件构成，如文本、图片、At 等，并且保留了顺序。

    Attributes:
        `chain` (list): 用于顺序存储各个组件。
        `use_t2i_` (bool): 用于标记是否使用文本转图片服务。默认为 None，即跟随用户的设置。当设置为 True 时，将会使用文本转图片服务。
        `result_type` (EventResultType): 事件处理的结果类型。
    """

    result_type: Optional[EventResultType] = field(
        default_factory=lambda: EventResultType.CONTINUE
    )

    result_content_type: Optional[ResultContentType] = field(
        default_factory=lambda: ResultContentType.GENERAL_RESULT
    )

    def stop_event(self) -> "MessageEventResult":
        """终止事件传播。"""
        self.result_type = EventResultType.STOP
        return self

    def continue_event(self) -> "MessageEventResult":
        """继续事件传播。"""
        self.result_type = EventResultType.CONTINUE
        return self

    def is_stopped(self) -> bool:
        """
        是否终止事件传播。
        """
        return self.result_type == EventResultType.STOP

    def set_result_content_type(self, typ: ResultContentType) -> "MessageEventResult":
        """设置事件处理的结果类型。

        Args:
            result_type (EventResultType): 事件处理的结果类型。
        """
        self.result_content_type = typ
        return self

    def is_llm_result(self) -> bool:
        """是否为 LLM 结果。"""
        return self.result_content_type == ResultContentType.LLM_RESULT

CommandResult = MessageEventResult
