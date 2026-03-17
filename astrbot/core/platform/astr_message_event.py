import abc
import asyncio
import hashlib
import re
import uuid
from collections.abc import AsyncGenerator
from time import time
from typing import Any

from astrbot import logger
from astrbot.core.agent.tool import ToolSet
from astrbot.core.db.po import Conversation
from astrbot.core.message.components import (
    At,
    AtAll,
    BaseMessageComponent,
    Face,
    Forward,
    Image,
    Plain,
    Reply,
)
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.platform.message_type import MessageType
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.trace import TraceSpan

from .astrbot_message import AstrBotMessage, Group
from .message_session import MessageSesion, MessageSession  # noqa
from .platform_metadata import PlatformMetadata


class AstrMessageEvent(abc.ABC):
    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
    ) -> None:
        self.message_str = message_str
        """纯文本的消息"""
        self.message_obj = message_obj
        """消息对象, AstrBotMessage。带有完整的消息结构。"""
        self.platform_meta = platform_meta
        """消息平台的信息, 其中 name 是平台的类型，如 aiocqhttp"""
        self.role = "member"
        """用户是否是管理员。如果是管理员，这里是 admin"""
        self.is_wake = False
        """是否唤醒(是否通过 WakingStage)"""
        self.is_at_or_wake_command = False
        """是否是 At 机器人或者带有唤醒词或者是私聊(插件注册的事件监听器会让 is_wake 设为 True, 但是不会让这个属性置为 True)"""
        self._extras: dict[str, Any] = {}
        message_type = getattr(message_obj, "type", None)
        if not isinstance(message_type, MessageType):
            try:
                message_type = MessageType(str(message_type))
            except (ValueError, TypeError, AttributeError):
                logger.warning(
                    f"Failed to convert message type {message_obj.type!r} to MessageType. "
                    f"Falling back to FRIEND_MESSAGE."
                )
                message_type = MessageType.FRIEND_MESSAGE
        self.session = MessageSession(
            platform_name=platform_meta.id,
            message_type=message_type,
            session_id=session_id,
        )
        # self.unified_msg_origin = str(self.session)
        """统一的消息来源字符串。格式为 platform_name:message_type:session_id"""
        self._result: MessageEventResult | None = None
        """消息事件的结果"""

        self.created_at = time()
        """事件创建时间(Unix timestamp)"""
        self.trace = TraceSpan(
            name="AstrMessageEvent",
            umo=self.unified_msg_origin,
            sender_name=self.get_sender_name(),
            message_outline=self.get_message_outline(),
        )
        """用于记录事件处理的 TraceSpan 对象"""
        self.span = self.trace
        """事件级 TraceSpan(别名: span)"""

        self._has_send_oper = False
        """在此次事件中是否有过至少一次发送消息的操作"""
        self.call_llm = False
        """是否在此消息事件中禁止默认的 LLM 请求"""

        self.plugins_name: list[str] | None = None
        """该事件启用的插件名称列表。None 表示所有插件都启用。空列表表示没有启用任何插件。"""

        # back_compability
        self.platform = platform_meta

    @property
    def unified_msg_origin(self) -> str:
        """统一的消息来源字符串。格式为 platform_name:message_type:session_id"""
        return str(self.session)

    @unified_msg_origin.setter
    def unified_msg_origin(self, value: str) -> None:
        """设置统一的消息来源字符串。格式为 platform_name:message_type:session_id"""
        self.new_session = MessageSession.from_str(value)
        self.session = self.new_session

    @property
    def session_id(self) -> str:
        """用户的会话 ID。可以直接使用下面的 unified_msg_origin"""
        return self.session.session_id

    @session_id.setter
    def session_id(self, value: str) -> None:
        """设置用户的会话 ID。可以直接使用下面的 unified_msg_origin"""
        self.session.session_id = value

    def get_platform_name(self):
        """获取这个事件所属的平台的类型（如 aiocqhttp, slack, discord 等）。

        NOTE: 用户可能会同时运行多个相同类型的平台适配器。
        """
        return self.platform_meta.name

    def get_platform_id(self):
        """获取这个事件所属的平台的 ID。

        NOTE: 用户可能会同时运行多个相同类型的平台适配器，但能确定的是 ID 是唯一的。
        """
        return self.platform_meta.id

    def get_message_str(self) -> str:
        """获取消息字符串。"""
        return self.message_str

    def _outline_chain(self, chain: list[BaseMessageComponent] | None) -> str:
        if not chain:
            return ""

        parts = []
        for i in chain:
            if isinstance(i, Plain):
                parts.append(i.text)
            elif isinstance(i, Image):
                parts.append("[图片]")
            elif isinstance(i, Face):
                parts.append(f"[表情:{i.id}]")
            elif isinstance(i, At):
                parts.append(f"[At:{i.qq}]")
            elif isinstance(i, AtAll):
                parts.append("[At:全体成员]")
            elif isinstance(i, Forward):
                # 转发消息
                parts.append("[转发消息]")
            elif isinstance(i, Reply):
                # 引用回复
                if i.message_str:
                    parts.append(f"[引用消息({i.sender_nickname}: {i.message_str})]")
                else:
                    parts.append("[引用消息]")
            else:
                parts.append(f"[{i.type}]")
            parts.append(" ")
        return "".join(parts)

    def get_message_outline(self) -> str:
        """获取消息概要。

        除了文本消息外，其他消息类型会被转换为对应的占位符。如图片消息会被转换为 [图片]。
        """
        return self._outline_chain(getattr(self.message_obj, "message", None))

    def get_messages(self) -> list[BaseMessageComponent]:
        """获取消息链。"""
        return getattr(self.message_obj, "message", [])

    def get_message_type(self) -> MessageType:
        """获取消息类型。"""
        message_type = getattr(self.message_obj, "type", None)
        if isinstance(message_type, MessageType):
            return message_type
        return self.session.message_type

    def get_session_id(self) -> str:
        """获取会话id。"""
        return self.session_id

    def get_group_id(self) -> str:
        """获取群组id。如果不是群组消息，返回空字符串。"""
        return getattr(self.message_obj, "group_id", "")

    def get_self_id(self) -> str:
        """获取机器人自身的id。"""
        return getattr(self.message_obj, "self_id", "")

    def get_sender_id(self) -> str:
        """获取消息发送者的id。"""
        sender = getattr(self.message_obj, "sender", None)
        if sender and isinstance(getattr(sender, "user_id", None), str):
            return sender.user_id
        return ""

    def get_sender_name(self) -> str:
        """获取消息发送者的名称。(可能会返回空字符串)"""
        sender = getattr(self.message_obj, "sender", None)
        if not sender:
            return ""
        nickname = getattr(sender, "nickname", None)
        if nickname is None:
            return ""
        if isinstance(nickname, str):
            return nickname
        return str(nickname)

    def set_extra(self, key, value) -> None:
        """设置额外的信息。"""
        self._extras[key] = value

    def get_extra(self, key: str | None = None, default=None) -> Any:
        """获取额外的信息。"""
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def clear_extra(self) -> None:
        """清除额外的信息。"""
        logger.info(f"清除 {self.get_platform_name()} 的额外信息: {self._extras}")
        self._extras.clear()

    def is_private_chat(self) -> bool:
        """是否是私聊。"""
        return self.get_message_type() == MessageType.FRIEND_MESSAGE

    def is_wake_up(self) -> bool:
        """是否是唤醒机器人的事件。"""
        return self.is_wake

    def is_admin(self) -> bool:
        """是否是管理员。"""
        return self.role == "admin"

    async def process_buffer(self, buffer: str, pattern: re.Pattern) -> str:
        """将消息缓冲区中的文本按指定正则表达式分割后发送至消息平台，作为不支持流式输出平台的Fallback。"""
        while True:
            match = re.search(pattern, buffer)
            if not match:
                break
            matched_text = match.group()
            await self.send(MessageChain([Plain(matched_text)]))
            buffer = buffer[match.end() :]
            await asyncio.sleep(1.5)  # 限速
        return buffer

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ) -> None:
        """发送流式消息到消息平台，使用异步生成器。
        目前仅支持: telegram，qq official 私聊。
        Fallback仅支持 aiocqhttp。
        """
        asyncio.create_task(
            Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name),
        )
        self._has_send_oper = True

    async def send_typing(self) -> None:
        """发送输入中状态。

        默认实现为空，由具体平台按需重写。
        """

    async def _pre_send(self) -> None:
        """调度器会在执行 send() 前调用该方法 deprecated in v3.5.18"""

    async def _post_send(self) -> None:
        """调度器会在执行 send() 后调用该方法 deprecated in v3.5.18"""

    def set_result(self, result: MessageEventResult | str) -> None:
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
        # 兼容外部插件或调用方传入的 chain=None 的情况，确保为可迭代列表
        if isinstance(result, MessageEventResult) and result.chain is None:
            result.chain = []
        self._result = result

    def stop_event(self) -> None:
        """终止事件传播。"""
        if self._result is None:
            self.set_result(MessageEventResult().stop_event())
        else:
            self._result.stop_event()

    def continue_event(self) -> None:
        """继续事件传播。"""
        if self._result is None:
            self.set_result(MessageEventResult().continue_event())
        else:
            self._result.continue_event()

    def is_stopped(self) -> bool:
        """是否终止事件传播。"""
        if self._result is None:
            return False  # 默认是继续传播
        return self._result.is_stopped()

    def should_call_llm(self, call_llm: bool) -> None:
        """是否在此消息事件中禁止默认的 LLM 请求。

        只会阻止 AstrBot 默认的 LLM 请求链路，不会阻止插件中的 LLM 请求。
        """
        self.call_llm = call_llm

    def get_result(self) -> MessageEventResult | None:
        """获取消息事件的结果。"""
        return self._result

    def clear_result(self) -> None:
        """清除消息事件的结果。"""
        self._result = None

    """消息链相关"""

    def make_result(self) -> MessageEventResult:
        """创建一个空的消息事件结果。

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
        """创建一个空的消息事件结果，只包含一条文本消息。"""
        return MessageEventResult().message(text)

    def image_result(self, url_or_path: str) -> MessageEventResult:
        """创建一个空的消息事件结果，只包含一条图片消息。

        根据开头是否包含 http 来判断是网络图片还是本地图片。
        """
        if url_or_path.startswith("http"):
            return MessageEventResult().url_image(url_or_path)
        return MessageEventResult().file_image(url_or_path)

    def chain_result(self, chain: list[BaseMessageComponent]) -> MessageEventResult:
        """创建一个空的消息事件结果，包含指定的消息链。"""
        mer = MessageEventResult()
        mer.chain = chain
        return mer

    """LLM 请求相关"""

    def request_llm(
        self,
        prompt: str,
        func_tool_manager=None,
        tool_set: ToolSet | None = None,
        session_id: str = "",
        image_urls: list[str] | None = None,
        contexts: list | None = None,
        system_prompt: str = "",
        conversation: Conversation | None = None,
    ) -> ProviderRequest:
        """创建一个 LLM 请求。

        Examples:
        ```py
        yield event.request_llm(prompt="hi")
        ```
        prompt: 提示词

        system_prompt: 系统提示词

        session_id: 已经过时，留空即可

        image_urls: 可以是 base64:// 或者 http:// 开头的图片链接，也可以是本地图片路径。

        contexts: 当指定 contexts 时，将会使用 contexts 作为上下文。如果同时传入了 conversation，将会忽略 conversation。

        func_tool_manager: [Deprecated] 函数工具管理器，用于调用函数工具。用 self.context.get_llm_tool_manager() 获取。已过时，请使用 tool_set 参数代替。

        conversation: 可选。如果指定，将在指定的对话中进行 LLM 请求。对话的人格会被用于 LLM 请求，并且结果将会被记录到对话中。

        """
        if image_urls is None:
            image_urls = []
        if contexts is None:
            contexts = []
        if len(contexts) > 0 and conversation:
            conversation = None

        return ProviderRequest(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            # func_tool=func_tool_manager,
            func_tool=tool_set,
            contexts=contexts,
            system_prompt=system_prompt,
            conversation=conversation,
        )

    """平台适配器"""

    async def send(self, message: MessageChain) -> None:
        """发送消息到消息平台。

        Args:
            message (MessageChain): 消息链，具体使用方式请参考文档。

        """
        # Leverage BLAKE2 hash function to generate a non-reversible hash of the sender ID for privacy.
        hash_obj = hashlib.blake2b(self.get_sender_id().encode("utf-8"), digest_size=16)
        sid = str(uuid.UUID(bytes=hash_obj.digest()))
        asyncio.create_task(
            Metric.upload(
                msg_event_tick=1,
                adapter_name=self.platform_meta.name,
                sid=sid,
            ),
        )
        self._has_send_oper = True

    async def react(self, emoji: str) -> None:
        """对消息添加表情回应。

        默认实现为发送一条包含该表情的消息。
        注意：此实现并不一定符合所有平台的原生“表情回应”行为。
        如需支持平台原生的消息反应功能，请在对应平台的子类中重写本方法。
        """
        await self.send(MessageChain([Plain(emoji)]))

    async def get_group(self, group_id: str | None = None, **kwargs) -> Group | None:
        """获取一个群聊的数据, 如果不填写 group_id: 如果是私聊消息，返回 None。如果是群聊消息，返回当前群聊的数据。

        适配情况:

        - aiocqhttp(OneBotv11)
        """
