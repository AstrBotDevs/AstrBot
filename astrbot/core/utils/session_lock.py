import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager


class SessionLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_count: dict[str, int] = defaultdict(int)
        self._access_lock: asyncio.Lock | None = None

    def _get_access_lock(self) -> asyncio.Lock:
        """延迟初始化 access lock，确保在有 event loop 时创建"""
        if self._access_lock is None:
            self._access_lock = asyncio.Lock()
        return self._access_lock

    @asynccontextmanager
    async def acquire_lock(self, session_id: str):
        access_lock = self._get_access_lock()
        async with access_lock:
            lock = self._locks.setdefault(session_id, asyncio.Lock())
            self._lock_count[session_id] += 1

        try:
            async with lock:
                yield
        finally:
            async with self._get_access_lock():
                self._lock_count[session_id] -= 1
                if self._lock_count[session_id] == 0:
                    self._locks.pop(session_id, None)
                    self._lock_count.pop(session_id, None)


session_lock_manager = SessionLockManager()
