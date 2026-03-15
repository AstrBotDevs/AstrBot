from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import AstrBotMessage, PlatformMetadata

if TYPE_CHECKING:
    from .weibo_adapter import WeiboPlatformAdapter


class WeiboMessageEvent(AstrMessageEvent):
    """AstrBot event wrapper for inbound Weibo direct messages."""

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        adapter: WeiboPlatformAdapter,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._adapter = adapter

    async def send(self, message: MessageChain) -> None:
        await self._adapter.send_message_chain(self.get_sender_id(), message)
        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ) -> None:
        await super().send_streaming(generator, use_fallback=use_fallback)

        buffer_parts: list[str] = []
        async for chain in generator:
            rendered = await self._adapter._render_message_chain(chain)
            if rendered:
                buffer_parts.append(rendered)

        final_text = "".join(buffer_parts).strip()
        if final_text:
            await self._adapter.send_message_chain(
                self.get_sender_id(),
                MessageChain().message(final_text),
            )
