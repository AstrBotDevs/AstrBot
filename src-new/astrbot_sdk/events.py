"""v4 原生事件对象。

顶层 ``MessageEvent`` 保持精简，只承载 v4 运行时真正需要的基础能力。
迁移期扩展事件能力放在独立模块中，而不是继续塞回顶层事件类型。

MessageEvent 是 handler 接收的主要事件类型，封装了：
    - 消息文本内容
    - 发送者信息（user_id, group_id）
    - 平台标识
    - 回复能力（reply, reply_image, reply_chain）
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .protocol.descriptors import SessionRef

if TYPE_CHECKING:
    from .context import Context


@dataclass(slots=True)
class PlainTextResult:
    """纯文本结果。

    用于 handler 返回简单的文本结果。
    """

    text: str


ReplyHandler = Callable[[str], Awaitable[None]]


class MessageEvent:
    """消息事件对象。

    封装收到的消息，提供便捷的回复方法。
    每个 handler 调用都会创建新的 MessageEvent 实例。

    Attributes:
        text: 消息文本内容
        user_id: 发送者用户 ID
        group_id: 群组 ID（私聊时为 None）
        platform: 平台标识（如 "qq", "wechat"）
        session_id: 会话 ID（通常是 group_id 或 user_id）
        raw: 原始消息数据

    Example:
        @on_command("echo")
        async def echo(self, event: MessageEvent, ctx: Context):
            await event.reply(f"你说: {event.text}")
    """

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
        """初始化消息事件。

        Args:
            text: 消息文本
            user_id: 用户 ID
            group_id: 群组 ID
            platform: 平台标识
            session_id: 会话 ID，None 时自动从 group_id/user_id 推断
            raw: 原始消息数据
            context: 运行时上下文
            reply_handler: 自定义回复处理器
        """
        self.text = text
        self.user_id = user_id
        self.group_id = group_id
        self.platform = platform
        self.session_id = session_id or group_id or user_id or ""
        self.raw = raw or {}
        self._context = context
        self._reply_handler = reply_handler
        if self._reply_handler is None and context is not None:
            self._reply_handler = lambda text: context.platform.send(
                self.session_ref or self.session_id,
                text,
            )

    def _require_runtime_context(self, action: str) -> "Context":
        """获取运行时上下文，不存在则抛出异常。"""
        if self._context is None:
            raise RuntimeError(f"MessageEvent 未绑定运行时上下文，无法 {action}")
        return self._context

    def _reply_target(self) -> SessionRef | str:
        """获取回复目标。"""
        return self.session_ref or self.session_id

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        context: "Context | None" = None,
        reply_handler: ReplyHandler | None = None,
    ) -> "MessageEvent":
        """从协议载荷创建事件实例。

        Args:
            payload: 协议层传递的消息数据
            context: 运行时上下文
            reply_handler: 自定义回复处理器

        Returns:
            新的 MessageEvent 实例
        """
        target_payload = payload.get("target")
        session_id = payload.get("session_id")
        platform = payload.get("platform")
        if isinstance(target_payload, dict):
            target = SessionRef.model_validate(target_payload)
            session_id = session_id or target.session
            platform = platform or target.platform
        return cls(
            text=str(payload.get("text", "")),
            user_id=payload.get("user_id"),
            group_id=payload.get("group_id"),
            platform=platform,
            session_id=session_id,
            raw=payload,
            context=context,
            reply_handler=reply_handler,
        )

    def to_payload(self) -> dict[str, Any]:
        """转换为协议载荷格式。

        Returns:
            可序列化的字典
        """
        payload = dict(self.raw)
        payload.update(
            {
                "text": self.text,
                "user_id": self.user_id,
                "group_id": self.group_id,
                "platform": self.platform,
                "session_id": self.session_id,
            }
        )
        if self.session_ref is not None:
            payload["target"] = self.session_ref.to_payload()
        return payload

    @property
    def session_ref(self) -> SessionRef | None:
        """获取会话引用对象。

        Returns:
            SessionRef 实例，如果没有有效的 session_id 则返回 None
        """
        if not self.session_id:
            return None
        return SessionRef(
            conversation_id=self.session_id,
            platform=self.platform,
            raw=self.raw or None,
        )

    @property
    def target(self) -> SessionRef | None:
        """session_ref 的别名。"""
        return self.session_ref

    async def reply(self, text: str) -> None:
        """回复文本消息。

        Args:
            text: 要回复的文本内容

        Raises:
            RuntimeError: 如果未绑定 reply handler
        """
        if self._reply_handler is None:
            raise RuntimeError("MessageEvent 未绑定 reply handler，无法 reply")
        await self._reply_handler(text)

    async def reply_image(self, image_url: str) -> None:
        """回复图片消息。

        Args:
            image_url: 图片 URL

        Raises:
            RuntimeError: 如果未绑定运行时上下文
        """
        context = self._require_runtime_context("reply_image")
        await context.platform.send_image(self._reply_target(), image_url)

    async def reply_chain(self, chain: list[dict[str, Any]]) -> None:
        """回复消息链（多类型消息组合）。

        Args:
            chain: 消息链组件列表

        Raises:
            RuntimeError: 如果未绑定运行时上下文
        """
        context = self._require_runtime_context("reply_chain")
        await context.platform.send_chain(self._reply_target(), chain)

    def bind_reply_handler(self, reply_handler: ReplyHandler) -> None:
        """绑定自定义回复处理器。

        Args:
            reply_handler: 回复处理函数
        """
        self._reply_handler = reply_handler

    def plain_result(self, text: str) -> PlainTextResult:
        """创建纯文本结果。

        Args:
            text: 结果文本

        Returns:
            PlainTextResult 实例
        """
        return PlainTextResult(text=text)
