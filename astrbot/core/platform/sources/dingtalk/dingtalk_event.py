from typing import Any

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.platform.astr_message_event import MessageSesion


class DingtalkMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        client: Any = None,
        adapter: "Any" = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client
        self.adapter = adapter

    async def send(self, message: MessageChain) -> None:
        if not self.adapter:
            logger.error("钉钉消息发送失败: 缺少 adapter")
            return
        raw_message = self.message_obj.raw_message
        if hasattr(raw_message, "conversation_type"):
            await self.adapter.send_message_chain_with_incoming(
                incoming_message=raw_message,
                message_chain=message,
            )
        else:
            await self.adapter.send_by_session(
                MessageSesion(
                    platform_name=self.platform_meta.id,
                    message_type=self.get_message_type(),
                    session_id=self.session_id,
                ),
                message,
            )
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        return await self._send_buffered_stream(
            generator, use_fallback, super().send_streaming
        )
