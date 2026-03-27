from __future__ import annotations

import asyncio
import uuid
from typing import TYPE_CHECKING

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

if TYPE_CHECKING:  # pragma: no cover - typing helper
    from .weixin_oc_adapter import WeixinOCAdapter


class WeixinOCMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        platform: WeixinOCAdapter,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.platform = platform
        self._typing_owner_id: str | None = None

    def _get_typing_owner_id(self) -> str:
        if not self._typing_owner_id:
            self._typing_owner_id = uuid.uuid4().hex
        return self._typing_owner_id

    @staticmethod
    def _segment_to_text(segment: BaseMessageComponent) -> str:
        if isinstance(segment, Plain):
            return segment.text
        if isinstance(segment, Image):
            return "[图片]"
        if isinstance(segment, File):
            return f"[文件:{segment.name}]"
        if isinstance(segment, Video):
            return "[视频]"
        if isinstance(segment, Record):
            return "[音频]"
        if isinstance(segment, At):
            return f"@{segment.name or segment.qq}"
        return "[消息]"

    @staticmethod
    def _build_plain_text(message: MessageChain) -> str:
        return "".join(
            WeixinOCMessageEvent._segment_to_text(seg) for seg in message.chain
        )

    async def send(self, message: MessageChain) -> None:
        if not message.chain:
            return
        await self.platform.send_by_session(self.session, message)
        await super().send(message)

    async def send_typing(self) -> None:
        await self.platform.start_typing(
            self.session.session_id,
            self._get_typing_owner_id(),
        )

    async def stop_typing(self) -> None:
        await self.platform.stop_typing(
            self.session.session_id,
            self._get_typing_owner_id(),
        )

    async def send_streaming(self, generator, use_fallback: bool = False):
        if not use_fallback:
            buffer = None
            async for chain in generator:
                if not buffer:
                    buffer = chain
                else:
                    buffer.chain.extend(chain.chain)
            if not buffer:
                return None
            await self.send(buffer)
            return await super().send_streaming(generator, use_fallback)

        buffer = ""
        async for chain in generator:
            if not isinstance(chain, MessageChain):
                continue
            for component in chain.chain:
                if not isinstance(component, Plain):
                    await self.send(MessageChain(chain=[component]))
                    await asyncio.sleep(1.2)
                    continue
                buffer += component.text
        if buffer.strip():
            await self.send(MessageChain([Plain(buffer)]))
        return await super().send_streaming(generator, use_fallback)
