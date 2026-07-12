from typing import Any

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.core.agent.stop_policy import AgentOutputStopped, event_requests_agent_stop


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
        if event_requests_agent_stop(self):
            raise AgentOutputStopped
        if not self.adapter:
            raise RuntimeError("DingTalk message adapter is unavailable.")
        await self.adapter.send_message_chain_with_incoming(
            incoming_message=self.message_obj.raw_message,
            message_chain=message,
            stop_event=self,
        )
        await super().send(message)

    async def send_streaming(self, generator, use_fallback: bool = False):
        # 钉钉统一回退为缓冲发送：最终发送仍使用新的 HTTP 消息接口。
        buffer = None
        async for chain in generator:
            if event_requests_agent_stop(self):
                raise AgentOutputStopped
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)
        if not buffer:
            raise RuntimeError("DingTalk streaming message produced no delivery.")
        buffer.squash_plain()
        if event_requests_agent_stop(self):
            raise AgentOutputStopped
        await self.send(buffer)
        return await super().send_streaming(generator, use_fallback)
