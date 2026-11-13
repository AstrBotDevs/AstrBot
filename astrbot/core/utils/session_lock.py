import asyncio
import threading
import weakref
from collections import defaultdict
from contextlib import asynccontextmanager


class SessionLockTimeoutError(TimeoutError):
    """The session remained busy until the lock acquisition deadline."""


class _PerLoopSessionLockManager:
    """Per-event-loop session lock manager; keeps original simple semantics."""

    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._lock_count: dict[str, int] = defaultdict(int)
        self._access_lock = asyncio.Lock()

    @asynccontextmanager
    async def acquire_lock(self, session_id: str, timeout: float | None = None):
        async with self._access_lock:
            lock = self._locks[session_id]
            self._lock_count[session_id] += 1

        try:
            try:
                await asyncio.wait_for(lock.acquire(), timeout=timeout)
            except asyncio.TimeoutError as exc:
                raise SessionLockTimeoutError(
                    "Timed out waiting for session lock"
                ) from exc
            try:
                yield
            finally:
                lock.release()
        finally:
            async with self._access_lock:
                self._lock_count[session_id] -= 1
                if self._lock_count[session_id] == 0:
                    self._locks.pop(session_id, None)
                    self._lock_count.pop(session_id, None)


class SessionLockManager:
    """Thread-safe session lock manager with per-event-loop isolation."""

    def __init__(self) -> None:
        self._state_guard = threading.Lock()
        self._loop_managers: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, _PerLoopSessionLockManager
        ] = weakref.WeakKeyDictionary()

    def _get_loop_manager(self) -> _PerLoopSessionLockManager:
        """Get the lock manager for the current event loop."""
        loop = asyncio.get_running_loop()
        with self._state_guard:
            return self._loop_managers.setdefault(loop, _PerLoopSessionLockManager())

    @asynccontextmanager
    async def acquire_lock(self, session_id: str, timeout: float | None = None):
        """Serialize a session, optionally bounding only the wait for ownership.

        Args:
            session_id: Session whose operations must be serialized.
            timeout: Maximum acquisition wait in seconds, or None to wait indefinitely.

        Yields:
            Control while holding the session lock.

        Raises:
            SessionLockTimeoutError: If acquisition exceeds the timeout.
        """
        manager = self._get_loop_manager()
        async with manager.acquire_lock(session_id, timeout=timeout):
            yield


session_lock_manager = SessionLockManager()
