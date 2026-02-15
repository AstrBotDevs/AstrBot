"""会话管理器

负责会话的创建、跟踪和过期清理。
"""

import asyncio
import time

from astrbot import logger


class SessionManager:
    """会话管理器

    I/O契约:
        Input: session_id (str), ttl (int)
        Output: None (管理会话生命周期)
    """

    CLEANUP_INTERVAL = 10  # 清理检查间隔（秒）

    def __init__(self, ttl: int = 30, enabled: bool = False):
        """初始化会话管理器

        Args:
            ttl: 会话过期时间（秒）
            enabled: 是否启用会话隔离
        """
        self.ttl = ttl
        self.enabled = enabled
        self._timestamps: dict[str, float] = {}
        self._cleanup_task: asyncio.Task | None = None
        self._running = False

    def register(self, session_id: str) -> None:
        """注册新会话

        Args:
            session_id: 会话ID
        """
        if not self.enabled:
            return

        if session_id not in self._timestamps:
            self._timestamps[session_id] = time.time()
            logger.debug("Created isolated session: %s, TTL=%ds", session_id, self.ttl)

    def touch(self, session_id: str) -> None:
        """更新会话时间戳

        Args:
            session_id: 会话ID
        """
        if self.enabled and session_id in self._timestamps:
            self._timestamps[session_id] = time.time()

    def is_expired(self, session_id: str) -> bool:
        """检查会话是否过期

        Args:
            session_id: 会话ID

        Returns:
            是否过期
        """
        if not self.enabled:
            return False

        timestamp = self._timestamps.get(session_id)
        if timestamp is None:
            return True

        return time.time() - timestamp > self.ttl

    def start_cleanup_task(self) -> None:
        """启动清理任务"""
        if not self.enabled:
            return

        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Session cleanup task started, TTL=%ds", self.ttl)

    async def stop_cleanup_task(self) -> None:
        """停止清理任务"""
        self._running = False

        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                logger.debug("Cleanup task cancelled")

    async def _cleanup_loop(self) -> None:
        """清理循环"""
        while self._running:
            try:
                await asyncio.sleep(self.CLEANUP_INTERVAL)

                if not self.enabled:
                    continue

                current_time = time.time()
                expired_sessions = [
                    sid
                    for sid, ts in list(self._timestamps.items())
                    if current_time - ts > self.ttl
                ]

                for session_id in expired_sessions:
                    logger.info("Cleaning expired session: %s", session_id)
                    self._timestamps.pop(session_id, None)

                if expired_sessions:
                    logger.info("Cleaned %d expired sessions", len(expired_sessions))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Session cleanup error: %s", e)

        logger.info("Session cleanup task stopped")
