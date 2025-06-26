import enum

from typing import List, Optional, Union, AsyncGenerator
from dataclasses import dataclass, field
from astrbot.core.message.components import (
    BaseMessageComponent,
    Plain,
    Image,
    At,
    AtAll,
)
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

    def at(self, name: str, qq: Union[str, int]):
        """添加一条 At 消息到消息链 `chain` 中。

        Example:

            CommandResult().at("张三", "12345678910")
            # 输出 @张三

        """
        self.chain.append(At(name=name, qq=qq))
        return self

    def at_all(self):
        """添加一条 AtAll 消息到消息链 `chain` 中。

        Example:

            CommandResult().at_all()
            # 输出 @所有人

        """
        self.chain.append(AtAll())
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

    def base64_image(self, base64_str: str):
        """添加一条图片消息（base64 编码字符串）到消息链 `chain` 中。
        Example:

            CommandResult().base64_image("iVBORw0KGgoAAAANSUhEUgAAAAUA...")
        """
        self.chain.append(Image.fromBase64(base64_str))
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

    def squash_plain(self):
        """将消息链中的所有 Plain 消息段聚合到第一个 Plain 消息段中。"""
        if not self.chain:
            return

        new_chain = []
        first_plain = None
        plain_texts = []

        for comp in self.chain:
            if isinstance(comp, Plain):
                if first_plain is None:
                    first_plain = comp
                    new_chain.append(comp)
                plain_texts.append(comp.text)
            else:
                new_chain.append(comp)

        if first_plain is not None:
            first_plain.text = "".join(plain_texts)

        self.chain = new_chain
        return self


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

    result_type: Optional[EventResultType] = field(
        default_factory=lambda: EventResultType.CONTINUE
    )

    result_content_type: Optional[ResultContentType] = field(
        default_factory=lambda: ResultContentType.GENERAL_RESULT
    )

    async_stream: Optional[AsyncGenerator] = None
    """异步流"""

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

    def set_async_stream(self, stream: AsyncGenerator) -> "MessageEventResult":
        """设置异步流。"""
        self.async_stream = stream
        return self

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


# 为了兼容旧版代码，保留 CommandResult 的别名
CommandResult = MessageEventResult
