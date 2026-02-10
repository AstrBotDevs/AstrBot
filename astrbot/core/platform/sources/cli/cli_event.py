"""
CLI Message Event - CLI消息事件

处理CLI平台的消息事件，包括消息发送和接收。
使用 ImageProcessor 处理图片，遵循 DRY 原则。
"""

import asyncio
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
    """

    # 延迟配置
    INITIAL_DELAY = 5.0  # 首次发送延迟
    EXTENDED_DELAY = 10.0  # 后续发送延迟
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

        # 多次回复收集
        self.send_buffer = None
        self._response_delay_task = None
        self._response_delay = self.INITIAL_DELAY

    async def send(self, message_chain: MessageChain) -> dict[str, Any]:
        """发送消息到CLI"""
        # 调用父类方法以设置 _has_send_oper 标志
        # 这告诉 ProcessStage 已经有发送操作，避免触发 LLM
        await super().send(message_chain)

        # Socket模式：收集多次回复
        if self.response_future is not None and not self.response_future.done():
            # 使用 ImageProcessor 预处理图片（避免临时文件被删除）
            ImageProcessor.preprocess_chain(message_chain)

            # 收集多次回复到buffer
            if not self.send_buffer:
                self.send_buffer = message_chain
                self._response_delay = self.INITIAL_DELAY
                logger.debug("[CLI] First send: buffer initialized")
            else:
                # 检查缓冲区大小限制
                current_size = len(self.send_buffer.chain)
                new_size = len(message_chain.chain)
                if current_size + new_size > self.MAX_BUFFER_SIZE:
                    logger.warning(
                        "[CLI] Buffer size limit reached (%d + %d > %d), truncating",
                        current_size,
                        new_size,
                        self.MAX_BUFFER_SIZE,
                    )
                    # 只添加能容纳的部分
                    available = self.MAX_BUFFER_SIZE - current_size
                    if available > 0:
                        self.send_buffer.chain.extend(message_chain.chain[:available])
                else:
                    self.send_buffer.chain.extend(message_chain.chain)
                self._response_delay = self.EXTENDED_DELAY
                logger.debug(
                    "[CLI] Appended to buffer, total: %d", len(self.send_buffer.chain)
                )

            # 重置延迟任务
            if self._response_delay_task and not self._response_delay_task.done():
                self._response_delay_task.cancel()

            self._response_delay_task = asyncio.create_task(self._delayed_response())
        else:
            # 其他模式：直接放入输出队列
            await self.output_queue.put(message_chain)

        return {"success": True}

    async def reply(self, message_chain: MessageChain) -> dict[str, Any]:
        """回复消息"""
        return await self.send(message_chain)

    async def _delayed_response(self) -> None:
        """延迟响应：收集所有回复后统一返回"""
        try:
            await asyncio.sleep(self._response_delay)

            if self.response_future and not self.response_future.done():
                self.response_future.set_result(self.send_buffer)
                logger.debug(
                    "[CLI] Delayed response set, %d components",
                    len(self.send_buffer.chain),
                )

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("[CLI] Delayed response error: %s", e)
            if self.response_future and not self.response_future.done():
                self.response_future.set_exception(e)
