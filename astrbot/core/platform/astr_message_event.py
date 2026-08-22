import abc
import asyncio
import hashlib
import os
import re
import uuid
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from time import time
from typing import Any

from astrbot import logger
from astrbot.core.agent.llm_types import ProviderRequest
from astrbot.core.agent.tool import ToolSet
from astrbot.core.auth.models import AuthContext, Resource, Subject
from astrbot.core.conversation_models import Conversation
from astrbot.core.message.components import (
    RPS,
    Anonymous,
    At,
    AtAll,
    BaseMessageComponent,
    Contact,
    Face,
    File,
    FlashTransfer,
    Forward,
    Image,
    Json,
    Location,
    Markdown,
    MFace,
    MiniApp,
    Node,
    Nodes,
    OnlineFile,
    Plain,
    Poke,
    Record,
    Reply,
    Shake,
    Share,
    Video,
    Xml,
)
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.message.qq_face import format_qq_face
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.metrics import MetricsSink
from astrbot.core.utils.task_utils import create_tracked_task
from astrbot.core.utils.trace import TraceSpan

from .astrbot_message import AstrBotMessage, Group
from .message_session import MessageSession
from .platform_metadata import PlatformMetadata
from .route_identity import PlatformRouteIdentity
from .send_result import DeliveryAttempt, PlatformSendResult


class _LazyExtraValue:
    def __init__(self, resolver) -> None:
        self._resolver = resolver
        self._resolved = False
        self._value = None

    def resolve(self) -> Any:
        if not self._resolved:
            self._value = self._resolver()
            self._resolved = True
        return self._value


class AstrMessageEvent(abc.ABC):
    requires_empty_completion = False

    @staticmethod
    def _resolve_route_target_id(
        message_obj: AstrBotMessage,
        message_type: MessageType,
        session_id: str,
    ) -> str:
        if message_type == MessageType.GROUP_MESSAGE:
            group_id = getattr(message_obj, "group_id", "") or ""
            if isinstance(group_id, str) and group_id:
                return group_id
            if group_id:
                return str(group_id)

        if session_id:
            return session_id

        sender = getattr(message_obj, "sender", None)
        sender_id = getattr(sender, "user_id", "")
        if isinstance(sender_id, str):
            return sender_id
        return str(sender_id) if sender_id else ""

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
        # Unknown adapter facts are represented separately; the compatibility
        # role view defaults to the least-privileged identified member.
        self.platform_member_role = "member"
        """Current-session platform fact: owner/admin/member/unknown only."""
        self.platform_role_source = "none"
        self.platform_role_expires_at: datetime | None = None
        self.subject: Subject | None = None
        self.resource: Resource | None = None
        self.auth_context: AuthContext | None = None
        self.is_wake = False
        """是否唤醒(是否通过 WakingStage)"""
        self.is_at_or_wake_command = False
        """是否是 At 机器人或者带有唤醒词或者是私聊(插件注册的事件监听器会让 is_wake 设为 True, 但是不会让这个属性置为 True)"""
        self._extras: dict[str, Any] = {}
        self._force_stopped: bool = False
        """独立的停止标志，不依赖 _result，不会被 clear_result() 重置"""
        message_type = getattr(message_obj, "type", None)
        if not isinstance(message_type, MessageType):
            try:
                message_type = MessageType(str(message_type))
            except ValueError, TypeError, AttributeError:
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
        self.route_identity = PlatformRouteIdentity(
            platform_id=platform_meta.id,
            message_type=message_type,
            target_id=self._resolve_route_target_id(
                message_obj=message_obj,
                message_type=message_type,
                session_id=session_id,
            ),
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
        self._temporary_local_files: list[str] = []
        """Temporary local files created during this event and safe to delete when it finishes."""
        self._background_tasks: set[asyncio.Task] = set()
        """Tasks retained by this event until its owning platform binds them."""
        self._metrics: MetricsSink | None = None
        """Telemetry capability injected by the originating platform."""

        self.plugins_name: list[str] | None = None
        """该事件启用的插件名称列表。None 表示所有插件都启用。空列表表示没有启用任何插件。"""

    @property
    def unified_msg_origin(self) -> str:
        """统一的消息来源字符串。格式为 platform_name:message_type:session_id"""
        return str(self.session)

    def bind_background_tasks(self, task_set: set[asyncio.Task]) -> None:
        """Transfer auxiliary task ownership to the originating platform."""
        if self._background_tasks and self._background_tasks is not task_set:
            task_set.update(self._background_tasks)
        self._background_tasks = task_set

    def bind_metrics(self, metrics: MetricsSink) -> None:
        """Bind telemetry from the platform that owns this event."""

        self._metrics = metrics

    def _schedule_metric(self, *, name: str, **kwargs: Any) -> None:
        """Schedule a metric under this event's bound task owner."""

        metrics = getattr(self, "_metrics", None)
        if metrics is None:
            return
        create_tracked_task(
            self._background_tasks,
            metrics.upload(**kwargs),
            name=name,
        )

    @property
    def route_origin(self) -> str:
        """Immutable transport routing origin string."""
        return self.route_identity.as_origin()

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

    def get_supported_platform_actions(self) -> list[str]:
        """Get proactive platform actions declared by the current adapter."""
        actions = getattr(self.platform_meta, "supported_actions", None)
        if not isinstance(actions, list):
            return []
        return [action for action in actions if isinstance(action, str)]

    def supports_platform_action(self, action_name: str) -> bool:
        """Whether the current event platform declares a proactive action."""
        return action_name in self.get_supported_platform_actions()

    def get_message_str(self) -> str:
        """获取消息字符串。"""
        return self.message_str

    def _outline_chain(self, chain: list[BaseMessageComponent] | None) -> str:
        if not chain:
            return ""

        parts: list[str] = []
        for i in chain:
            if isinstance(i, Plain):
                parts.append(i.text)
            elif isinstance(i, Image):
                parts.append("[图片]")
            elif isinstance(i, Face):
                parts.append(format_qq_face(i.id))
            elif isinstance(i, MFace):
                parts.append(f"[商城表情:{i.summary}]")
            elif isinstance(i, At):
                parts.append(f"[At:{i.qq}]")
            elif isinstance(i, AtAll):
                parts.append("[At:全体成员]")
            elif isinstance(i, Record):
                parts.append("[语音]")
            elif isinstance(i, Video):
                parts.append("[视频]")
            elif isinstance(i, File):
                parts.append(f"[文件:{i.name or 'file'}]")
            elif isinstance(i, OnlineFile):
                parts.append(f"[在线文件:{i.file_name}]")
            elif isinstance(i, FlashTransfer):
                parts.append("[闪传]")
            elif isinstance(i, Poke):
                parts.append("[戳一戳]")
            elif isinstance(i, Share):
                parts.append(f"[分享:{i.title}]")
            elif isinstance(i, Contact):
                parts.append(f"[联系人:{i.sub_type}]")
            elif isinstance(i, Location):
                parts.append("[位置]")
            elif isinstance(i, Json):
                parts.append("[Json]")
            elif isinstance(i, Xml):
                parts.append("[Xml]")
            elif isinstance(i, Markdown):
                parts.append("[Markdown]")
            elif isinstance(i, MiniApp):
                parts.append("[小程序]")
            elif isinstance(i, Anonymous):
                parts.append("[匿名]")
            elif isinstance(i, RPS):
                parts.append("[猜拳]")
            elif isinstance(i, Shake):
                parts.append("[窗口抖动]")
            elif isinstance(i, Forward):
                # 转发消息
                parts.append("[转发消息]")
            elif isinstance(i, Node | Nodes):
                parts.append("[转发节点]")
            elif isinstance(i, Reply):
                # 引用回复
                if i.message_str:
                    parts.append(f"[引用消息({i.sender_nickname}: {i.message_str})]")
                else:
                    parts.append("[引用消息]")
            else:
                parts.append(f"[{i.type}]")
        return " ".join(parts)

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

    def set_lazy_extra(self, key, resolver) -> None:
        """Set an extra value resolved on first access."""
        self._extras[key] = _LazyExtraValue(resolver)

    def _resolve_extra_value(self, key: str, value: Any) -> Any:
        if not isinstance(value, _LazyExtraValue):
            return value
        resolved = value.resolve()
        self._extras[key] = resolved
        return resolved

    def get_extra(self, key: str | None = None, default=None) -> Any:
        """获取额外的信息。"""
        if key is None:
            return {
                extra_key: self._resolve_extra_value(extra_key, extra_value)
                for extra_key, extra_value in list(self._extras.items())
            }
        if key not in self._extras:
            return default
        return self._resolve_extra_value(key, self._extras[key])

    def clear_extra(self) -> None:
        """清除额外的信息。"""
        logger.info(f"清除 {self.get_platform_name()} 的额外信息: {self._extras}")
        self._extras.clear()

    def track_temporary_local_file(self, path: str) -> None:
        if path and path not in self._temporary_local_files:
            self._temporary_local_files.append(path)

    def has_temporary_local_file(self, path: str) -> bool:
        return bool(path) and path in self._temporary_local_files

    def transfer_temporary_local_file(self, path: str) -> bool:
        """Transfer one temporary artifact to another runtime-owned lease."""
        if path not in self._temporary_local_files:
            return False
        self._temporary_local_files.remove(path)
        return True

    def cleanup_temporary_local_files(self) -> None:
        for path in getattr(self.message_obj, "temporary_file_paths", []):
            self.track_temporary_local_file(path)
        paths = list(self._temporary_local_files)
        self._temporary_local_files.clear()
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                logger.warning(
                    "Failed to remove temporary local file %s: %s",
                    path,
                    e,
                )

    def is_private_chat(self) -> bool:
        """是否是私聊。"""
        return self.get_message_type() == MessageType.FRIEND_MESSAGE

    def is_wake_up(self) -> bool:
        """是否是唤醒机器人的事件。"""
        return self.is_wake

    def is_admin(self) -> bool:
        """Return false: authorization now requires an async action decision.

        This compatibility method intentionally cannot turn a platform field
        into an AstrBot control-plane privilege. Plugins should use
        ``event.auth_context`` and ``context.authz.authorize`` instead.
        """

        return False

    def set_platform_member_role(
        self,
        role: str,
        *,
        source: str,
        ttl_seconds: int = 300,
    ) -> None:
        """Attach a normalized, expiring platform membership fact."""

        normalized = role.strip().lower()
        normalized = {
            "owner": "owner",
            "group_owner": "owner",
            "creator": "owner",
            "admin": "admin",
            "administrator": "admin",
            "member": "member",
        }.get(normalized, "unknown")
        self.platform_member_role = normalized
        self.platform_role_source = source if source else "none"
        self.platform_role_expires_at = datetime.now(UTC) + timedelta(
            seconds=max(1, min(ttl_seconds, 3600))
        )

    def attach_authorization(
        self,
        *,
        subject: Subject,
        resource: Resource,
        context: AuthContext,
    ) -> None:
        """Install the pipeline-owned authorization values for this event."""

        self.subject = subject
        self.resource = resource
        self.auth_context = context

    def _success_send_result(
        self,
        *,
        target: str | None = None,
        message_count: int = 0,
    ) -> PlatformSendResult:
        return PlatformSendResult(
            platform_id=self.get_platform_id(),
            success=True,
            target=target or self.route_identity.target_id,
            message_count=message_count,
        )

    def _failure_send_result(
        self,
        error_message: str,
        *,
        target: str | None = None,
        message_count: int = 0,
    ) -> PlatformSendResult:
        return PlatformSendResult(
            platform_id=self.get_platform_id(),
            success=False,
            target=target or self.route_identity.target_id,
            message_count=message_count,
            error_message=error_message,
        )

    async def process_buffer(self, buffer: str, pattern: re.Pattern) -> str:
        """将消息缓冲区中的文本按指定正则表达式分割后发送至消息平台，作为不支持流式输出平台的Fallback。"""
        while True:
            match = re.search(pattern, buffer)
            if not match:
                break
            matched_text = match.group().strip()
            if matched_text:
                await self.send(MessageChain([Plain(matched_text)]))
                await asyncio.sleep(1.5)  # 限速
            buffer = buffer[match.end() :]
        return buffer

    @staticmethod
    def _history_semantic_text(chain: MessageChain) -> str:
        """Return local semantic text for a submitted streaming fragment."""
        text_parts: list[str] = []
        for component in chain.chain:
            if isinstance(component, (At, AtAll, Reply)):
                continue
            if isinstance(component, Plain) and component.text:
                text_parts.append(component.text)
            elif isinstance(component, Markdown) and component.content:
                text_parts.append(component.content)
        return "".join(text_parts)

    async def _send_streaming_fragment(
        self,
        chain: MessageChain,
    ) -> DeliveryAttempt:
        """Submit one fallback fragment and retain its explicit transport outcome."""
        semantic_text = self._history_semantic_text(chain)
        try:
            result = await self.send(chain)
        except asyncio.CancelledError:
            raise
        except Exception:
            return DeliveryAttempt(
                status="unknown",
                semantic_text=semantic_text,
                error_summary="platform streaming submission outcome unknown",
            )
        if not isinstance(result, PlatformSendResult):
            return DeliveryAttempt(
                status="unknown",
                semantic_text=semantic_text,
                error_summary="platform did not return an acceptance receipt",
            )
        return result.to_delivery_attempt(semantic_text=semantic_text)

    async def _streaming_result_from_attempts(
        self,
        attempts: list[DeliveryAttempt],
        generator: AsyncGenerator[MessageChain],
        use_fallback: bool,
    ) -> PlatformSendResult | None:
        """Record stream metrics and return a receipt-backed compatibility result."""
        recorded = await AstrMessageEvent.send_streaming(
            self,
            generator,
            use_fallback,
        )
        if not isinstance(recorded, PlatformSendResult):
            # Preserve adapter/test overrides of the old metrics-only helper.
            return recorded
        return PlatformSendResult.from_delivery_attempts(
            attempts,
            platform_id=self.get_platform_id(),
            target=self.route_identity.target_id,
        )

    async def _send_buffered_streaming_response(
        self,
        generator: AsyncGenerator[MessageChain],
        use_fallback: bool = False,
        *,
        record_empty: bool = False,
    ) -> PlatformSendResult | None:
        """Buffer a stream into one message while preserving component order.

        This is for adapters whose streaming fallback must submit the complete
        message in one request. It deliberately does not use
        :meth:`send_non_streaming_response`: that method may flush media before
        later text when ``use_fallback`` is enabled.
        """
        message_buffer: MessageChain | None = None
        async for chain in generator:
            if message_buffer is None:
                message_buffer = chain
            else:
                message_buffer.chain.extend(chain.chain)

        if message_buffer is None:
            if record_empty:
                return await AstrMessageEvent.send_streaming(
                    self, generator, use_fallback
                )
            return None

        message_buffer.squash_plain()
        attempt = await self._send_streaming_fragment(message_buffer)
        return await self._streaming_result_from_attempts(
            [attempt],
            generator,
            use_fallback,
        )

    async def send_non_streaming_response(
        self,
        generator: AsyncGenerator[MessageChain],
        *,
        use_fallback: bool,
        sentence_pattern: re.Pattern | None = None,
        component_delay: float = 1.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        record_empty: bool = False,
    ) -> PlatformSendResult | None:
        """Consume a non-native stream once and send its ordinary message parts.

        Adapters use this for platforms without a native streaming protocol. The
        adapter-specific ``send`` method remains responsible for transport and
        rate limits; this shared path only owns stream consumption and metrics.
        """
        if not use_fallback:
            return await self._send_buffered_streaming_response(
                generator,
                use_fallback,
                record_empty=record_empty,
            )

        text_buffer = ""
        attempts: list[DeliveryAttempt] = []
        for_sentence_flush = sentence_pattern is not None

        async def send_text(text: str) -> None:
            if not text:
                return
            attempts.append(
                await self._send_streaming_fragment(MessageChain([Plain(text)])),
            )

        async for chain in generator:
            if not isinstance(chain, MessageChain):
                continue
            for component in chain.chain:
                if isinstance(component, Plain):
                    text_buffer += component.text
                    if for_sentence_flush and sentence_pattern is not None:
                        while match := sentence_pattern.search(text_buffer):
                            matched_text = match.group().strip()
                            if matched_text:
                                await send_text(matched_text)
                                await sleep(component_delay)
                            text_buffer = text_buffer[match.end() :]
                else:
                    attempts.append(
                        await self._send_streaming_fragment(
                            MessageChain(chain=[component]),
                        ),
                    )
                    await sleep(component_delay)

        if text_buffer.strip():
            await send_text(text_buffer.strip())
        if not attempts:
            if record_empty:
                return await AstrMessageEvent.send_streaming(
                    self,
                    generator,
                    use_fallback,
                )
            return None
        return await self._streaming_result_from_attempts(
            attempts,
            generator,
            use_fallback,
        )

    async def _record_streaming_send(self) -> PlatformSendResult:
        """Record exactly one successful logical streaming response."""
        self._schedule_metric(
            name=f"metric:stream:{self.platform_meta.name}",
            msg_event_tick=1,
            adapter_name=self.platform_meta.name,
        )
        self._has_send_oper = True
        return self._success_send_result()

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain],
        use_fallback: bool = False,
    ) -> PlatformSendResult | None:
        """发送流式消息到消息平台，使用异步生成器。
        目前仅支持: telegram，qq official 私聊。
        Fallback仅支持 aiocqhttp。
        """
        return await self._record_streaming_send()

    async def send_typing(self) -> None:
        """发送输入中状态。

        默认实现为空，由具体平台按需重写。
        """

    async def stop_typing(self) -> None:
        """停止输入中状态。

        默认实现为空，由具体平台按需重写。
        """

    async def _pre_send(self) -> None:
        """Reserved send hook for platform overrides."""

    async def _post_send(self) -> PlatformSendResult | None:
        """Reserved post-send hook for platform overrides."""

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
        self._force_stopped = True
        if self._result is None:
            self.set_result(MessageEventResult().stop_event())
        else:
            self._result.stop_event()

    def continue_event(self) -> None:
        """继续事件传播。"""
        self._force_stopped = False
        if self._result is None:
            self.set_result(MessageEventResult().continue_event())
        else:
            self._result.continue_event()

    def is_stopped(self) -> bool:
        """是否终止事件传播。"""
        if self._force_stopped:
            return True
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
        tool_set: ToolSet | None = None,
        session_id: str = "",
        image_urls: list[str] | None = None,
        audio_urls: list[str] | None = None,
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

        audio_urls: 音频 URL 列表，也支持本地路径。

        contexts: 当指定 contexts 时，将会使用 contexts 作为上下文。如果同时传入了 conversation，将会忽略 conversation。

        conversation: 可选。如果指定，将在指定的对话中进行 LLM 请求。对话的人格会被用于 LLM 请求，并且结果将会被记录到对话中。

        """
        if image_urls is None:
            image_urls = []
        if audio_urls is None:
            audio_urls = []
        if contexts is None:
            contexts = []
        if len(contexts) > 0 and conversation:
            conversation = None

        return ProviderRequest(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            audio_urls=audio_urls,
            func_tool=tool_set,
            contexts=contexts,
            system_prompt=system_prompt,
            conversation=conversation,
        )

    """平台适配器"""

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        """发送消息到消息平台。

        Args:
            message (MessageChain): 消息链，具体使用方式请参考文档。

        """
        from astrbot.core.group_sender_concurrency import (
            current_concurrent_turn,
        )

        turn = current_concurrent_turn()
        gate = self.get_extra("_group_outbound_gate")
        umo = self.get_extra("_group_outbound_umo")
        if turn is not None:
            await turn.gate.hold_turn(turn.umo, turn.event)
        elif gate is not None and umo:
            await gate.hold_turn(umo, self)

        # Leverage BLAKE2 hash function to generate a non-reversible hash of the sender ID for privacy.
        hash_obj = hashlib.blake2b(self.get_sender_id().encode("utf-8"), digest_size=16)
        sid = str(uuid.UUID(bytes=hash_obj.digest()))
        self._schedule_metric(
            name=f"metric:send:{self.platform_meta.name}",
            msg_event_tick=1,
            adapter_name=self.platform_meta.name,
            sid=sid,
        )
        self._has_send_oper = True
        return self._success_send_result(message_count=len(message.chain))

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
