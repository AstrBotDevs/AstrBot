from __future__ import annotations

import asyncio

import pytest

from astrbot_sdk._internal.testing_support import MockContext


class RecordingLogger:
    def __init__(self) -> None:
        self.debug_calls: list[tuple[str, str, str]] = []
        self.exception_calls: list[tuple[str, str, str]] = []

    def debug(self, message: str, plugin_id: str, desc: str) -> None:
        self.debug_calls.append((message, plugin_id, desc))

    def exception(self, message: str, plugin_id: str, desc: str) -> None:
        self.exception_calls.append((message, plugin_id, desc))


@pytest.mark.asyncio
async def test_register_task_accepts_coroutine() -> None:
    ctx = MockContext()

    async def background() -> str:
        await asyncio.sleep(0)
        return "done"

    task = await ctx.register_task(background(), "coroutine")

    assert isinstance(task, asyncio.Task)
    assert await task == "done"


@pytest.mark.asyncio
async def test_register_task_wraps_future_inputs() -> None:
    ctx = MockContext()
    loop = asyncio.get_running_loop()
    future: asyncio.Future[str] = loop.create_future()

    task = await ctx.register_task(future, "future")
    future.set_result("done")

    assert isinstance(task, asyncio.Task)
    assert task is not future
    assert await task == "done"


@pytest.mark.asyncio
async def test_register_task_logs_cancel_once() -> None:
    logger = RecordingLogger()
    ctx = MockContext(logger=logger)
    started = asyncio.Event()

    async def background() -> None:
        started.set()
        await asyncio.Future()

    task = await ctx.register_task(background(), "cancelled")
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert logger.debug_calls == [
        (
            "SDK background task cancelled: plugin_id={} desc={}",
            "test-plugin",
            "cancelled",
        )
    ]
    assert logger.exception_calls == []


@pytest.mark.asyncio
async def test_register_task_logs_failures() -> None:
    logger = RecordingLogger()
    ctx = MockContext(logger=logger)

    async def background() -> None:
        raise RuntimeError("boom")

    task = await ctx.register_task(background(), "failing")

    with pytest.raises(RuntimeError, match="boom"):
        await task

    assert logger.debug_calls == []
    assert logger.exception_calls == [
        (
            "SDK background task failed: plugin_id={} desc={}",
            "test-plugin",
            "failing",
        )
    ]
