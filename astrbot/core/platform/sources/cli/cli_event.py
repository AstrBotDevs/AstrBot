"""
CLI Message Event - CLI消息事件

处理CLI平台的消息事件，包括消息发送和接收。
使用 ImageProcessor 处理图片，遵循 DRY 原则。
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Any

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage
from astrbot.core.platform.platform_metadata import PlatformMetadata

from .message.image_processor import ImageProcessor


class CLIMessageEvent(AstrMessageEvent):
    """CLI消息事件

    处理命令行模拟器的消息事件。
    Socket模式下收集管道中所有send()调用的消息，在管道完成(finalize)后统一返回。
    """

    MAX_BUFFER_SIZE = 100  # 缓冲区最大消息组件数

    def __init__(
        self,
        message_str: str,
        message_obj: AstrBotMessage,
        platform_meta: PlatformMetadata,
        session_id: str,
        output_queue: asyncio.Queue,
        response_future: asyncio.Future = None,
    ):
        """初始化CLI消息事件"""
        super().__init__(
            message_str=message_str,
            message_obj=message_obj,
            platform_meta=platform_meta,
            session_id=session_id,
        )

        self.output_queue = output_queue
        self.response_future = response_future

        # 多次回复收集（Socket模式）
        self.send_buffer = None

    async def send(self, message_chain: MessageChain) -> dict[str, Any]:
        """发送消息到CLI"""
        await super().send(message_chain)

        # Socket模式：收集所有回复到buffer，等待finalize()统一返回
        if self.response_future is not None and not self.response_future.done():
            ImageProcessor.preprocess_chain(message_chain)

            if not self.send_buffer:
                self.send_buffer = message_chain
                logger.debug("[CLI] First send: buffer initialized")
            else:
                current_size = len(self.send_buffer.chain)
                new_size = len(message_chain.chain)
                if current_size + new_size > self.MAX_BUFFER_SIZE:
                    logger.warning(
                        "[CLI] Buffer size limit reached (%d + %d > %d), truncating",
                        current_size,
                        new_size,
                        self.MAX_BUFFER_SIZE,
                    )
                    available = self.MAX_BUFFER_SIZE - current_size
                    if available > 0:
                        self.send_buffer.chain.extend(message_chain.chain[:available])
                else:
                    self.send_buffer.chain.extend(message_chain.chain)
                logger.debug(
                    "[CLI] Appended to buffer, total: %d", len(self.send_buffer.chain)
                )
        else:
            # 非Socket模式或future已完成：直接放入输出队列
            await self.output_queue.put(message_chain)

        return {"success": True}

    async def send_streaming(
        self,
        generator: AsyncGenerator[MessageChain, None],
        use_fallback: bool = False,
    ) -> None:
        """处理流式LLM响应

        CLI不支持真正的流式输出，采用收集后一次性发送的策略。
        与aiocqhttp的非fallback模式一致。
        """
        buffer = None
        async for chain in generator:
            if not buffer:
                buffer = chain
            else:
                buffer.chain.extend(chain.chain)

        if not buffer:
            return

        buffer.squash_plain()
        await self.send(buffer)
        await super().send_streaming(generator, use_fallback)

    async def reply(self, message_chain: MessageChain) -> dict[str, Any]:
        """回复消息"""
        return await self.send(message_chain)

    async def finalize(self) -> None:
        """管道完成后调用，将收集的所有回复统一返回给Socket客户端。

        由PipelineScheduler.execute()在所有阶段执行完毕后调用。
        """
        if self.response_future and not self.response_future.done():
            if self.send_buffer:
                self.response_future.set_result(self.send_buffer)
                logger.debug(
                    "[CLI] Pipeline done, response set with %d components",
                    len(self.send_buffer.chain),
                )
            else:
                # 管道完成但没有任何发送操作（如被白名单/频率限制拦截）
                self.response_future.set_result(None)
                logger.debug("[CLI] Pipeline done, no response to send")
