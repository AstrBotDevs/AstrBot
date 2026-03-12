# =============================================================================
# 新旧对比 - events.py
# =============================================================================
#
# 【旧版 src/astrbot_sdk/api/event/】
# 包含多个文件：
# - astr_message_event.py: AstrMessageEvent 类（约 370 行）
# - astrbot_message.py: AstrBotMessage 消息对象
# - event_result.py: MessageEventResult 事件结果
# - event_type.py: EventType 枚举
# - message_session.py: MessageSession 会话
# - message_type.py: MessageType 枚举
#
# 【新版 src-new/astrbot_sdk/events.py】
# 仅包含:
# - MessageEvent: 简化的消息事件类
# - PlainTextResult: 纯文本结果数据类
#
# =============================================================================
# TODO: 功能缺失
# =============================================================================
#
# 1. AstrMessageEvent 大量功能缺失
#    - 属性缺失:
#      - message_obj: AstrBotMessage 消息对象
#      - platform_meta: PlatformMetadata 平台元信息
#      - role: "admin" | "member" 角色
#      - is_wake, is_at_or_wake_command: 唤醒状态
#      - session, unified_msg_origin: 会话标识
#
#    - 方法缺失:
#      - get_platform_name(), get_platform_id(): 平台信息
#      - get_messages(): 获取消息链
#      - get_message_type(): 获取消息类型
#      - get_group_id(), get_self_id(), get_sender_id(), get_sender_name(): ID 获取
#      - set_extra(), get_extra(), clear_extra(): 额外信息存储
#      - is_private_chat(), is_wake_up(), is_admin(): 状态判断
#      - set_result(), stop_event(), continue_event(), is_stopped(): 事件控制
#      - should_call_llm(), get_result(), clear_result(): LLM 控制
#      - make_result(), plain_result(), image_result(), chain_result(): 结果构建
#      - send(), react(), get_group(): 消息操作
#
# 2. 缺少关联类型
#    - AstrBotMessage: 消息对象（包含 sender, message, type 等）
#    - MessageEventResult: 事件结果（包含 chain, result_type 等）
#    - MessageSession: 会话标识
#    - MessageType: 消息类型枚举 (FRIEND_MESSAGE, GROUP_MESSAGE 等)
#    - PlatformMetadata: 平台元信息
#
# 3. 新版 MessageEvent 特性
#    - 简化设计，仅包含核心属性: text, user_id, group_id, platform, session_id
#    - 通过 reply_handler 实现回复功能
#    - 支持从 payload 构建: from_payload()
#    - 支持序列化: to_payload()
#
# =============================================================================

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .context import Context


@dataclass(slots=True)
class PlainTextResult:
    text: str


ReplyHandler = Callable[[str], Awaitable[None]]


class MessageEvent:
    def __init__(
        self,
        *,
        text: str = "",
        user_id: str | None = None,
        group_id: str | None = None,
        platform: str | None = None,
        session_id: str | None = None,
        raw: dict[str, Any] | None = None,
        context: "Context | None" = None,
        reply_handler: ReplyHandler | None = None,
    ) -> None:
        self.text = text
        self.user_id = user_id
        self.group_id = group_id
        self.platform = platform
        self.session_id = session_id or group_id or user_id or ""
        self.raw = raw or {}
        self._reply_handler = reply_handler
        if self._reply_handler is None and context is not None:
            self._reply_handler = lambda text: context.platform.send(
                self.session_id, text
            )

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        context: "Context | None" = None,
        reply_handler: ReplyHandler | None = None,
    ) -> "MessageEvent":
        return cls(
            text=str(payload.get("text", "")),
            user_id=payload.get("user_id"),
            group_id=payload.get("group_id"),
            platform=payload.get("platform"),
            session_id=payload.get("session_id"),
            raw=payload,
            context=context,
            reply_handler=reply_handler,
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "platform": self.platform,
            "session_id": self.session_id,
        }

    async def reply(self, text: str) -> None:
        if self._reply_handler is None:
            raise RuntimeError("MessageEvent 未绑定 reply handler，无法 reply")
        await self._reply_handler(text)

    def bind_reply_handler(self, reply_handler: ReplyHandler) -> None:
        self._reply_handler = reply_handler

    def plain_result(self, text: str) -> PlainTextResult:
        return PlainTextResult(text=text)
