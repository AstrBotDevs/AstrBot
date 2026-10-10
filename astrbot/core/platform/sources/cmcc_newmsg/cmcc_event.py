"""中国移动新消息(5G消息) 事件定义。"""

from __future__ import annotations

from astrbot import logger
from astrbot.api.event import AstrMessageEvent, MessageChain


class CmccNewmsgMessageEvent(AstrMessageEvent):
    """cmcc-newmsg 平台消息事件。

    回复目标从 raw_message 的 from 字段取（即发信人号码/ID），
    兜底用 sender_id。
    """

    def __init__(
        self,
        message_str: str,
        message_obj,
        platform_meta,
        session_id: str,
        adapter=None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.adapter = adapter

    def _reply_to(self) -> str:
        raw = getattr(self.message_obj, "raw_message", None)
        if isinstance(raw, dict) and raw.get("from"):
            return str(raw["from"])
        sender = self.get_sender_id() or ""
        return sender or self.session_id

    async def send(self, message: MessageChain) -> None:
        if not self.adapter:
            logger.error("cmcc-newmsg 消息发送失败: 缺少 adapter")
            return
        await self.adapter.send_message_chain(self._reply_to(), message)
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        # 5G 消息不支持流式，统一缓冲后一次性发送
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
