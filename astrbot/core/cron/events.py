import time
import uuid
from typing import Any

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.send_result import PlatformSendResult


class CronMessageEvent(AstrMessageEvent):
    """Synthetic event used when a cron job triggers the main agent loop."""

    def __init__(
        self,
        *,
        context,
        session: MessageSession,
        message: str,
        sender_id: str = "astrbot",
        sender_name: str = "Scheduler",
        extras: dict[str, Any] | None = None,
        message_type: MessageType = MessageType.FRIEND_MESSAGE,
    ) -> None:
        platform_meta = PlatformMetadata(
            name="cron",
            description="CronJob",
            id=session.platform_id,
        )

        msg_obj = AstrBotMessage()
        msg_obj.type = message_type
        msg_obj.self_id = sender_id
        msg_obj.session_id = session.session_id
        msg_obj.message_id = uuid.uuid4().hex
        msg_obj.sender = MessageMember(user_id=session.session_id, nickname=sender_name)
        msg_obj.message = [Plain(message)]
        msg_obj.message_str = message
        msg_obj.raw_message = message
        msg_obj.timestamp = int(time.time())

        super().__init__(message, msg_obj, platform_meta, session.session_id)

        # Ensure we use the original session for sending messages
        self.session = session
        self.context_obj = context
        self.set_extra("adapter_preconfigured", True)

        if extras:
            self._extras.update(extras)

    async def send(self, message: MessageChain) -> PlatformSendResult:
        if message is None:
            return self._success_send_result(message_count=0)
        send_result = await self.context_obj.send_message(self.session, message)
        await super().send(message)
        return send_result

    async def send_streaming(
        self, generator, use_fallback: bool = False
    ) -> PlatformSendResult:
        last_result = self._success_send_result(message_count=0)
        async for chain in generator:
            last_result = await self.send(chain)
        return last_result


__all__ = ["CronMessageEvent"]
