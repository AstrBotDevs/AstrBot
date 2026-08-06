from typing import Any

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.send_result import PlatformSendResult


class DingtalkMessageEvent(AstrMessageEvent):
    def __init__(
        self,
        message_str,
        message_obj,
        platform_meta,
        session_id,
        client: Any = None,
        adapter: Any = None,
    ) -> None:
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self._client = client
        self._adapter = adapter

    async def send(self, message: MessageChain) -> PlatformSendResult | None:
        if not self._adapter:
            logger.error("钉钉消息发送失败: 缺少 adapter")
            return self._failure_send_result(
                "DingTalk adapter unavailable",
                message_count=len(message.chain),
            )
        await self._adapter.send_message_chain_with_incoming(
            incoming_message=self.message_obj.raw_message,
            message_chain=message,
        )
        return await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        # 钉钉统一回退为缓冲发送：最终发送仍使用新的 HTTP 消息接口。
        return await self._send_buffered_streaming_response(generator, use_fallback)
