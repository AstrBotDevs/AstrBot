"""
企业微信智能机器人队列管理器
参考 webchat_queue_mgr.py，为企业微信智能机器人实现队列机制
支持异步消息处理和流式响应
"""

import asyncio
from typing import Dict, Any, Optional
from astrbot.api import logger


class WecomAIQueueMgr:
    """企业微信智能机器人队列管理器"""

    def __init__(self) -> None:
        self.queues: Dict[str, asyncio.Queue] = {}
        """StreamID 到输入队列的映射 - 用于接收用户消息"""

        self.back_queues: Dict[str, asyncio.Queue] = {}
        """StreamID 到输出队列的映射 - 用于发送机器人响应"""

        self.pending_responses: Dict[str, Dict[str, Any]] = {}
        """待处理的响应缓存，用于流式响应"""

    def get_or_create_queue(self, session_id: str) -> asyncio.Queue:
        """获取或创建指定会话的输入队列

        Args:
            session_id: 会话ID

        Returns:
            输入队列实例
        """
        if session_id not in self.queues:
            self.queues[session_id] = asyncio.Queue()
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
            self.back_queues[session_id] = asyncio.Queue()
            logger.debug(f"[WecomAI] 创建输出队列: {session_id}")
        return self.back_queues[session_id]

    def remove_queues(self, session_id: str):
        """移除指定会话的所有队列

        Args:
            session_id: 会话ID
        """
        if session_id in self.queues:
            del self.queues[session_id]
            logger.debug(f"[WecomAI] 移除输入队列: {session_id}")

        if session_id in self.back_queues:
            del self.back_queues[session_id]
            logger.debug(f"[WecomAI] 移除输出队列: {session_id}")

        if session_id in self.pending_responses:
            del self.pending_responses[session_id]
            logger.debug(f"[WecomAI] 移除待处理响应: {session_id}")

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

    def set_pending_response(self, session_id: str, callback_params: Dict[str, str]):
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

    def get_pending_response(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取待处理的响应参数

        Args:
            session_id: 会话ID

        Returns:
            响应参数，如果不存在则返回None
        """
        return self.pending_responses.get(session_id)

    def cleanup_expired_responses(self, max_age_seconds: int = 300):
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
            del self.pending_responses[session_id]
            logger.debug(f"[WecomAI] 清理过期响应: {session_id}")

    def get_stats(self) -> Dict[str, int]:
        """获取队列统计信息

        Returns:
            统计信息字典
        """
        return {
            "input_queues": len(self.queues),
            "output_queues": len(self.back_queues),
            "pending_responses": len(self.pending_responses),
        }


# 全局队列管理器实例
wecomai_queue_mgr = WecomAIQueueMgr()
