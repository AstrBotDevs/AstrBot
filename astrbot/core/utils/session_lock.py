import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager


class SessionLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._lock_count: dict[str, int] = defaultdict(int)
        self._access_lock: asyncio.Lock | None = None
        self._access_lock_loop_id: int | None = None

    def _get_access_lock(self) -> asyncio.Lock:
        """延迟初始化 access lock，确保绑定到当前 event loop"""
        current_loop = asyncio.get_running_loop()
        current_loop_id = id(current_loop)
        if self._access_lock is None or self._access_lock_loop_id != current_loop_id:
            self._access_lock = asyncio.Lock()
            self._access_lock_loop_id = current_loop_id
        return self._access_lock

    def _get_lock(self, session_id: str) -> asyncio.Lock:
        """延迟初始化 session lock，确保绑定到当前 event loop"""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    @asynccontextmanager
    async def acquire_lock(self, session_id: str):
        access_lock = self._get_access_lock()
        async with access_lock:
            lock = self._get_lock(session_id)
            self._lock_count[session_id] += 1

        try:
            async with lock:
                yield
        finally:
            async with access_lock:
                self._lock_count[session_id] -= 1
                if self._lock_count[session_id] == 0:
                    self._locks.pop(session_id, None)
                    self._lock_count.pop(session_id, None)


session_lock_manager = SessionLockManager()
