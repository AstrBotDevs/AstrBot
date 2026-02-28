from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import At, Image, Plain, Reply

if TYPE_CHECKING:
    from .heihe_adapter import HeihePlatformAdapter


class HeiheMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj,
        platform_meta,
        session_id: str,
        adapter: "HeihePlatformAdapter",
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter

    @classmethod
    async def send_with_adapter(
        cls,
        adapter: "HeihePlatformAdapter",
        message: MessageChain,
        session_id: str,
    ) -> None:
        payload = await cls._build_send_payload(message, session_id)
        await adapter.send_payload(payload)

    async def send(self, message: MessageChain) -> None:
        await self.send_with_adapter(self.adapter, message, self.session_id)
        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ):
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
        return await super().send_streaming(generator, use_fallback)

    @classmethod
    async def _build_send_payload(
        cls,
        message: MessageChain,
        session_id: str,
    ) -> dict[str, Any]:
        text_parts: list[str] = []
        segments: list[dict[str, Any]] = []

        for component in message.chain:
            if isinstance(component, Plain):
                if component.text:
                    text_parts.append(component.text)
                    segments.append({"type": "text", "text": component.text})
                continue

            if isinstance(component, At):
                at_name = str(component.name or component.qq or "").strip()
                if at_name:
                    text_parts.append(f"@{at_name}")
                    segments.append(
                        {
                            "type": "mention",
                            "user_id": str(component.qq or ""),
                            "name": at_name,
                        },
                    )
                continue

            if isinstance(component, Reply):
                if component.id:
                    segments.append({"type": "reply", "message_id": component.id})
                continue

            if isinstance(component, Image):
                image_url = ""
                try:
                    image_url = await component.register_to_file_service()
                except Exception as e:
                    logger.debug("[heihe] image upload fallback failed: %s", e)

                if image_url:
                    segments.append({"type": "image", "url": image_url})
                    text_parts.append("[image]")
                continue

        content = "".join(text_parts).strip()
        payload: dict[str, Any] = {
            "action": "send_message",
            "channel_id": session_id,
            "content": content,
            "segments": segments,
        }
        return payload
