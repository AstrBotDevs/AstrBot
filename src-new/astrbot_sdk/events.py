"""v4 原生事件对象。

顶层 ``MessageEvent`` 保持精简，只承载 v4 运行时真正需要的基础能力。
旧版 ``AstrMessageEvent`` 的便捷方法与结果对象由
``astrbot_sdk.api.event`` 兼容层承接，而不是继续塞回顶层事件类型。
"""

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
        return payload

    async def reply(self, text: str) -> None:
        if self._reply_handler is None:
            raise RuntimeError("MessageEvent 未绑定 reply handler，无法 reply")
        await self._reply_handler(text)

    def bind_reply_handler(self, reply_handler: ReplyHandler) -> None:
        self._reply_handler = reply_handler

    def plain_result(self, text: str) -> PlainTextResult:
        return PlainTextResult(text=text)
