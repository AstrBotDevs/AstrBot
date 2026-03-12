from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .context import Context


@dataclass(slots=True)
class PlainTextResult:
    text: str


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
    ) -> None:
        self.text = text
        self.user_id = user_id
        self.group_id = group_id
        self.platform = platform
        self.session_id = session_id or group_id or user_id or ""
        self.raw = raw or {}
        self._context = context

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        context: "Context | None" = None,
    ) -> "MessageEvent":
        return cls(
            text=str(payload.get("text", "")),
            user_id=payload.get("user_id"),
            group_id=payload.get("group_id"),
            platform=payload.get("platform"),
            session_id=payload.get("session_id"),
            raw=payload,
            context=context,
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
        if self._context is None:
            raise RuntimeError("MessageEvent 未绑定 Context，无法 reply")
        await self._context.platform.send(self.session_id, text)

    def plain_result(self, text: str) -> PlainTextResult:
        return PlainTextResult(text=text)
