from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot_sdk.errors import InvalidRequest, NotFound
from astrbot_sdk.messages import MessageChain

from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.platform_metadata import PlatformMetadata

from ..convert import to_core_chain

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class _InjectedMessageEvent(AstrMessageEvent):
    """Synthetic event re-injected into the pipeline by a bridged plugin.

    Mirrors cron.events.CronMessageEvent: sends route through the original
    session so replies reach the platform the UMO points at.
    """

    def __init__(
        self,
        *,
        context: Context,
        session: MessageSession,
        platform_meta: PlatformMetadata,
        message_str: str,
        chain: list,
        sender_id: str,
        sender_name: str,
        self_id: str,
        is_wake: bool,
        extras: dict[str, Any],
    ) -> None:
        msg_obj = AstrBotMessage()
        msg_obj.type = session.message_type
        msg_obj.self_id = self_id
        msg_obj.session_id = session.session_id
        msg_obj.message_id = uuid4().hex
        msg_obj.sender = MessageMember(user_id=sender_id, nickname=sender_name)
        msg_obj.message = chain
        msg_obj.message_str = message_str
        msg_obj.raw_message = message_str
        msg_obj.timestamp = int(time.time())

        super().__init__(message_str, msg_obj, platform_meta, session.session_id)
        self.session = session
        self.context_obj = context
        self.is_wake = is_wake
        self.is_at_or_wake_command = is_wake
        self._extras.update(extras)

    async def send(self, message: Any) -> None:
        if message is None:
            return
        await self.context_obj.send_message(self.session, message)
        await super().send(message)


class EventInjectService:
    """Serve the event.inject capability (legacy get_event_queue().put)."""

    capability_id = "event.inject"

    def __init__(self, context: Context) -> None:
        """Initialize the service with the core star context."""
        self._context = context

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Queue one synthetic event onto the Host pipeline."""
        if operation != "inject":
            raise NotFound(f"unknown event.inject operation: {operation}")
        umo = payload.get("umo")
        if not isinstance(umo, str) or not umo:
            raise InvalidRequest("inject requires a umo")
        try:
            session = MessageSession.from_str(umo)
        except (ValueError, TypeError) as exc:
            raise InvalidRequest(f"inject umo is malformed: {umo!r}") from exc
        chain = payload.get("chain")
        if not isinstance(chain, MessageChain):
            raise InvalidRequest("inject requires a message chain")

        platform_meta = None
        for inst in self._context.platform_manager.platform_insts:
            meta = inst.meta()
            if meta.id == session.platform_id:
                platform_meta = meta
                break
        if platform_meta is None:
            platform_meta = PlatformMetadata(
                name="injected",
                description="Plugin-injected event",
                id=session.platform_id,
            )

        message_str = str(payload.get("message_str") or "")
        extras = payload.get("extras")
        self._context._event_queue.put_nowait(
            _InjectedMessageEvent(
                context=self._context,
                session=session,
                platform_meta=platform_meta,
                message_str=message_str,
                chain=to_core_chain(chain),
                sender_id=str(payload.get("sender_id") or ""),
                sender_name=str(payload.get("sender_name") or ""),
                self_id=str(payload.get("self_id") or ""),
                is_wake=bool(payload.get("is_wake", True)),
                extras=extras if isinstance(extras, dict) else {},
            ),
        )
        return {"queued": True}
