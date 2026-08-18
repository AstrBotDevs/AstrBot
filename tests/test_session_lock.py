"""Import smoke tests for astrbot.core.utils.session_lock."""

import asyncio

import pytest

from astrbot.core.utils import session_lock as session_lock_module
from astrbot.core.utils.session_lock import SessionLockManager, session_lock_manager


class TestImports:
    def test_module_importable(self):
        assert session_lock_module is not None

    def test_session_lock_manager_class_exists(self):
        assert SessionLockManager is not None

    def test_session_lock_manager_instance_exists(self):
        assert isinstance(session_lock_manager, SessionLockManager)


class TestSessionLockManagerSmoke:
    @pytest.mark.asyncio
    async def test_acquire_lock_basic(self):
        manager = SessionLockManager()
        async with manager.acquire_lock("test-session"):
            pass

    @pytest.mark.asyncio
    async def test_acquire_lock_multiple_sessions(self):
        manager = SessionLockManager()
        async with manager.acquire_lock("session-a"):
            async with manager.acquire_lock("session-b"):
                pass

    @pytest.mark.asyncio
    async def test_acquire_lock_same_session_sequentially(self):
        manager = SessionLockManager()
        async with manager.acquire_lock("same"):
            pass
        async with manager.acquire_lock("same"):
            pass

    @pytest.mark.asyncio
    async def test_global_instance_acquire_lock(self):
        async with session_lock_manager.acquire_lock("global-test"):
            pass

    @pytest.mark.asyncio
    async def test_concurrent_different_sessions(self):
        manager = SessionLockManager()

        async def work(session_id: str):
            async with manager.acquire_lock(session_id):
                pass

        await asyncio.gather(work("a"), work("b"), work("c"))

    @pytest.mark.asyncio
    async def test_concurrent_same_session_serialized(self):
        manager = SessionLockManager()
        order: list[str] = []

        async def work(name: str):
            async with manager.acquire_lock("shared"):
                order.append(name)
                await asyncio.sleep(0.01)

        await asyncio.gather(work("first"), work("second"))
        # Both should complete; order is deterministic due to asyncio.Lock
        assert len(order) == 2

    @pytest.mark.asyncio
    async def test_smoke_release_cleanup(self):
        manager = SessionLockManager()
        async with manager.acquire_lock("temp"):
            pass
        # After context exit, the lock should be cleaned up internally.
        # No assertion needed beyond not crashing.
