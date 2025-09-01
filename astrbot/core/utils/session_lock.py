import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager


class SessionLockManager:
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_count: dict[str, int] = defaultdict(int)
        self._access_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire_lock(self, session_id: str):
        async with self._access_lock:
            lock = self._locks[session_id]
            self._lock_count[session_id] += 1

        try:
            async with lock:
                yield
        finally:
            async with self._access_lock:
                self._lock_count[session_id] -= 1
                if self._lock_count[session_id] == 0:
                    self._locks.pop(session_id, None)
                    self._lock_count.pop(session_id, None)


session_lock_manager = SessionLockManager()
