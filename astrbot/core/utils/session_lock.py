import asyncio
from typing import Dict

class SessionLockManager:
    """
    管理会话锁，确保同一会话的异步操作互斥执行。
    """
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._access_lock = asyncio.Lock()

    async def get_lock(self, session_id: str) -> asyncio.Lock:
        """
        获取或创建指定 session_id 的锁。

        Args:
            session_id (str): 唯一的会话标识符。

        Returns:
            asyncio.Lock: 对应会话的锁实例。
        """
        async with self._access_lock:
            if session_id not in self._locks:
                self._locks[session_id] = asyncio.Lock()
            return self._locks[session_id]

# 创建一个全局实例，方便在其他模块中直接导入和使用
session_lock_manager = SessionLockManager()