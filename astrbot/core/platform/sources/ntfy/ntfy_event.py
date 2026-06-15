import asyncio
import os
import re
from collections.abc import AsyncGenerator
from typing import Any, Optional

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    At,
    BaseMessageComponent,
    File,
    Image,
    Plain,
    Record,
    Video,
)
from .ntfy_api import NtfyAPIClient


class NtfyMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str: str,
        message_obj: Any,
        platform_meta: Any,
        session_id: str,
        ntfy_api: NtfyAPIClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.ntfy_api = ntfy_api

    async def send(self, message: MessageChain) -> None:
        """Dispatches rich content payloads or raw fallback string configurations."""
        text_payload = ""
        file_component: Optional[BaseMessageComponent] = None

        for segment in message.chain:
            if isinstance(segment, Plain):
                text_payload += segment.text
            elif isinstance(segment, At):
                name = str(segment.name or segment.qq or "").strip()
                if name:
                    text_payload += f" @{name} "
            elif isinstance(segment, (Image, File, Video, Record)):
                file_component = segment

        if file_component:
            try:
                file_path = await file_component.convert_to_file_path()
                if file_path and os.path.exists(file_path):
                    filename = getattr(
                        file_component, "name", None
                    ) or os.path.basename(file_path)
                    with open(file_path, "rb") as f:
                        file_bytes = f.read()

                    await self.ntfy_api.send_file(
                        file_bytes=file_bytes,
                        filename=filename,
                        message=text_payload.strip() if text_payload else None,
                    )
                    await super().send(message)
                    return
            except Exception as e:
                logger.error(
                    "[ntfy-event] Failed resolving attachment binary sequence: %s", e
                )

        if text_payload.strip():
            await self.ntfy_api.send_notification(text_payload.strip())

        await super().send(message)

    async def send_streaming(
        self,
        generator: AsyncGenerator,
        use_fallback: bool = False,
    ) -> Any:
        """Pipes live execution generator data using a structured pattern tokenizer buffer."""
        if not use_fallback:
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

        buffer = ""
        pattern = re.compile(r"[^。？！~…]+[。？！~…]+")

        async for chain in generator:
            if isinstance(chain, MessageChain):
                for comp in chain.chain:
                    if isinstance(comp, Plain):
                        buffer += comp.text
                        if any(p in buffer for p in "。？！~…"):
                            buffer = await self.process_buffer(buffer, pattern)
                    else:
                        await self.send(MessageChain(chain=[comp]))
                        await asyncio.sleep(1.5)

        if buffer.strip():
            await self.send(MessageChain([Plain(buffer)]))
        return await super().send_streaming(generator, use_fallback)

    async def process_buffer(self, buffer: str, pattern: re.Pattern) -> str:
        matches = pattern.findall(buffer)
        if matches:
            for match in matches:
                await self.send(MessageChain([Plain(match)]))
                await asyncio.sleep(1.0)
            return pattern.sub("", buffer)
        return buffer
