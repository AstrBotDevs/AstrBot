import asyncio
from contextlib import asynccontextmanager
from typing import Dict


class SessionLockManager:
    def __init__(self):
        self._locks: Dict[str, asyncio.Lock] = {}
        self._lock_count: Dict[str, int] = {}
        self._access_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire_lock(self, session_id: str):
        async with self._access_lock:
            lock = self._locks.setdefault(session_id, asyncio.Lock())
            self._lock_count[session_id] = self._lock_count.get(session_id, 0) + 1

        try:
            async with lock:
                yield
        finally:
            async with self._access_lock:
                count = self._lock_count.get(session_id, 0)
                if count <= 1:
                    self._locks.pop(session_id, None)
                    self._lock_count.pop(session_id, None)
                else:
                    self._lock_count[session_id] = count - 1


session_lock_manager = SessionLockManager()
