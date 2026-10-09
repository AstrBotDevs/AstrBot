"""Tests for demand-driven async generator task ownership."""

import asyncio
from contextvars import ContextVar

import anyio
import pytest

from astrbot.core.utils.async_generator import iterate_in_task


@pytest.mark.asyncio
@pytest.mark.parametrize("exit_mode", ["close", "exhaust", "error"])
async def test_owner_task_context_and_demand_are_preserved(exit_mode):
    tasks = set(asyncio.all_tasks())
    context = ContextVar("generator_context", default="caller")
    owners = []
    advanced = []
    error = ValueError("controlled generator failure")

    async def source():
        owners.append(asyncio.current_task())
        token = context.set("generator")
        try:
            with anyio.CancelScope():
                yield None
                advanced.append("next")
                owners.append(asyncio.current_task())
                if exit_mode == "error":
                    raise error
                yield error
        finally:
            await asyncio.sleep(0)
            owners.append(asyncio.current_task())
            context.reset(token)

    results = iterate_in_task(source())
    try:
        assert await anext(results) is None
        await asyncio.sleep(0)
        assert advanced == []
        assert context.get() == "caller"
        if exit_mode == "exhaust":
            assert await anext(results) is error
            with pytest.raises(StopAsyncIteration):
                await anext(results)
        elif exit_mode == "error":
            with pytest.raises(ValueError) as caught:
                await anext(results)
            assert caught.value is error
    finally:
        await results.aclose()
    assert all(owner is owners[0] for owner in owners)
    assert len(owners) == (2 if exit_mode == "close" else 3)
    assert not (set(asyncio.all_tasks()) - tasks)


@pytest.mark.asyncio
async def test_cancel_pending_read_waits_for_cleanup():
    tasks = set(asyncio.all_tasks())
    started = asyncio.Event()
    cleanup = []

    async def source():
        try:
            started.set()
            await asyncio.Future()
            yield "unreachable"
        finally:
            await asyncio.sleep(0)
            cleanup.append("closed")

    results = iterate_in_task(source())
    pending = asyncio.create_task(anext(results))
    try:
        await asyncio.wait_for(started.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await pending
        assert cleanup == ["closed"]
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await results.aclose()
    assert not (set(asyncio.all_tasks()) - tasks)


@pytest.mark.asyncio
async def test_cleanup_failure_is_not_hidden():
    error = OSError("controlled cleanup failure")

    async def source():
        try:
            yield "result"
        finally:
            raise error

    results = iterate_in_task(source())
    assert await anext(results) == "result"
    with pytest.raises(OSError) as caught:
        await results.aclose()
    assert caught.value is error


@pytest.mark.asyncio
async def test_exhaustion_waits_without_cancelling_cleanup():
    cleanup_started = asyncio.Event()
    release = asyncio.Event()
    closed = []

    async def source():
        try:
            yield "result"
        finally:
            cleanup_started.set()
            await release.wait()
            closed.append("closed")

    results = iterate_in_task(source())
    assert await anext(results) == "result"
    pending = asyncio.create_task(anext(results))
    try:
        await asyncio.wait_for(cleanup_started.wait(), 1)
        assert not pending.done()
        release.set()
        with pytest.raises(StopAsyncIteration):
            await asyncio.wait_for(pending, 1)
        assert closed == ["closed"]
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        await results.aclose()
