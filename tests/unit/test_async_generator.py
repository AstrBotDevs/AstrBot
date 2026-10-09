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


@pytest.mark.asyncio
async def test_close_waits_for_async_cleanup_in_owner_task():
    owners = []
    cleanup_started = asyncio.Event()
    release = asyncio.Event()

    async def source():
        owners.append(asyncio.current_task())
        try:
            yield "result"
        finally:
            cleanup_started.set()
            await release.wait()
            owners.append(asyncio.current_task())

    results = iterate_in_task(source())
    assert await anext(results) == "result"
    closing = asyncio.create_task(results.aclose())
    try:
        await asyncio.wait_for(cleanup_started.wait(), 1)
        assert not closing.done()
        release.set()
        await asyncio.wait_for(closing, 1)
        assert len(owners) == 2 and owners[0] is owners[1]
    finally:
        release.set()
        await asyncio.gather(closing, return_exceptions=True)


@pytest.mark.asyncio
async def test_empty_generator_finishes_without_pending_task():
    tasks = set(asyncio.all_tasks())

    async def source():
        if False:
            yield

    assert [value async for value in iterate_in_task(source())] == []
    assert not (set(asyncio.all_tasks()) - tasks)


@pytest.mark.asyncio
async def test_repeated_cancel_does_not_interrupt_owner_cleanup():
    tasks = set(asyncio.all_tasks())
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release = asyncio.Event()
    closed = []

    async def source():
        try:
            started.set()
            await asyncio.Future()
            yield "unreachable"
        finally:
            cleanup_started.set()
            await release.wait()
            closed.append("closed")

    results = iterate_in_task(source())
    pending = asyncio.create_task(anext(results))
    try:
        await asyncio.wait_for(started.wait(), 1)
        pending.cancel()
        await asyncio.wait_for(cleanup_started.wait(), 1)
        pending.cancel()
        await asyncio.sleep(0)
        assert not pending.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, 1)
        assert closed == ["closed"]
    finally:
        release.set()
        await asyncio.gather(pending, return_exceptions=True)
        await results.aclose()
    assert not (set(asyncio.all_tasks()) - tasks)


@pytest.mark.asyncio
async def test_generator_that_yields_after_cancel_is_still_closed():
    tasks = set(asyncio.all_tasks())
    started = asyncio.Event()
    closed = []

    async def source():
        try:
            started.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                yield "late result"
        finally:
            closed.append("closed")

    results = iterate_in_task(source())
    pending = asyncio.create_task(anext(results))
    try:
        await asyncio.wait_for(started.wait(), 1)
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, 0.1)
        assert closed == ["closed"]
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await results.aclose()
    assert not (set(asyncio.all_tasks()) - tasks)


@pytest.mark.asyncio
async def test_source_cancellation_reaches_consumer():
    error = asyncio.CancelledError("source cancelled itself")
    closed = []

    async def source():
        try:
            raise error
            yield
        finally:
            closed.append("closed")

    results = iterate_in_task(source())
    try:
        with pytest.raises(asyncio.CancelledError) as caught:
            await asyncio.wait_for(anext(results), 0.1)
        assert caught.value is error
        assert closed == ["closed"]
    finally:
        await results.aclose()


@pytest.mark.asyncio
async def test_source_error_is_delivered_after_cleanup():
    error = ValueError("source failure")
    cleanup = []

    async def source():
        try:
            raise error
            yield
        finally:
            await asyncio.sleep(0)
            cleanup.append("closed")

    results = iterate_in_task(source())
    try:
        with pytest.raises(ValueError) as caught:
            await anext(results)
        assert caught.value is error
        assert cleanup == ["closed"]
    finally:
        await results.aclose()


@pytest.mark.asyncio
async def test_cancel_with_queued_value_and_cleanup_error(monkeypatch):
    original_queue = asyncio.Queue
    pending = None
    queued = asyncio.Event()
    error = OSError("queued cleanup failure")

    class CancelAfterPut(original_queue):
        async def get(self):
            await asyncio.Future()

        async def put(self, item):
            if item[0]:
                pending.cancel()
                queued.set()
            await super().put(item)

    monkeypatch.setattr(
        "astrbot.core.utils.async_generator.asyncio.Queue", CancelAfterPut
    )

    async def source():
        try:
            yield "queued result"
        finally:
            raise error

    results = iterate_in_task(source())
    pending = asyncio.create_task(anext(results))
    try:
        await asyncio.wait_for(queued.wait(), 1)
        with pytest.raises(OSError) as caught:
            await asyncio.wait_for(pending, 0.1)
        assert caught.value is error
    finally:
        pending.cancel()
        await asyncio.gather(pending, return_exceptions=True)
        await results.aclose()
