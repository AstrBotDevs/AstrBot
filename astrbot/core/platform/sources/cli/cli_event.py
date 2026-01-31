"""
CLI Message Event - CLI消息事件

处理CLI平台的消息事件，包括消息发送和接收。
"""

import asyncio
from typing import Any

from astrbot import logger
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage
from astrbot.core.platform.platform_metadata import PlatformMetadata


class CLIMessageEvent(AstrMessageEvent):
    """CLI消息事件

    处理命令行模拟器的消息事件。
    """

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        output_queue: asyncio.Queue,
        response_future: asyncio.Future = None,
    ):
        """初始化CLI消息事件

        Args:
            message_str: 纯文本消息
            message_obj: 消息对象
            platform_meta: 平台元数据
            session_id: 会话ID
            output_queue: 输出队列
            response_future: 响应Future对象（用于socket模式）
        """
        super().__init__(
            message_str=message_str,
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id=session_id,
        )

        logger.debug("[ENTRY] CLIMessageEvent.__init__ inputs={message_str=%s}", message_str)

        self.output_queue = output_queue
        self.response_future = response_future

        logger.debug("[EXIT] CLIMessageEvent.__init__ return=None")

    async def send(self, message_chain: MessageChain) -> dict[str, Any]:
        """发送消息到CLI

        Args:
            message_chain: 消息链

        Returns:
            发送结果
        """
        logger.debug("[ENTRY] CLIMessageEvent.send inputs={message_chain=%s}", message_chain)

        # Socket模式：直接设置Future结果（返回完整MessageChain以支持图片等组件）
        if self.response_future is not None and not self.response_future.done():
            # 预处理本地文件图片：立即读取并转换为base64（避免临时文件被删除）
            from astrbot.core.message.components import Image
            import base64
            import os

            for comp in message_chain.chain:
                if isinstance(comp, Image) and comp.file and comp.file.startswith("file:///"):
                    file_path = comp.file[8:]  # 去掉 file:///
                    try:
                        if os.path.exists(file_path):
                            with open(file_path, 'rb') as f:
                                image_data = f.read()
                                base64_data = base64.b64encode(image_data).decode('utf-8')
                                # 修改Image组件，将本地文件转换为base64
                                comp.file = f"base64://{base64_data}"
                                logger.debug(f"[PROCESS] Converted local image to base64: {file_path}, size: {len(image_data)} bytes")
                    except Exception as e:
                        logger.error(f"[ERROR] Failed to read image file {file_path}: {e}")

            self.response_future.set_result(message_chain)
            logger.debug("[PROCESS] Set socket response future with MessageChain")
        else:
            # 其他模式：将消息放入输出队列
            await self.output_queue.put(message_chain)
            logger.debug("[PROCESS] Put message to output queue")

        logger.debug("[EXIT] CLIMessageEvent.send return={success=True}")

        return {"success": True}

    async def reply(self, message_chain: MessageChain) -> dict[str, Any]:
        """回复消息

        Args:
            message_chain: 消息链

        Returns:
            发送结果
        """
        logger.debug("[ENTRY] CLIMessageEvent.reply inputs={message_chain=%s}", message_chain)

        result = await self.send(message_chain)

        logger.debug("[EXIT] CLIMessageEvent.reply return=%s", result)

        return result
