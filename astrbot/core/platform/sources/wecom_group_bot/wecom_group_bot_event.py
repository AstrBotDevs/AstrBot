"""企业微信消息推送机器人（原群机器人）事件"""

from __future__ import annotations

from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import At, Image, Plain

from .wecom_group_bot_client import WecomGroupBotClient


class WecomGroupBotEvent(AstrMessageEvent):
    """封装消息推送机器人的回复能力"""

    def __init__(
        self,
        message_str: str,
        message_obj,
        platform_meta,
        session_id: str,
        client: WecomGroupBotClient,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.client = client

    async def send(self, message: MessageChain):
        webhook_url = self._extract_webhook()
        if not webhook_url:
            logger.warning("缺少 webhook_url，无法向企业微信消息推送机器人（原群机器人）发送消息")
            return

        chat_id = self._extract_chat_id()
        mentioned_list: list[str] = []
        plain_segments: list[str] = []
        image_components: list[Image] = []

        for comp in message.chain:
            if isinstance(comp, Plain):
                plain_segments.append(comp.text)
            elif isinstance(comp, At):
                target = str(comp.qq)
                plain_segments.append(f"<@{target}>")
                mentioned_list.append(target)
            elif isinstance(comp, Image):
                image_components.append(comp)
            else:
                logger.warning("暂未支持的消息组件类型: %s", comp.type)

        if plain_segments:
            await self.client.send_plain_message(
                webhook_url,
                chat_id,
                Plain("\n".join(segment.strip() for segment in plain_segments if segment)),
                mentioned_list or None,
            )

        for image in image_components:
            await self.client.send_image_message(webhook_url, chat_id, image)

        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if buffer:
            await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)

    def _extract_chat_id(self) -> str:
        raw = self.message_obj.raw_message or {}
        if isinstance(raw, dict):
            payload: dict[str, Any] = raw.get("payload") or raw
            chat_id = payload.get("chatid") or payload.get("chat_id")
            if chat_id:
                return str(chat_id)
        return self.message_obj.session_id or self.session_id or ""

    def _extract_webhook(self) -> str:
        raw = self.message_obj.raw_message or {}
        if isinstance(raw, dict):
            payload: dict[str, Any] = raw.get("payload") or raw
            return payload.get("webhook_url", "") or payload.get("response_url", "")
        return ""
