"""
企业微信智能机器人事件处理模块，处理消息事件的发送和接收
"""

import uuid
from typing import AsyncGenerator, Dict, Any, Optional

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.message_components import (
    Image,
    Plain,
)
from astrbot.api.platform import Group
from astrbot.api import logger

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
        callback_params: Dict[str, str],
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
        session_id: str,
        streaming: bool = False,
    ):
        session_key = session_id.split("!")[-1] if "!" in session_id else session_id
        back_queue = wecomai_queue_mgr.get_or_create_back_queue(session_key)

        if not message_chain:
            await back_queue.put(
                {
                    "type": "end",
                    "data": "",
                    "streaming": False,
                }
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
                        "session_id": session_id,
                    }
                )
            elif isinstance(comp, Image):
                # 处理图片消息
                try:
                    image_base64 = await comp.convert_to_base64()
                    if image_base64:
                        data = f"[IMAGE]{str(uuid.uuid4())}"
                        await back_queue.put(
                            {
                                "type": "image",
                                "data": data,
                                "image_data": image_base64,
                                "streaming": streaming,
                                "session_id": session_id,
                            }
                        )
                    else:
                        logger.warning("图片数据为空，跳过")
                except Exception as e:
                    logger.error("处理图片消息失败: %s", e)
            else:
                # 其他类型的组件转换为文本
                text_data = str(comp)
                data += text_data
                await back_queue.put(
                    {
                        "type": "component",
                        "data": text_data,
                        "streaming": streaming,
                        "session_id": session_id,
                    }
                )

        return data

    async def send(self, message: MessageChain):
        """发送消息"""
        await WecomAIBotMessageEvent._send(message, self.session_id)
        await super().send(message)

    async def send_streaming(
        self, generator: AsyncGenerator, use_fallback: bool = False
    ):
        """流式发送消息，参考webchat的send_streaming设计"""
        final_data = ""
        session_key = (
            self.session_id.split("!")[-1]
            if "!" in self.session_id
            else self.session_id
        )
        back_queue = wecomai_queue_mgr.get_or_create_back_queue(session_key)

        async for chain in generator:
            if chain.type == "break" and final_data:
                # 分割符
                await back_queue.put(
                    {
                        "type": "break",  # break means a segment end
                        "data": final_data,
                        "streaming": True,
                        "session_id": self.session_id,
                    }
                )
                final_data = ""
                continue

            final_data += await WecomAIBotMessageEvent._send(
                chain,
                session_id=self.session_id,
                streaming=True,
            )

        await back_queue.put(
            {
                "type": "complete",  # complete means we return the final result
                "data": final_data,
                "streaming": True,
                "session_id": self.session_id,
            }
        )
        await super().send_streaming(generator, use_fallback)

    async def get_group(self, group_id=None, **kwargs) -> Optional[Group]:
        """获取群组信息"""
        return None

    def get_sender_id(self) -> str:
        """获取发送者 ID"""
        return getattr(self.message_obj, "sender", {}).get("user_id", "unknown")

    def get_sender_name(self) -> str:
        """获取发送者名称"""
        return getattr(self.message_obj, "sender", {}).get("nickname", "Unknown")

    def get_group_id(self) -> Optional[str]:
        """获取群组 ID"""
        return None

    def is_private_message(self) -> bool:
        """是否为私聊消息"""
        return True

    def is_group_message(self) -> bool:
        """是否为群消息"""
        return False

    def get_raw_message(self) -> Any:
        """获取原始消息数据"""
        return getattr(self.message_obj, "raw_message", {})
