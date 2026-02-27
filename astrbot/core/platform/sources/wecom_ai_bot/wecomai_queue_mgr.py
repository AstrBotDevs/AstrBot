"""企业微信智能机器人队列管理器
参考 webchat_queue_mgr.py，为企业微信智能机器人实现队列机制
支持异步消息处理和流式响应
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from astrbot.api import logger


class WecomAIQueueMgr:
    """企业微信智能机器人队列管理器"""

    def __init__(self, queue_maxsize: int = 128, back_queue_maxsize: int = 512) -> None:
        self.queues: dict[str, asyncio.Queue] = {}
        """StreamID 到输入队列的映射 - 用于接收用户消息"""

        self.back_queues: dict[str, asyncio.Queue] = {}
        """StreamID 到输出队列的映射 - 用于发送机器人响应"""

        self.pending_responses: dict[str, dict[str, Any]] = {}
        """待处理的响应缓存，用于流式响应"""
        self.completed_streams: dict[str, float] = {}
        """已结束的 stream 缓存，用于兼容平台后续重复轮询"""
        self._queue_close_events: dict[str, asyncio.Event] = {}
        self._listener_tasks: dict[str, asyncio.Task] = {}
        self._listener_callback: Callable[[dict], Awaitable[None]] | None = None
        self.queue_maxsize = queue_maxsize
        self.back_queue_maxsize = back_queue_maxsize

    def get_or_create_queue(self, session_id: str) -> asyncio.Queue:
        """获取或创建指定会话的输入队列

        Args:
            session_id: 会话ID

        Returns:
            输入队列实例

        """
        if session_id not in self.queues:
            self.queues[session_id] = asyncio.Queue(maxsize=self.queue_maxsize)
            self._queue_close_events[session_id] = asyncio.Event()
            self._start_listener_if_needed(session_id)
            logger.debug(f"[WecomAI] 创建输入队列: {session_id}")
        return self.queues[session_id]

    def get_or_create_back_queue(self, session_id: str) -> asyncio.Queue:
        """获取或创建指定会话的输出队列

        Args:
            session_id: 会话ID

        Returns:
            输出队列实例

        """
        if session_id not in self.back_queues:
            self.back_queues[session_id] = asyncio.Queue(
                maxsize=self.back_queue_maxsize
            )
            logger.debug(f"[WecomAI] 创建输出队列: {session_id}")
        return self.back_queues[session_id]

    def remove_queues(self, session_id: str, mark_finished: bool = False) -> None:
        """移除指定会话的所有队列

        Args:
            session_id: 会话ID
            mark_finished: 是否标记为已正常结束

        """
        self.remove_queue(session_id)

        if session_id in self.back_queues:
            del self.back_queues[session_id]
            logger.debug(f"[WecomAI] 移除输出队列: {session_id}")

        if session_id in self.pending_responses:
            del self.pending_responses[session_id]
            logger.debug(f"[WecomAI] 移除待处理响应: {session_id}")
        if mark_finished:
            self.completed_streams[session_id] = asyncio.get_event_loop().time()
            logger.debug(f"[WecomAI] 标记流已结束: {session_id}")

    def remove_queue(self, session_id: str):
        """仅移除输入队列和对应监听任务"""
        if session_id in self.queues:
            del self.queues[session_id]
            logger.debug(f"[WecomAI] 移除输入队列: {session_id}")

        close_event = self._queue_close_events.pop(session_id, None)
        if close_event is not None:
            close_event.set()

        task = self._listener_tasks.pop(session_id, None)
        if task is not None:
            task.cancel()

    def has_queue(self, session_id: str) -> bool:
        """检查是否存在指定会话的队列

        Args:
            session_id: 会话ID

        Returns:
            是否存在队列

        """
        return session_id in self.queues

    def has_back_queue(self, session_id: str) -> bool:
        """检查是否存在指定会话的输出队列

        Args:
            session_id: 会话ID

        Returns:
            是否存在输出队列

        """
        return session_id in self.back_queues

    def set_pending_response(
        self, session_id: str, callback_params: dict[str, str]
    ) -> None:
        """设置待处理的响应参数

        Args:
            session_id: 会话ID
            callback_params: 回调参数（nonce, timestamp等）

        """
        self.pending_responses[session_id] = {
            "callback_params": callback_params,
            "timestamp": asyncio.get_event_loop().time(),
        }
        logger.debug(f"[WecomAI] 设置待处理响应: {session_id}")

    def get_pending_response(self, session_id: str) -> dict[str, Any] | None:
        """获取待处理的响应参数

        Args:
            session_id: 会话ID

        Returns:
            响应参数，如果不存在则返回None

        """
        return self.pending_responses.get(session_id)

    def is_stream_finished(
        self,
        session_id: str,
        max_age_seconds: int = 60,
    ) -> bool:
        """判断 stream 是否在短期内已结束"""
        finished_at = self.completed_streams.get(session_id)
        if finished_at is None:
            return False
        if asyncio.get_event_loop().time() - finished_at > max_age_seconds:
            self.completed_streams.pop(session_id, None)
            return False
        return True

    def cleanup_expired_responses(self, max_age_seconds: int = 300) -> None:
        """清理过期的待处理响应

        Args:
            max_age_seconds: 最大存活时间（秒）

        """
        current_time = asyncio.get_event_loop().time()
        expired_sessions = []

        for session_id, response_data in self.pending_responses.items():
            if current_time - response_data["timestamp"] > max_age_seconds:
                expired_sessions.append(session_id)

        for session_id in expired_sessions:
            self.remove_queues(session_id)
            logger.debug(f"[WecomAI] 清理过期响应及队列: {session_id}")
        expired_finished = [
            session_id
            for session_id, finished_at in self.completed_streams.items()
            if current_time - finished_at > 60
        ]
        for session_id in expired_finished:
            self.completed_streams.pop(session_id, None)

    def set_listener(
        self,
        callback: Callable[[dict], Awaitable[None]],
    ):
        self._listener_callback = callback
        for session_id in list(self.queues.keys()):
            self._start_listener_if_needed(session_id)

    def _start_listener_if_needed(self, session_id: str):
        if self._listener_callback is None:
            return
        if session_id in self._listener_tasks:
            task = self._listener_tasks[session_id]
            if not task.done():
                return
        queue = self.queues.get(session_id)
        close_event = self._queue_close_events.get(session_id)
        if queue is None or close_event is None:
            return
        task = asyncio.create_task(
            self._listen_to_queue(session_id, queue, close_event),
            name=f"wecomai_listener_{session_id}",
        )
        self._listener_tasks[session_id] = task
        task.add_done_callback(lambda _: self._listener_tasks.pop(session_id, None))
        logger.debug(f"[WecomAI] 为会话启动监听器: {session_id}")

    async def _listen_to_queue(
        self,
        session_id: str,
        queue: asyncio.Queue,
        close_event: asyncio.Event,
    ):
        while True:
            get_task = asyncio.create_task(queue.get())
            close_task = asyncio.create_task(close_event.wait())
            try:
                done, pending = await asyncio.wait(
                    {get_task, close_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                if close_task in done:
                    break
                data = get_task.result()
                if self._listener_callback is None:
                    continue
                try:
                    await self._listener_callback(data)
                except Exception as e:
                    logger.error(f"处理会话 {session_id} 消息时发生错误: {e}")
            except asyncio.CancelledError:
                break
            finally:
                if not get_task.done():
                    get_task.cancel()
                if not close_task.done():
                    close_task.cancel()

    def get_stats(self) -> dict[str, int]:
        """获取队列统计信息

        Returns:
            统计信息字典

        """
        return {
            "input_queues": len(self.queues),
            "output_queues": len(self.back_queues),
            "pending_responses": len(self.pending_responses),
        }
