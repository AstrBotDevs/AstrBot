from __future__ import annotations
import typing as T
from .astrbot_message import AstrBotMessage, Group
from ...api.platform.platform_metadata import PlatformMetadata
from ...api.event.message_type import MessageType
from ...api.event.message_session import MessageSession
from ...api.event.event_result import MessageEventResult
from ...api.message.chain import MessageChain
from ...api.message.components import BaseMessageComponent
from dataclasses import dataclass, field
from pydantic import BaseModel, Field


class AstrMessageEventModel(BaseModel):
    message_str: str
    message_obj: AstrBotMessage
    platform_meta: PlatformMetadata
    session_id: str
    role: T.Literal["admin", "member"] = "member"
    is_wake: bool = False
    is_at_or_wake_command: bool = False
    extras: dict = Field(default_factory=dict)
    result: MessageEventResult | None = None
    has_send_oper: bool = False
    call_llm: bool = False
    plugins_name: list[str] = Field(default_factory=list)

    @classmethod
    def from_event(cls, event: AstrMessageEvent) -> AstrMessageEventModel:
        return cls(
            message_str=event.message_str,
            message_obj=event.message_obj,
            platform_meta=event.platform_meta,
            session_id=event.session_id,
            role=event.role,
            is_wake=event.is_wake,
            is_at_or_wake_command=event.is_at_or_wake_command,
            extras=event._extras,
            result=event._result,
            has_send_oper=event.has_send_oper,
            call_llm=event.call_llm,
            plugins_name=event._plugins_name,
        )

    def to_event(self) -> AstrMessageEvent:
        event = AstrMessageEvent(
            message_str=self.message_str,
            message_obj=self.message_obj,
            platform_meta=self.platform_meta,
            session_id=self.session_id,
            role=self.role,
            is_wake=self.is_wake,
            is_at_or_wake_command=self.is_at_or_wake_command,
            _extras=self.extras,
            _result=self.result,
            has_send_oper=self.has_send_oper,
            call_llm=self.call_llm,
            _plugins_name=self.plugins_name,
        )
        return event


@dataclass
class AstrMessageEvent:
    message_str: str
    """消息的纯文本内容"""

    message_obj: AstrBotMessage
    """消息对象"""

    platform_meta: PlatformMetadata
    """平台适配器的元信息"""

    session_id: str
    """会话 ID"""

    role: T.Literal["admin", "member"] = "member"
    """消息发送者的角色，如 "admin", "member" 等"""

    is_wake: bool = False
    """是否唤醒(是否通过 WakingStage)"""

    is_at_or_wake_command: bool = False
    """是否艾特机器人或通过唤醒命令触发的消息"""

    _extras: dict = field(default_factory=dict)
    """存储额外的信息"""

    _result: MessageEventResult | None = None
    """消息事件的结果"""

    has_send_oper: bool = False
    """是否已经发送过操作"""

    call_llm: bool = False
    """是否调用 LLM"""

    _plugins_name: list[str] = field(default_factory=list)
    """处理该事件的插件名称列表"""

    def __post_init__(self):
        self.session = MessageSession(
            platform_name=self.platform_meta.id,
            message_type=self.message_obj.type,
            session_id=self.session_id,
        )
        self.unified_msg_origin = str(self.session)
        self.platform = self.platform_meta  # back compatibility

    def get_platform_name(self) -> str:
        """
        获取这个事件所属的平台的类型（如 aiocqhttp, slack, discord 等）。
        NOTE: 用户可能会同时运行多个相同类型的平台适配器。
        """
        return self.platform_meta.name

    def get_platform_id(self):
        """
        获取这个事件所属的平台的 ID。
        NOTE: 用户可能会同时运行多个相同类型的平台适配器，但能确定的是 ID 是唯一的。
        """
        return self.platform_meta.id

    def get_message_str(self) -> str:
        """获取消息字符串。"""
        return self.message_str

    def get_messages(self) -> list[BaseMessageComponent]:
        """获取消息链。"""
        return self.message_obj.message

    def get_message_type(self) -> MessageType:
        """获取消息类型。"""
        return self.message_obj.type

    def get_session_id(self) -> str:
        """获取会话id。"""
        return self.session_id

    def get_group_id(self) -> str:
        """获取群组id。如果不是群组消息，返回空字符串。"""
        return self.message_obj.group_id

    def get_self_id(self) -> str:
        """获取机器人自身的id。"""
        return self.message_obj.self_id

    def get_sender_id(self) -> str:
        """获取消息发送者的id。"""
        return self.message_obj.sender.user_id

    def get_sender_name(self) -> str | None:
        """获取消息发送者的名称。(可能会返回空字符串)"""
        return self.message_obj.sender.nickname

    def set_extra(self, key, value):
        """设置额外的信息。"""
        self._extras[key] = value

    def get_extra(self, key: str | None = None, default=None) -> T.Any:
        """获取额外的信息。"""
        if key is None:
            return self._extras
        return self._extras.get(key, default)

    def clear_extra(self):
        """清除额外的信息。"""
        self._extras.clear()

    def is_private_chat(self) -> bool:
        """是否是私聊。"""
        return self.message_obj.type.value == (MessageType.FRIEND_MESSAGE).value

    def is_wake_up(self) -> bool:
        """是否是唤醒机器人的事件。"""
        return self.is_wake

    def is_admin(self) -> bool:
        """是否是管理员。"""
        return self.role == "admin"

    # async def send_streaming(
    #     self,
    #     generator: AsyncGenerator[MessageChain, None],
    #     use_fallback: bool = False,
    # ):
    #     """发送流式消息到消息平台，使用异步生成器。
    #     目前仅支持: telegram，qq official 私聊。
    #     Fallback仅支持 aiocqhttp。
    #     """
    #     asyncio.create_task(
    #         Metric.upload(msg_event_tick=1, adapter_name=self.platform_meta.name),
    #     )
    #     self._has_send_oper = True

    def set_result(self, result: MessageEventResult | str):
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
        """是否终止事件传播。"""
        if self._result is None:
            return False  # 默认是继续传播
        return self._result.is_stopped()

    def should_call_llm(self, call_llm: bool):
        """是否在此消息事件中禁止默认的 LLM 请求。

        只会阻止 AstrBot 默认的 LLM 请求链路，不会阻止插件中的 LLM 请求。
        """
        self.call_llm = call_llm

    def get_result(self) -> MessageEventResult | None:
        """获取消息事件的结果。"""
        return self._result

    def clear_result(self):
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

    # """LLM 请求相关"""

    # def request_llm(
    #     self,
    #     prompt: str,
    #     func_tool_manager=None,
    #     session_id: str | None = None,
    #     image_urls: list[str] | None = None,
    #     contexts: list | None = None,
    #     system_prompt: str = "",
    #     conversation: Conversation | None = None,
    # ) -> ProviderRequest:
    #     """创建一个 LLM 请求。

    #     Examples:
    #     ```py
    #     yield event.request_llm(prompt="hi")
    #     ```
    #     prompt: 提示词

    #     system_prompt: 系统提示词

    #     session_id: 已经过时，留空即可

    #     image_urls: 可以是 base64:// 或者 http:// 开头的图片链接，也可以是本地图片路径。

    #     contexts: 当指定 contexts 时，将会使用 contexts 作为上下文。如果同时传入了 conversation，将会忽略 conversation。

    #     func_tool_manager: 函数工具管理器，用于调用函数工具。用 self.context.get_llm_tool_manager() 获取。

    #     conversation: 可选。如果指定，将在指定的对话中进行 LLM 请求。对话的人格会被用于 LLM 请求，并且结果将会被记录到对话中。

    #     """
    #     if image_urls is None:
    #         image_urls = []
    #     if contexts is None:
    #         contexts = []
    #     if len(contexts) > 0 and conversation:
    #         conversation = None

    #     return ProviderRequest(
    #         prompt=prompt,
    #         session_id=session_id,
    #         image_urls=image_urls,
    #         func_tool=func_tool_manager,
    #         contexts=contexts,
    #         system_prompt=system_prompt,
    #         conversation=conversation,
    #     )

    async def send(self, message: MessageChain):
        """发送消息到消息平台。

        Args:
            message (MessageChain): 消息链，具体使用方式请参考文档。

        """
        ...

    async def react(self, emoji: str):
        """对消息添加表情回应。

        默认实现为发送一条包含该表情的消息。
        注意：此实现并不一定符合所有平台的原生“表情回应”行为。
        如需支持平台原生的消息反应功能，请在对应平台的子类中重写本方法。
        """
        ...

    async def get_group(self, group_id: str | None = None, **kwargs) -> Group | None:
        """获取一个群聊的数据, 如果不填写 group_id: 如果是私聊消息，返回 None。如果是群聊消息，返回当前群聊的数据。

        适配情况:

        - aiocqhttp(OneBotv11)
        """
