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

        # 用于收集多次回复
        self.send_buffer = None
        self._response_delay_task = None
        self._response_delay = 3.0  # 延迟3秒收集所有回复（支持工具调用等多轮场景）

        logger.debug("[EXIT] CLIMessageEvent.__init__ return=None")

    async def send(self, message_chain: MessageChain) -> dict[str, Any]:
        """发送消息到CLI

        Args:
            message_chain: 消息链

        Returns:
            发送结果
        """
        logger.debug("[ENTRY] CLIMessageEvent.send inputs={message_chain=%s}", message_chain)

        # Socket模式：收集多次回复
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

            # 收集多次回复到buffer（自适应延迟机制）
            if not self.send_buffer:
                # 第一次send：初始化buffer，使用中等延迟（5秒）
                # 5秒足够等待工具调用的第二次回复，同时不会让简单回复等太久
                self.send_buffer = message_chain
                self._response_delay = 5.0
                logger.info("[PROCESS] First send: initialized buffer with 5s delay")
            else:
                # 后续send：追加到buffer，切换到长延迟（10秒）
                # 确保能收集到所有工具调用的回复
                self.send_buffer.chain.extend(message_chain.chain)
                self._response_delay = 10.0
                logger.info(
                    f"[PROCESS] Appended to buffer (switched to 10s delay), total: {len(self.send_buffer.chain)} components"
                )

            # 取消之前的延迟任务（如果存在）
            if self._response_delay_task and not self._response_delay_task.done():
                self._response_delay_task.cancel()
                logger.info("[PROCESS] Cancelled previous delay task")

            # 启动新的延迟任务（每次send都重置延迟）
            self._response_delay_task = asyncio.create_task(self._delayed_response())
            logger.info(f"[PROCESS] Started new delay task ({self._response_delay}s)")
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

    async def _delayed_response(self) -> None:
        """延迟响应：等待一段时间收集所有回复后统一返回

        等待 _response_delay 秒后，将累积的所有消息统一返回给客户端。
        这样可以支持插件的多轮回复（如先发文本，再发图片）。
        """
        logger.debug(
            "[ENTRY] _delayed_response inputs={delay=%s}", self._response_delay
        )

        try:
            # 等待延迟时间，收集所有回复
            await asyncio.sleep(self._response_delay)

            # 检查 Future 是否还未完成
            if self.response_future and not self.response_future.done():
                # 将累积的消息设置到 Future
                self.response_future.set_result(self.send_buffer)
                logger.debug(
                    "[PROCESS] Set delayed response with %d components",
                    len(self.send_buffer.chain),
                )
            else:
                logger.warning(
                    "[WARN] Response future already done or None, skipping set_result"
                )

        except Exception as e:
            logger.error("[ERROR] Failed to set delayed response: %s", e)
            # 如果出错，尝试设置异常到 Future
            if self.response_future and not self.response_future.done():
                self.response_future.set_exception(e)

        logger.debug("[EXIT] _delayed_response return=None")
