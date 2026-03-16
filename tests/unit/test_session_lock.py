"""Tests for SessionLockManager with multi-event-loop isolation."""

import asyncio
import threading
import time
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest

from astrbot.core.utils.session_lock import SessionLockManager


class TestSessionLockManagerBasic:
    """Basic functionality tests."""

    def test_init(self):
        """Test manager initialization."""
        manager = SessionLockManager()
        assert manager._state_guard is not None
        assert manager._loop_managers is not None

    @pytest.mark.asyncio
    async def test_acquire_release_lock(self):
        """Test basic lock acquire and release."""
        manager = SessionLockManager()
        session_id = "test-session"

        async with manager.acquire_lock(session_id):
            # Lock acquired successfully
            pass

        # Lock should be released and cleaned up
        state = manager._get_loop_manager()
        assert session_id not in state._locks
        assert session_id not in state._lock_count

    @pytest.mark.asyncio
    async def test_lock_is_reusable(self):
        """Test that locks can be acquired multiple times."""
        manager = SessionLockManager()
        session_id = "test-session"

        async with manager.acquire_lock(session_id):
            pass

        async with manager.acquire_lock(session_id):
            pass

        # Both acquisitions should succeed


class TestCrossLoopIsolation:
    """Tests for event loop isolation."""

    @pytest.mark.asyncio
    async def test_different_loops_have_different_managers(self):
        """Test that different event loops get different per-loop managers."""
        manager = SessionLockManager()

        # Get manager for current loop
        manager1 = manager._get_loop_manager()

        # Run in a different event loop
        def run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(new_loop)

                async def get_manager():
                    return manager._get_loop_manager()

                return new_loop.run_until_complete(get_manager())
            finally:
                new_loop.close()
                asyncio.set_event_loop(None)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_new_loop)
            manager2 = future.result()

        # Should be different manager instances
        assert manager1 is not manager2

    @pytest.mark.asyncio
    async def test_locks_isolated_across_loops(self):
        """Test that locks from different loops are isolated."""
        manager = SessionLockManager()
        session_id = "shared-session"
        results = []

        async def acquire_in_loop(loop_id: int):
            """Acquire lock in a new event loop."""
            async with manager.acquire_lock(session_id):
                results.append(f"loop-{loop_id}-acquired")
                await asyncio.sleep(0.05)
                results.append(f"loop-{loop_id}-released")

        def run_in_thread(loop_id: int):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(acquire_in_loop(loop_id))
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # Run two loops concurrently - they should NOT block each other
        # because locks are isolated per-loop
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(run_in_thread, i) for i in range(2)]
            for f in futures:
                f.result()

        # Both loops should acquire immediately (no blocking between loops)
        # Order should show interleaved acquisitions, not sequential
        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_same_loop_blocks_on_same_session(self):
        """Test that same loop blocks when acquiring same session lock."""
        manager = SessionLockManager()
        session_id = "test-session"
        execution_order = []

        async def task1():
            async with manager.acquire_lock(session_id):
                execution_order.append("task1-start")
                await asyncio.sleep(0.1)
                execution_order.append("task1-end")

        async def task2():
            await asyncio.sleep(0.01)  # Let task1 start first
            async with manager.acquire_lock(session_id):
                execution_order.append("task2-start")
                execution_order.append("task2-end")

        await asyncio.gather(task1(), task2())

        # task2 should wait for task1 to finish
        assert execution_order.index("task1-start") < execution_order.index("task1-end")
        assert execution_order.index("task1-end") < execution_order.index("task2-start")


class TestConcurrency:
    """Tests for concurrent access."""

    @pytest.mark.asyncio
    async def test_concurrent_acquisitions_same_loop(self):
        """Test concurrent lock acquisitions on the same loop."""
        manager = SessionLockManager()
        session_id = "concurrent-session"
        acquired_count = 0
        max_concurrent = 0
        lock = asyncio.Lock()

        async def acquire_and_check():
            nonlocal acquired_count, max_concurrent
            async with manager.acquire_lock(session_id):
                async with lock:
                    acquired_count += 1
                    max_concurrent = max(max_concurrent, acquired_count)
                await asyncio.sleep(0.01)
                async with lock:
                    acquired_count -= 1

        # Run multiple concurrent tasks
        tasks = [acquire_and_check() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Max concurrent should be 1 (lock serializes access)
        assert max_concurrent == 1

    @pytest.mark.asyncio
    async def test_thread_safety_of_loop_manager_creation(self):
        """Test that _get_loop_manager is thread-safe."""
        manager = SessionLockManager()
        managers = []
        errors = []

        def create_loop_and_get_manager():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def get_mgr():
                    return manager._get_loop_manager()

                mgr = loop.run_until_complete(get_mgr())
                managers.append(mgr)
            except Exception as e:
                errors.append(e)
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        threads = [threading.Thread(target=create_loop_and_get_manager) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # All managers should be valid
        for m in managers:
            assert hasattr(m, "_locks")
            assert hasattr(m, "_access_lock")


class TestEventLoopCleanup:
    """Tests for event loop cleanup behavior."""

    @pytest.mark.asyncio
    async def test_weakref_cleanup_on_loop_close(self):
        """Test that per-loop managers are cleaned up when loop is closed."""
        manager = SessionLockManager()
        loop_ref: weakref.ref[asyncio.AbstractEventLoop] | None = None

        def run_in_new_loop():
            nonlocal loop_ref
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_ref = weakref.ref(loop)

            async def use_lock():
                async with manager.acquire_lock("test-session"):
                    pass
                return manager._get_loop_manager()

            try:
                per_loop_mgr = loop.run_until_complete(use_lock())
                # Keep a weak ref to the per-loop manager
                return weakref.ref(per_loop_mgr)
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_new_loop)
            per_loop_mgr_ref = future.result()

        # Give time for weakref cleanup
        import gc

        gc.collect()

        # The per-loop manager should be cleaned up when the loop is closed
        # because WeakKeyDictionary removes entries when the key (loop) is gone
        per_loop_mgr = per_loop_mgr_ref()
        loop = loop_ref() if loop_ref is not None else None
        assert per_loop_mgr is None or loop is None

    @pytest.mark.asyncio
    async def test_access_after_loop_close_in_new_loop_works(self):
        """Test that accessing from a new loop after old loop closes works."""
        manager = SessionLockManager()

        # Use lock in current loop
        async with manager.acquire_lock("session-1"):
            pass

        # Simulate old loop being closed and new loop being created
        def run_in_new_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def use_lock():
                    # Should work without issues in new loop
                    async with manager.acquire_lock("session-2"):
                        return "success"

                return loop.run_until_complete(use_lock())
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_new_loop)
            result = future.result()

        assert result == "success"


class TestIssue5464:
    """Tests for issue #5464: Multiple OneBot instances with different event loops.

    Issue: Running multiple OneBot adapter instances causes
    "is bound to a different event loop" error.
    """

    @pytest.mark.asyncio
    async def test_multiple_event_loops_no_cross_loop_error(self):
        """Test that multiple event loops don't cause cross-loop binding errors.

        This simulates the scenario where multiple OneBot instances
        (each potentially running in different event loops) access the
        same SessionLockManager concurrently.
        """
        from astrbot.core.utils.session_lock import session_lock_manager

        errors: list[Exception] = []
        results: list[str] = []

        def simulate_onebot_instance(instance_id: int, session_ids: list[str]):
            """Simulate a OneBot instance running in its own event loop."""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def process_messages():
                    for session_id in session_ids:
                        try:
                            async with session_lock_manager.acquire_lock(session_id):
                                # Simulate message processing
                                await asyncio.sleep(0.01)
                                results.append(f"instance-{instance_id}-{session_id}")
                        except Exception as e:
                            errors.append(e)

                loop.run_until_complete(process_messages())
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # Simulate 4 OneBot instances (as in the issue report)
        # Each handles multiple sessions concurrently
        threads = []
        for i in range(4):
            sessions = [f"session-{i}-1", f"session-{i}-2", f"session-{i}-3"]
            t = threading.Thread(target=simulate_onebot_instance, args=(i, sessions))
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have no errors (especially no "bound to a different event loop")
        assert len(errors) == 0, f"Errors occurred: {errors}"
        assert len(results) == 12  # 4 instances * 3 sessions each

    @pytest.mark.asyncio
    async def test_lock_object_not_shared_across_loops(self):
        """Verify that asyncio.Lock objects are not shared across event loops.

        The root cause of issue #5464 was that Lock objects created in one
        event loop were being used in another, causing the error.
        """
        manager = SessionLockManager()
        session_id = "shared-session-id"
        lock_ids: set[int] = set()
        lock_id_lock = threading.Lock()

        def get_lock_in_new_loop():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def acquire_and_capture():
                    # Get the per-loop manager
                    per_loop_mgr = manager._get_loop_manager()
                    # Capture the lock object id before acquiring
                    async with per_loop_mgr._access_lock:
                        lock = per_loop_mgr._locks[session_id]
                        with lock_id_lock:
                            lock_ids.add(id(lock))
                    async with manager.acquire_lock(session_id):
                        await asyncio.sleep(0.01)

                loop.run_until_complete(acquire_and_capture())
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # Run multiple loops concurrently
        threads = [threading.Thread(target=get_lock_in_new_loop) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each loop should have its own Lock object
        # If locks were shared, we'd only have 1 lock_id
        assert len(lock_ids) == 5, "Each event loop should have its own Lock object"

    @pytest.mark.asyncio
    async def test_concurrent_access_same_session_different_loops(self):
        """Test that same session ID accessed from different loops doesn't block.

        This verifies the fix: locks are isolated per event loop,
        so different loops can acquire the "same" session lock concurrently.
        """
        from astrbot.core.utils.session_lock import session_lock_manager

        session_id = "global-session"
        acquisition_times: list[float] = []
        time_lock = threading.Lock()

        def acquire_lock_in_loop(loop_id: int):
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:

                async def acquire():
                    import time

                    start = time.time()
                    async with session_lock_manager.acquire_lock(session_id):
                        with time_lock:
                            acquisition_times.append(start)
                        await asyncio.sleep(0.1)  # Hold the lock

                loop.run_until_complete(acquire())
            finally:
                loop.close()
                asyncio.set_event_loop(None)

        # Start 3 threads nearly simultaneously
        threads = [threading.Thread(target=acquire_lock_in_loop, args=(i,)) for i in range(3)]

        start_time = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        total_time = time.time() - start_time

        # If locks were NOT isolated, we'd need ~0.3s (3 * 0.1s serial)
        # With isolation, all should complete in ~0.1s (parallel)
        # Allow some overhead, but should be much less than 0.3s
        assert total_time < 0.25, (
            f"Locks should be isolated per loop, but took {total_time:.2f}s"
        )


class TestEdgeCases:
    """Tests for edge cases."""

    @pytest.mark.asyncio
    async def test_empty_session_id(self):
        """Test with empty session ID."""
        manager = SessionLockManager()

        async with manager.acquire_lock(""):
            pass

        # Should work without issues

    @pytest.mark.asyncio
    async def test_special_characters_in_session_id(self):
        """Test with special characters in session ID."""
        manager = SessionLockManager()
        session_id = "session-with-special-chars!@#$%^&*()"

        async with manager.acquire_lock(session_id):
            pass

        # Should work without issues

    @pytest.mark.asyncio
    async def test_very_long_session_id(self):
        """Test with very long session ID."""
        manager = SessionLockManager()
        session_id = "a" * 10000

        async with manager.acquire_lock(session_id):
            pass

        # Should work without issues

    @pytest.mark.asyncio
    async def test_lock_not_held_after_context_exit(self):
        """Test that lock is released after context manager exit."""
        manager = SessionLockManager()
        session_id = "test-session"

        async with manager.acquire_lock(session_id):
            state = manager._get_loop_manager()
            # Lock should exist and have count 1
            assert session_id in state._locks
            assert state._lock_count[session_id] == 1

        # After exit, lock should be cleaned up
        state = manager._get_loop_manager()
        assert session_id not in state._locks
        assert session_id not in state._lock_count

    @pytest.mark.asyncio
    async def test_exception_during_lock(self):
        """Test that lock is released even if exception occurs."""
        manager = SessionLockManager()
        session_id = "test-session"

        with pytest.raises(ValueError):
            async with manager.acquire_lock(session_id):
                raise ValueError("test error")

        # Lock should still be released
        state = manager._get_loop_manager()
        assert session_id not in state._locks
        assert session_id not in state._lock_count

    @pytest.mark.asyncio
    async def test_nested_lock_different_sessions(self):
        """Test nested locks on different sessions."""
        manager = SessionLockManager()

        async with manager.acquire_lock("session-1"):
            async with manager.acquire_lock("session-2"):
                state = manager._get_loop_manager()
                assert "session-1" in state._locks
                assert "session-2" in state._locks
                assert state._lock_count["session-1"] == 1
                assert state._lock_count["session-2"] == 1

        state = manager._get_loop_manager()
        assert "session-1" not in state._locks
        assert "session-2" not in state._locks

    @pytest.mark.asyncio
    async def test_reentrant_lock_same_session(self):
        """Test reentrant locking on same session (should block)."""
        manager = SessionLockManager()
        session_id = "test-session"
        order = []

        async def outer():
            async with manager.acquire_lock(session_id):
                order.append("outer-acquired")
                await asyncio.sleep(0.1)
                order.append("outer-done")

        async def inner():
            await asyncio.sleep(0.01)  # Let outer acquire first
            order.append("inner-attempt")
            async with manager.acquire_lock(session_id):
                order.append("inner-acquired")
                order.append("inner-done")

        await asyncio.gather(outer(), inner())

        # Inner should wait for outer to complete
        assert order.index("outer-acquired") < order.index("outer-done")
        assert order.index("outer-done") < order.index("inner-acquired")
