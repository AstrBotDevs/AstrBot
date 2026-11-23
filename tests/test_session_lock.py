"""Observable ordering, cancellation and reuse of per-session locks."""

import asyncio
from collections.abc import Coroutine

import pytest
import pytest_asyncio

from astrbot.core.utils.session_lock import SessionLockManager, session_lock_manager


@pytest_asyncio.fixture
async def spawn_task():
    tasks: list[asyncio.Task[None]] = []

    def spawn(coroutine: Coroutine[object, object, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(coroutine)
        tasks.append(task)
        return task

    try:
        yield spawn
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_same_session_holds_exclusive_access_until_owner_releases(spawn_task):
    manager = SessionLockManager()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_attempted = asyncio.Event()
    second_entered = asyncio.Event()
    order: list[str] = []

    async def first() -> None:
        async with manager.acquire_lock("shared"):
            order.append("first-enter")
            first_entered.set()
            await release_first.wait()
            order.append("first-leave")

    async def second() -> None:
        second_attempted.set()
        async with manager.acquire_lock("shared"):
            order.append("second-enter")
            second_entered.set()

    owner = spawn_task(first())
    async with asyncio.timeout(2):
        await first_entered.wait()
        waiter = spawn_task(second())
        await second_attempted.wait()
        assert not second_entered.is_set()
        release_first.set()
        await asyncio.gather(owner, waiter)

    assert order == ["first-enter", "first-leave", "second-enter"]


@pytest.mark.asyncio
async def test_different_sessions_enter_while_another_session_is_locked(spawn_task):
    manager = SessionLockManager()
    entered = asyncio.Event()

    async def other_session() -> None:
        async with manager.acquire_lock("other"):
            entered.set()

    async with manager.acquire_lock("busy"):
        other = spawn_task(other_session())
        async with asyncio.timeout(2):
            await entered.wait()
            await other


@pytest.mark.asyncio
async def test_cancelled_waiter_does_not_release_the_active_owner(spawn_task):
    manager = SessionLockManager()
    attempted = asyncio.Event()
    entered: list[str] = []

    async def waiter() -> None:
        attempted.set()
        async with manager.acquire_lock("shared"):
            entered.append("cancelled")

    async with manager.acquire_lock("shared"):
        waiting = spawn_task(waiter())
        async with asyncio.timeout(2):
            await attempted.wait()
            waiting.cancel()
            with pytest.raises(asyncio.CancelledError):
                await waiting
        assert entered == []

    async with asyncio.timeout(2):
        async with manager.acquire_lock("shared"):
            entered.append("replacement")
    assert entered == ["replacement"]


@pytest.mark.asyncio
async def test_exception_in_owner_releases_session_for_next_execution():
    manager = SessionLockManager()
    with pytest.raises(ValueError, match="failed execution"):
        async with manager.acquire_lock("shared"):
            raise ValueError("failed execution")

    async with asyncio.timeout(2):
        async with manager.acquire_lock("shared"):
            acquired = True
    assert acquired is True


def test_global_manager_can_be_reused_by_successive_event_loops():
    entered: list[int] = []

    async def acquire(index: int) -> None:
        async with session_lock_manager.acquire_lock("successive-loops"):
            entered.append(index)

    asyncio.run(acquire(1))
    asyncio.run(acquire(2))
    assert entered == [1, 2]
