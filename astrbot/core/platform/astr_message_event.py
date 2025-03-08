import abc
import asyncio
from dataclasses import dataclass
from .astrbot_message import AstrBotMessage
from .platform_metadata import PlatformMetadata
from astrbot.core.message.message_event_result import MessageEventResult, MessageChain
from astrbot.core.platform.message_type import MessageType
from typing import List, Union
from astrbot.core.message.components import (
    Plain,
    Image,
    BaseMessageComponent,
    Face,
    At,
    AtAll,
    Forward,
)
from astrbot.core.utils.metrics import Metric
from astrbot.core.provider.entites import ProviderRequest
from astrbot.core.db.po import Conversation


@dataclass
class MessageSesion:
    platform_name: str
    message_type: MessageType
    session_id: str

    def __str__(self):
        return f"{self.platform_name}:{self.message_type.value}:{self.session_id}"

    @staticmethod
    def from_str(session_str: str):
        platform_name, message_type, session_id = session_str.split(":")
        return MessageSesion(platform_name, MessageType(message_type), session_id)


class AstrMessageEvent(abc.ABC):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
    ):
        self.message_str = message_str
        """纯文本的消息"""
        self.message_obj = message_obj
        """消息对象, AstrBotMessage。带有完整的消息结构。"""
        self.platform_meta = platform_meta
        """消息平台的信息, 其中 name 是平台的类型，如 aiocqhttp"""
        self.session_id = session_id
        """用户的会话 ID。可以直接使用下面的 unified_msg_origin"""
        self.role = "member"
        """用户是否是管理员。如果是管理员，这里是 admin"""
        self.is_wake = False
        """是否唤醒(是否通过 WakingStage)"""
        self.is_at_or_wake_command = False
        """是否是 At 机器人或者带有唤醒词或者是私聊(插件注册的事件监听器会让 is_wake 设为 True, 但是不会让这个属性置为 True)"""
        self._extras = {}
        self.session = MessageSesion(
            platform_name=platform_meta.name,
            message_type=message_obj.type,
            session_id=session_id,
        )
        self.unified_msg_origin = str(self.session)
        """统一的消息来源字符串。格式为 platform_name:message_type:session_id"""
        self._result: MessageEventResult = None
        """消息事件的结果"""

        self._has_send_oper = False
        """在此次事件中是否有过至少一次发送消息的操作"""
        self.call_llm = False
        """是否在此消息事件中禁止默认的 LLM 请求"""

        # back_compability
        self.platform = platform_meta

    def get_platform_name(self):
        return self.platform_meta.name

    def get_message_str(self) -> str:
        """
        获取消息字符串。
        """
        return self.message_str

    def _outline_chain(self, chain: List[BaseMessageComponent]) -> str:
        outline = ""
        for i in chain:
            if isinstance(i, Plain):
                outline += i.text
            elif isinstance(i, Image):
                outline += "[图片]"
            elif isinstance(i, Face):
                outline += f"[表情:{i.id}]"
            elif isinstance(i, At):
                outline += f"[At:{i.qq}]"
            elif isinstance(i, AtAll):
                outline += "[At:全体成员]"
            elif isinstance(i, Forward):
                # 转发消息
                outline += "[转发消息]"
            else:
                outline += f"[{i.type}]"
        return outline

    def get_message_outline(self) -> str:
        """
        获取消息概要。

        除了文本消息外，其他消息类型会被转换为对应的占位符。如图片消息会被转换为 [图片]。
        """
        return self._outline_chain(self.message_obj.message)

    def get_messages(self) -> List[BaseMessageComponent]:
        """
        获取消息链。
        """
        return self.message_obj.message

    def get_message_type(self) -> MessageType:
        """
        获取消息类型。
        """
        return self.message_obj.type

    def get_session_id(self) -> str:
        """
        获取会话id。
        """
        return self.session_id

    def get_group_id(self) -> str:
        """
        获取群组id。如果不是群组消息，返回空字符串。
        """
        return self.message_obj.group_id

    def get_self_id(self) -> str:
        """
        获取机器人自身的id。
        """
        return self.message_obj.self_id

    def get_sender_id(self) -> str:
        """
        获取消息发送者的id。
        """
        return self.message_obj.sender.user_id

    def get_sender_name(self) -> str:
        """
        获取消息发送者的名称。(可能会返回空字符串)
        """
        return self.message_obj.sender.nickname

    def set_extra(self, key, value):
        """
        设置额外的信息。
        """
        self._extras[key] = value

    def get_extra(self, key=None):
        """
        获取额外的信息。
        """
        if key is None:
            return self._extras
        return self._extras.get(key, None)

    def clear_extra(self):
        """
        清除额外的信息。
        """
        self._extras.clear()

    def is_private_chat(self) -> bool:
        """
        是否是私聊。
        """
        return self.message_obj.type.value == (MessageType.FRIEND_MESSAGE).value

    def is_wake_up(self) -> bool:
        """
        是否是唤醒机器人的事件。
        """
        return self.is_wake

    def is_admin(self) -> bool:
        """
        是否是管理员。
        """
        return self.role == "admin"

    async def send(self, message: MessageChain):
        """
        发送消息到消息平台。
        """
        asyncio.create_task(Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name))
        self._has_send_oper = True

    async def _pre_send(self):
        """调度器会在执行 send() 前调用该方法"""

    async def _post_send(self):
        """调度器会在执行 send() 后调用该方法"""

    def set_result(self, result: Union[MessageEventResult, str]):
        """设置消息事件的结果。

        Note:
            事件处理器可以通过设置结果来控制事件是否继续传播，并向消息适配器发送消息。

            如果没有设置 `MessageEventResult` 中的 result_type，默认为 CONTINUE。即事件将会继续向后面的 listener 或者 command 传播。

        Example:
        ```
        async def ban_handler(self, event: AstrMessageEvent):
            if event.get_sender_id() in self.blacklist:
                event.set_result(MessageEventResult().set_console_log("由于用户在黑名单，因此消息事件中断处理。")).set_result_type(EventResultType.STOP)
                return

        async def check_count(self, event: AstrMessageEvent):
            self.count += 1
            event.set_result(MessageEventResult().set_console_log("数量已增加", logging.DEBUG).set_result_type(EventResultType.CONTINUE))
            return
        ```
        """
        if isinstance(result, str):
            result = MessageEventResult().message(result)
        self._result = result

    def stop_event(self):
        """终止事件传播。"""
        if self._result is None:
            self.set_result(MessageEventResult().stop_event())
        else:
            self._result.stop_event()

    def continue_event(self):
        """继续事件传播。"""
        if self._result is None:
            self.set_result(MessageEventResult().continue_event())
        else:
            self._result.continue_event()

    def is_stopped(self) -> bool:
        """
        是否终止事件传播。
        """
        if self._result is None:
            return False  # 默认是继续传播
        return self._result.is_stopped()

    def should_call_llm(self, call_llm: bool):
        """
        是否在此消息事件中禁止默认的 LLM 请求。

        只会阻止 AstrBot 默认的 LLM 请求链路，不会阻止插件中的 LLM 请求。
        """
        self.call_llm = call_llm

    def get_result(self) -> MessageEventResult:
        """
        获取消息事件的结果。
        """
        return self._result

    def clear_result(self):
        """
        清除消息事件的结果。
        """
        self._result = None

    """消息链相关"""

    def make_result(self) -> MessageEventResult:
        """
        创建一个空的消息事件结果。

        Example:

        ```python
        # 纯文本回复
        yield event.make_result().message("Hi")
        # 发送图片
        yield event.make_result().url_image("https://example.com/image.jpg")
        yield event.make_result().file_image("image.jpg")
        ```
        """
        return MessageEventResult()

    def plain_result(self, text: str) -> MessageEventResult:
        """
        创建一个空的消息事件结果，只包含一条文本消息。
        """
        return MessageEventResult().message(text)

    def image_result(self, url_or_path: str) -> MessageEventResult:
        """
        创建一个空的消息事件结果，只包含一条图片消息。

        根据开头是否包含 http 来判断是网络图片还是本地图片。
        """
        if url_or_path.startswith("http"):
            return MessageEventResult().url_image(url_or_path)
        return MessageEventResult().file_image(url_or_path)

    def chain_result(self, chain: List[BaseMessageComponent]) -> MessageEventResult:
        """
        创建一个空的消息事件结果，包含指定的消息链。
        """
        mer = MessageEventResult()
        mer.chain = chain
        return mer

    """LLM 请求相关"""

    def request_llm(
        self,
        prompt: str,
        func_tool_manager=None,
        session_id: str = None,
        image_urls: List[str] = [],
        contexts: List = [],
        system_prompt: str = "",
        conversation: Conversation = None,
    ) -> ProviderRequest:
        """
        创建一个 LLM 请求。

        Examples:
        ```py
        yield event.request_llm(prompt="hi")
        ```
        prompt: 提示词

        system_prompt: 系统提示词

        session_id: 已经过时，留空即可

        image_urls: 可以是 base64:// 或者 http:// 开头的图片链接，也可以是本地图片路径。

        contexts: 当指定 contexts 时，将会使用 contexts 作为上下文。如果同时传入了 conversation，将会忽略 conversation。

        func_tool_manager: 函数工具管理器，用于调用函数工具。用 self.context.get_llm_tool_manager() 获取。

        conversation: 可选。如果指定，将在指定的对话中进行 LLM 请求。对话的人格会被用于 LLM 请求，并且结果将会被记录到对话中。
        """

        if len(contexts) > 0 and conversation:
            conversation = None

        return ProviderRequest(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            func_tool=func_tool_manager,
            contexts=contexts,
            system_prompt=system_prompt,
            conversation=conversation,
        )
