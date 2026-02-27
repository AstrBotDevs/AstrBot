"""企业微信智能机器人事件处理模块，处理消息事件的发送和接收"""
from astrbot.core.lang import t

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import At, Image, Plain

from .wecomai_api import WecomAIBotAPIClient
from .wecomai_queue_mgr import WecomAIQueueMgr
from .wecomai_webhook import WecomAIBotWebhookClient


class WecomAIBotMessageEvent(AstrMessageEvent):
    """企业微信智能机器人消息事件"""

    def __init__(
        self,
        message_str: str,
        message_obj,
        platform_meta,
        session_id: str,
        api_client: WecomAIBotAPIClient,
        queue_mgr: WecomAIQueueMgr,
        webhook_client: WecomAIBotWebhookClient | None = None,
        only_use_webhook_url_to_send: bool = False,
    ) -> None:
        """初始化消息事件

        Args:
            message_str: 消息字符串
            message_obj: 消息对象
            platform_meta: 平台元数据
            session_id: 会话 ID
            api_client: API 客户端

        """
        super().__init__(message_str, message_obj, platform_meta, session_id)
        self.api_client = api_client
        self.queue_mgr = queue_mgr
        self.webhook_client = webhook_client
        self.only_use_webhook_url_to_send = only_use_webhook_url_to_send

    async def _mark_stream_complete(self, stream_id: str) -> None:
        back_queue = self.queue_mgr.get_or_create_back_queue(stream_id)
        await back_queue.put(
            {
                "type": "complete",
                "data": "",
                "streaming": False,
                "session_id": stream_id,
            },
        )

    @staticmethod
    async def _send(
        message_chain: MessageChain | None,
        stream_id: str,
        queue_mgr: WecomAIQueueMgr,
        streaming: bool = False,
        suppress_unsupported_log: bool = False,
    ):
        back_queue = queue_mgr.get_or_create_back_queue(stream_id)

        if not message_chain:
            await back_queue.put(
                {
                    "type": "end",
                    "data": "",
                    "streaming": False,
                },
            )
            return ""

        data = ""
        for comp in message_chain.chain:
            if isinstance(comp, At):
                data = f"@{comp.name} "
                await back_queue.put(
                    {
                        "type": "plain",
                        "data": data,
                        "streaming": streaming,
                        "session_id": stream_id,
                    },
                )
            elif isinstance(comp, Plain):
                data = comp.text
                await back_queue.put(
                    {
                        "type": "plain",
                        "data": data,
                        "streaming": streaming,
                        "session_id": stream_id,
                    },
                )
            elif isinstance(comp, Image):
                # 处理图片消息
                try:
                    image_base64 = await comp.convert_to_base64()
                    if image_base64:
                        await back_queue.put(
                            {
                                "type": "image",
                                "image_data": image_base64,
                                "streaming": streaming,
                                "session_id": stream_id,
                            },
                        )
                    else:
                        logger.warning(t("msg-e44e77b0"))
                except Exception as e:
                    logger.error(t("msg-30d116ed"), e)
            else:
                if not suppress_unsupported_log:
                    logger.warning(
                        t("msg-31b11295", res=type(comp))
                    )

        return data

    async def send(self, message: MessageChain | None) -> None:
        """发送消息"""
        raw = self.message_obj.raw_message
        assert isinstance(raw, dict), (
            "wecom_ai_bot platform event raw_message should be a dict"
        )
        stream_id = raw.get("stream_id", self.session_id)
        if self.only_use_webhook_url_to_send and self.webhook_client and message:
            await self.webhook_client.send_message_chain(message)
            await self._mark_stream_complete(stream_id)
            await super().send(MessageChain([]))
            return

        if self.webhook_client and message:
            await self.webhook_client.send_message_chain(
                message,
                unsupported_only=True,
            )

        await WecomAIBotMessageEvent._send(
            message,
            stream_id,
            self.queue_mgr,
            suppress_unsupported_log=self.webhook_client is not None,
        )
        await super().send(MessageChain([]))

    async def send_streaming(self, generator, use_fallback=False) -> None:
        """流式发送消息，参考webchat的send_streaming设计"""
        final_data = ""
        raw = self.message_obj.raw_message
        assert isinstance(raw, dict), (
            "wecom_ai_bot platform event raw_message should be a dict"
        )
        stream_id = raw.get("stream_id", self.session_id)
        back_queue = self.queue_mgr.get_or_create_back_queue(stream_id)

        if self.only_use_webhook_url_to_send and self.webhook_client:
            merged_chain = MessageChain([])
            async for chain in generator:
                merged_chain.chain.extend(chain.chain)
            merged_chain.squash_plain()
            await self.webhook_client.send_message_chain(merged_chain)
            await self._mark_stream_complete(stream_id)
            await super().send_streaming(generator, use_fallback)
            return

        # 企业微信智能机器人不支持增量发送，因此我们需要在这里将增量内容累积起来，积累发送
        increment_plain = ""
        async for chain in generator:
            if self.webhook_client:
                await self.webhook_client.send_message_chain(
                    chain, unsupported_only=True
                )
            # 累积增量内容，并改写 Plain 段
            chain.squash_plain()
            for comp in chain.chain:
                if isinstance(comp, Plain):
                    comp.text = increment_plain + comp.text
                    increment_plain = comp.text
                    break

            if chain.type == "break" and final_data:
                # 分割符
                await back_queue.put(
                    {
                        "type": "break",  # break means a segment end
                        "data": final_data,
                        "streaming": True,
                        "session_id": stream_id,
                    },
                )
                final_data = ""
                continue

            final_data += await WecomAIBotMessageEvent._send(
                chain,
                stream_id=stream_id,
                queue_mgr=self.queue_mgr,
                streaming=True,
                suppress_unsupported_log=self.webhook_client is not None,
            )

        await back_queue.put(
            {
                "type": "complete",  # complete means we return the final result
                "data": final_data,
                "streaming": True,
                "session_id": stream_id,
            },
        )
        await super().send_streaming(generator, use_fallback)
