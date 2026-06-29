import time
from typing import Any

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import Plain


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
        await self.adapter.send_message_chain_with_incoming(
            incoming_message=self.message_obj.raw_message,
            message_chain=message,
        )
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        if not self.adapter:
            logger.error("钉钉流式消息发送失败: 缺少 adapter")
            return await self._send_streaming_as_plain_text(generator)

        if not getattr(self.adapter, "card_template_id", ""):
            return await self._send_streaming_as_plain_text(generator)

        incoming_message = getattr(self.message_obj, "raw_message", None)
        if incoming_message is None:
            logger.warning("钉钉流式卡片发送失败: 缺少原始消息，回退普通消息")
            return await self._send_streaming_as_plain_text(generator)

        card_token = await self.adapter.create_message_card(
            message_id=getattr(self.message_obj, "message_id", ""),
            incoming_message=incoming_message,
        )
        if not card_token:
            return await self._send_streaming_as_plain_text(generator)

        full_content = ""
        pending_chain = MessageChain()
        last_update_at = 0.0
        update_interval = max(
            0.1,
            getattr(self.adapter, "card_update_interval", 0.35),
        )

        try:
            async for chain in generator:
                for segment in chain.chain:
                    if isinstance(segment, Plain):
                        full_content += segment.text
                    else:
                        pending_chain.chain.append(segment)

                now = time.monotonic()
                if full_content and now - last_update_at >= update_interval:
                    await self.adapter.send_card_message(
                        card_token=card_token,
                        content=full_content,
                        is_final=False,
                    )
                    last_update_at = now
        finally:
            await self.adapter.send_card_message(
                card_token=card_token,
                content=full_content,
                is_final=True,
            )

        if pending_chain.chain:
            await self.send(pending_chain)

        return None

    async def _send_streaming_as_plain_text(self, generator):
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if not buffer:
            return None
        buffer.squash_plain()
        await self.send(buffer)
        return None
