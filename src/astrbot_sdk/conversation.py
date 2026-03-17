from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .context import Context
from .events import MessageEvent
from .message_components import BaseMessageComponent
from .message_result import MessageChain
from .session_waiter import SessionWaiterManager

DEFAULT_BUSY_MESSAGE = "当前会话已有进行中的交互，请先完成后再试。"


class ConversationState(str, Enum):
    ACTIVE = "active"
    REJECTED_BUSY = "rejected_busy"
    REPLACED = "replaced"
    TIMEOUT = "timeout"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ConversationReplaced(RuntimeError):
    pass


class ConversationClosed(RuntimeError):
    pass


@dataclass(slots=True)
class ConversationSession:
    ctx: Context
    event: MessageEvent
    waiter_manager: SessionWaiterManager
    timeout: int
    state: ConversationState = ConversationState.ACTIVE
    _owner_task: asyncio.Task[Any] | None = None

    def __post_init__(self) -> None:
        if self.state != ConversationState.ACTIVE:
            self.state = ConversationState.ACTIVE

    def bind_owner_task(self, task: asyncio.Task[Any]) -> None:
        self._owner_task = task

    @property
    def session_key(self) -> str:
        return self.event.unified_msg_origin

    @property
    def active(self) -> bool:
        return self.state == ConversationState.ACTIVE

    async def ask(self, prompt: str, timeout: int | None = None) -> MessageEvent:
        self._ensure_usable("ask")
        if prompt:
            await self.reply(prompt)
        try:
            return await self.waiter_manager.wait_for_event(
                event=self.event,
                timeout=timeout or self.timeout,
                record_history_chains=False,
            )
        except asyncio.TimeoutError:
            self.close(ConversationState.TIMEOUT)
            raise
        except asyncio.CancelledError as exc:
            if self.state == ConversationState.REPLACED:
                raise ConversationReplaced(
                    "conversation replaced by a newer session"
                ) from exc
            self.close(ConversationState.CANCELLED)
            raise

    async def reply(self, text: str) -> None:
        self._ensure_usable("reply")
        await self.event.reply(text)

    async def reply_chain(
        self,
        chain: MessageChain | list[BaseMessageComponent] | list[dict[str, Any]],
    ) -> None:
        self._ensure_usable("reply_chain")
        await self.event.reply_chain(chain)

    async def send_message(
        self,
        content: str | MessageChain | list[BaseMessageComponent] | list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._ensure_usable("send_message")
        return await self.ctx.platform.send_by_session(self.event.session_id, content)

    def end(self) -> None:
        self.close(ConversationState.COMPLETED)

    def mark_replaced(self) -> None:
        self.close(ConversationState.REPLACED)

    def close(self, state: ConversationState) -> None:
        if self.state != ConversationState.ACTIVE and state == self.state:
            return
        if (
            self.state != ConversationState.ACTIVE
            and state != ConversationState.REPLACED
        ):
            return
        self.state = state

    def _ensure_usable(self, action: str) -> None:
        if (
            self._owner_task is not None
            and asyncio.current_task() is not self._owner_task
        ):
            raise ConversationClosed(
                f"ConversationSession cannot be used outside its owner task during {action}"
            )
        if not self.active:
            raise ConversationClosed(
                f"ConversationSession is already closed ({self.state.value}) during {action}"
            )


__all__ = [
    "ConversationClosed",
    "ConversationReplaced",
    "ConversationSession",
    "ConversationState",
    "DEFAULT_BUSY_MESSAGE",
]
