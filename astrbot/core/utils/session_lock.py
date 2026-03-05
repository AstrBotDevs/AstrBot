import asyncio
import threading
import weakref
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field


@dataclass
class _LoopLockState:
    """单个事件循环的锁状态"""

    access_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    locks: dict[str, asyncio.Lock] = field(
        default_factory=lambda: defaultdict(asyncio.Lock)
    )
    lock_count: dict[str, int] = field(default_factory=lambda: defaultdict(int))


class SessionLockManager:
    def __init__(self) -> None:
        self._state_guard = threading.Lock()
        self._loop_states: weakref.WeakKeyDictionary[
            asyncio.AbstractEventLoop, _LoopLockState
        ] = weakref.WeakKeyDictionary()

    def _get_loop_state(self) -> _LoopLockState:
        """获取当前事件循环的锁状态，确保锁绑定到正确的 loop"""
        loop = asyncio.get_running_loop()
        with self._state_guard:
            return self._loop_states.setdefault(loop, _LoopLockState())

    @asynccontextmanager
    async def acquire_lock(self, session_id: str):
        state = self._get_loop_state()

        async with state.access_lock:
            lock = state.locks[session_id]
            state.lock_count[session_id] += 1

        try:
            async with lock:
                yield
        finally:
            async with state.access_lock:
                state.lock_count[session_id] -= 1
                if state.lock_count[session_id] == 0:
                    state.locks.pop(session_id, None)
                    state.lock_count.pop(session_id, None)


session_lock_manager = SessionLockManager()
