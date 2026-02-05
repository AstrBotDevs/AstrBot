"""响应收集器

负责收集多次回复并延迟返回，支持工具调用等多轮场景。
"""

import asyncio

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain

from .image_processor import ImageProcessor


class ResponseCollector:
    """响应收集器

    I/O契约:
        Input: MessageChain (多次)
        Output: MessageChain (合并后)
    """

    # 延迟配置
    INITIAL_DELAY = 5.0  # 首次回复延迟
    EXTENDED_DELAY = 10.0  # 后续回复延迟

    def __init__(self, response_future: asyncio.Future):
        """初始化响应收集器

        Args:
            response_future: 响应Future对象
        """
        self.response_future = response_future
        self.buffer: MessageChain | None = None
        self._delay_task: asyncio.Task | None = None
        self._current_delay = self.INITIAL_DELAY

    def collect(self, message_chain: MessageChain) -> None:
        """收集消息到缓冲区

        Args:
            message_chain: 消息链
        """
        if self.response_future.done():
            logger.warning("Response future already done, skipping collect")
            return

        # 预处理图片
        ImageProcessor.preprocess_chain(message_chain)

        if not self.buffer:
            # 首次收集
            self.buffer = message_chain
            self._current_delay = self.INITIAL_DELAY
            logger.info(
                "First collect: initialized buffer with %.1fs delay",
                self._current_delay,
            )
        else:
            # 追加到缓冲区
            self.buffer.chain.extend(message_chain.chain)
            self._current_delay = self.EXTENDED_DELAY
            logger.info(
                "Appended to buffer (switched to %.1fs delay), total: %d components",
                self._current_delay,
                len(self.buffer.chain),
            )

        # 重置延迟任务
        self._reset_delay_task()

    def _reset_delay_task(self) -> None:
        """重置延迟任务"""
        # 取消之前的延迟任务
        if self._delay_task and not self._delay_task.done():
            self._delay_task.cancel()
            logger.debug("Cancelled previous delay task")

        # 启动新的延迟任务
        self._delay_task = asyncio.create_task(self._delayed_response())
        logger.debug("Started new delay task (%.1fs)", self._current_delay)

    async def _delayed_response(self) -> None:
        """延迟响应：等待一段时间后统一返回"""
        try:
            await asyncio.sleep(self._current_delay)

            if self.response_future and not self.response_future.done():
                self.response_future.set_result(self.buffer)
                logger.debug(
                    "Set delayed response with %d components",
                    len(self.buffer.chain) if self.buffer else 0,
                )
            else:
                logger.warning(
                    "Response future already done or None, skipping set_result"
                )

        except asyncio.CancelledError:
            # 被取消是正常的（有新消息到来）
            pass
        except Exception as e:
            logger.error("Failed to set delayed response: %s", e)
            if self.response_future and not self.response_future.done():
                self.response_future.set_exception(e)
