"""企业微信智能机器人事件处理模块，处理消息事件的发送和接收"""

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    Image,
    Plain,
)

from .wecomai_api import WecomAIBotAPIClient
from .wecomai_queue_mgr import wecomai_queue_mgr


class WecomAIBotMessageEvent(AstrMessageEvent):
    """企业微信智能机器人消息事件"""

    def __init__(
        self,
        message_str: str,
        message_obj,
        platform_meta,
        session_id: str,
        api_client: WecomAIBotAPIClient,
    ):
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

    @staticmethod
    async def _send(
        message_chain: MessageChain,
        stream_id: str,
        streaming: bool = False,
    ):
        back_queue = wecomai_queue_mgr.get_or_create_back_queue(stream_id)

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
            if isinstance(comp, Plain):
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
                        logger.warning("图片数据为空，跳过")
                except Exception as e:
                    logger.error("处理图片消息失败: %s", e)
            else:
                logger.warning(f"[WecomAI] 不支持的消息组件类型: {type(comp)}, 跳过")

        return data

    async def send(self, message: MessageChain):
        """发送消息"""
        raw = self.message_obj.raw_message
        assert isinstance(raw, dict), (
            "wecom_ai_bot platform event raw_message should be a dict"
        )
        stream_id = raw.get("stream_id", self.session_id)
        await WecomAIBotMessageEvent._send(message, stream_id)
        await super().send(message)

    async def send_streaming(self, generator, use_fallback=False):
        """流式发送消息，参考webchat的send_streaming设计"""
        final_data = ""
        raw = self.message_obj.raw_message
        assert isinstance(raw, dict), (
            "wecom_ai_bot platform event raw_message should be a dict"
        )
        stream_id = raw.get("stream_id", self.session_id)
        back_queue = wecomai_queue_mgr.get_or_create_back_queue(stream_id)

        # 企业微信智能机器人不支持增量发送，因此我们需要在这里将增量内容累积起来，积累发送
        increment_plain = ""
        async for chain in generator:
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
                        "session_id": self.session_id,
                    },
                )
                final_data = ""
                continue

            final_data += await WecomAIBotMessageEvent._send(
                chain,
                stream_id=stream_id,
                streaming=True,
            )

        await back_queue.put(
            {
                "type": "complete",  # complete means we return the final result
                "data": final_data,
                "streaming": True,
                "session_id": self.session_id,
            },
        )
        await super().send_streaming(generator, use_fallback)
