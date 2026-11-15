"""Events for programmatic main-agent wakeups targeting an existing session."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Literal

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    streaming_response_event,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.platform_metadata import PlatformMetadata

if TYPE_CHECKING:
    from astrbot.core.agent.runtime import AgentSessionRef
    from astrbot.core.star.context import Context

WakeupSource = Literal["cron", "background_task", "plugin"]


class AgentWakeupEvent(AstrMessageEvent):
    """Adapt a programmatic user turn to the existing message-event interface."""

    event_kind = "agent_wakeup"
    trace_name = "AgentWakeupEvent"

    def __init__(
        self,
        *,
        context: Context,
        session: MessageSession,
        platform_meta: PlatformMetadata,
        prompt: str,
        source: WakeupSource,
        source_id: str | None = None,
        role: str = "member",
        agent_session: AgentSessionRef | None = None,
    ) -> None:
        """Create a wakeup without changing the target session's identity.

        Args:
            context: Services used to deliver messages to the target session.
            session: Session whose current conversation will receive the turn.
            platform_meta: Target platform metadata, resolved before construction.
            prompt: Current user input, including any trigger instructions.
            source: Mechanism that triggered the turn, independent of its platform.
            source_id: Cron job ID, background task ID, or invoking plugin ID.
            role: Caller permission role already resolved by the framework.
            agent_session: Explicit runtime conversation, independent of UMO selection.

        Raises:
            ValueError: If the source or target platform identity is invalid.
        """
        if source not in ("cron", "background_task", "plugin"):
            raise ValueError(f"Unsupported agent wakeup source: {source!r}")
        if platform_meta.id != session.platform_id:
            raise ValueError("Wakeup platform metadata must match the target session.")
        self.source = source
        self.source_id = source_id
        self.agent_session = agent_session

        message = AstrBotMessage()
        message.type = session.message_type
        message.self_id = ""
        message.session_id = session.session_id
        message.message_id = uuid.uuid4().hex
        message.sender = MessageMember(user_id="astrbot", nickname="System")
        message.message = [Plain(prompt)]
        message.message_str = prompt
        message.raw_message = prompt

        metadata: dict[str, str] = {"source": source}
        if source_id is not None:
            metadata["source_id"] = source_id
        super().__init__(
            prompt,
            message,
            platform_meta,
            session.session_id,
            event_metadata=metadata,
        )
        self.session = session
        self.context_obj = context
        self.role = role
        self.is_at_or_wake_command = True
        self.is_wake = True
        # The supplied UMO is already the final target, including any isolation.
        self.set_extra("_session_resolved", True)
        self.set_extra("_role_resolved", True)
        self.set_extra("enable_streaming", False)

    async def send(self, message: MessageChain) -> None:
        """Deliver through the target session and account only for successful sends.

        Args:
            message: Message chain to deliver.
        """
        if message is None:
            return
        # The outer event.send records delivery; suppress its nested public send.
        token = streaming_response_event.set(self)
        try:
            sent = await self.context_obj.send_message(self.session, message)
        finally:
            streaming_response_event.reset(token)
        if sent:
            await super().send(message)

    async def send_streaming(
        self, generator: AsyncGenerator[MessageChain, None], use_fallback: bool = False
    ) -> None:
        """Buffer streaming output and deliver it as one complete message.

        Args:
            generator: Stream of message chains to deliver.
            use_fallback: Compatibility argument; wakeups always buffer the stream.
        """
        buffer: MessageChain | None = None
        async for chain in generator:
            if not chain.chain:
                continue
            if buffer is None:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if buffer is not None:
            buffer.squash_plain()
            await self.send(buffer)
