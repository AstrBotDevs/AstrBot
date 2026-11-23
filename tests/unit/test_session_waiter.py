"""Tests for astrbot.core.utils.session_waiter.

These tests lock in the expected behavior of the session-waiter task-tracking
mechanism introduced in PR #9458: a handler task that is still running after a
timeout (or after being superseded by a second trigger) must be cancelled, and
the resulting ``asyncio.CancelledError`` must NOT be funneled into
``SessionController.stop(error)`` as if it were an ordinary handler exception.

The tests encode the *expected* behavior. They must not be weakened to satisfy
the current implementation.
"""

import asyncio
from contextlib import suppress
from unittest.mock import MagicMock

import pytest

from astrbot.core.utils.session_waiter import (
    FILTERS,
    USER_SESSIONS,
    DefaultSessionFilter,
    SessionWaiter,
)


def make_event(unified_msg_origin: str = "test_umo") -> MagicMock:
    """Build a minimal AstrMessageEvent mock for session_waiter tests."""
    event = MagicMock()
    event.unified_msg_origin = unified_msg_origin
    event.get_messages.return_value = []
    return event


async def _wait_for_session(session_id: str, timeout: float = 5.0) -> None:
    """Wait until ``session_id`` appears in USER_SESSIONS (register_wait started)."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while session_id not in USER_SESSIONS:
        if loop.time() >= deadline:
            raise AssertionError(
                f"Session {session_id!r} was not registered within {timeout}s"
            )
        await asyncio.sleep(0.01)


@pytest.fixture(autouse=True)
def reset_session_globals():
    """Clear module-level USER_SESSIONS / FILTERS before and after each test."""
    USER_SESSIONS.clear()
    FILTERS.clear()
    yield
    USER_SESSIONS.clear()
    FILTERS.clear()


class TestSessionWaiterBasicFlow:
    """基础流程：trigger 触发 handler 执行；handler 调 stop() 后 register_wait 返回。"""

    @pytest.mark.asyncio
    async def test_trigger_runs_handler_and_register_wait_returns(self):
        handler_executed = asyncio.Event()

        async def handler(controller, event):  # noqa: ARG001
            handler_executed.set()
            controller.stop()

        waiter = SessionWaiter(DefaultSessionFilter(), "session_basic", False)
        register_task = asyncio.create_task(waiter.register_wait(handler, timeout=30))
        await _wait_for_session("session_basic")

        event = make_event("session_basic")
        await SessionWaiter.trigger("session_basic", event)

        assert handler_executed.is_set(), "handler should have been executed by trigger"

        result = await asyncio.wait_for(register_task, timeout=5)
        assert register_task.done()
        assert not register_task.cancelled()
        assert result is None


class TestSessionWaiterDoubleTrigger:
    """重复 trigger 取消上一个仍在运行的 handler。"""

    @pytest.mark.asyncio
    async def test_second_trigger_cancels_previous_handler(self):
        first_handler_started = asyncio.Event()
        first_handler_cancelled = asyncio.Event()
        call_count = 0

        async def handler(controller, event):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                first_handler_started.set()
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    first_handler_cancelled.set()
                    raise
            else:
                controller.stop()

        waiter = SessionWaiter(DefaultSessionFilter(), "session_double", False)
        register_task = asyncio.create_task(waiter.register_wait(handler, timeout=30))
        await _wait_for_session("session_double")

        event1 = make_event("session_double")
        trigger1_task = asyncio.create_task(
            SessionWaiter.trigger("session_double", event1)
        )
        await asyncio.wait_for(first_handler_started.wait(), timeout=5)

        # Previous handler is still running -> second trigger must cancel it.
        event2 = make_event("session_double")
        await SessionWaiter.trigger("session_double", event2)

        await asyncio.wait_for(first_handler_cancelled.wait(), timeout=5)
        assert first_handler_cancelled.is_set(), (
            "previous handler task should have been cancelled by the second trigger"
        )

        # trigger1 was awaiting the cancelled task; it should swallow the
        # CancelledError and return cleanly.
        await asyncio.wait_for(trigger1_task, timeout=5)
        assert trigger1_task.done()
        assert not trigger1_task.cancelled()

        # Second handler called stop() -> register_wait returns normally.
        await asyncio.wait_for(register_task, timeout=5)
        assert register_task.done()
        assert not register_task.cancelled()


class TestSessionWaiterCleanupCancelsHandler:
    """超时/清理取消运行中的 handler。"""

    @pytest.mark.asyncio
    async def test_cleanup_cancels_running_handler(self):
        handler_started = asyncio.Event()
        handler_cancelled = asyncio.Event()

        async def handler(controller, event):  # noqa: ARG001
            handler_started.set()
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise

        waiter = SessionWaiter(DefaultSessionFilter(), "session_cleanup", False)
        register_task = asyncio.create_task(waiter.register_wait(handler, timeout=30))
        await _wait_for_session("session_cleanup")

        event = make_event("session_cleanup")
        trigger_task = asyncio.create_task(
            SessionWaiter.trigger("session_cleanup", event)
        )
        await asyncio.wait_for(handler_started.wait(), timeout=5)

        # Handler is running. _cleanup() is what register_wait calls on timeout
        # / finally; invoking it directly simulates that path.
        await waiter._cleanup()

        await asyncio.wait_for(handler_cancelled.wait(), timeout=5)
        assert handler_cancelled.is_set(), (
            "running handler task should be cancelled by _cleanup"
        )

        # trigger was awaiting the now-cancelled handler task; it returns.
        await asyncio.wait_for(trigger_task, timeout=5)
        assert trigger_task.done()
        assert not trigger_task.cancelled()

        # _cleanup set the future result -> register_wait completes.
        await asyncio.wait_for(register_task, timeout=5)
        assert register_task.done()
        assert not register_task.cancelled()


class TestSessionWaiterCancelledErrorHandling:
    """CancelledError 不被当作普通异常处理（PR 核心修复点）。

    当 handler 被取消时，CancelledError 不得通过 stop(e) 被当作普通异常设置到
    future 上。验证：stop() 从未被以 CancelledError 为参数调用；且若 future 已完成，
    其 exception() 绝不是 CancelledError。
    """

    def _install_stop_spy(self, waiter: SessionWaiter) -> list:
        """Record every error passed to SessionController.stop()."""
        original_stop = waiter.session_controller.stop
        stop_calls: list = []

        def stop_spy(error=None):
            stop_calls.append(error)
            return original_stop(error)

        waiter.session_controller.stop = stop_spy
        return stop_calls

    @pytest.mark.asyncio
    async def test_stop_not_called_with_cancelled_error_on_cleanup(self):
        handler_started = asyncio.Event()
        handler_cancelled = asyncio.Event()

        async def handler(controller, event):  # noqa: ARG001
            handler_started.set()
            try:
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise

        waiter = SessionWaiter(DefaultSessionFilter(), "session_cancel_cleanup", False)
        stop_calls = self._install_stop_spy(waiter)

        register_task = asyncio.create_task(waiter.register_wait(handler, timeout=30))
        await _wait_for_session("session_cancel_cleanup")

        event = make_event("session_cancel_cleanup")
        trigger_task = asyncio.create_task(
            SessionWaiter.trigger("session_cancel_cleanup", event)
        )
        await asyncio.wait_for(handler_started.wait(), timeout=5)

        await waiter._cleanup()
        await asyncio.wait_for(handler_cancelled.wait(), timeout=5)

        # Core: stop() must never receive a CancelledError.
        for err in stop_calls:
            assert not isinstance(err, asyncio.CancelledError), (
                f"stop() must not be called with CancelledError, got {err!r}"
            )

        # Core: a completed future must not carry a CancelledError.
        future = waiter.session_controller.future
        if future.done():
            exc = future.exception()
            assert not isinstance(exc, asyncio.CancelledError), (
                f"future exception must not be CancelledError, got {exc!r}"
            )

        await asyncio.wait_for(trigger_task, timeout=5)
        await asyncio.wait_for(register_task, timeout=5)

    @pytest.mark.asyncio
    async def test_stop_not_called_with_cancelled_error_on_double_trigger(self):
        first_handler_started = asyncio.Event()
        first_handler_cancelled = asyncio.Event()
        call_count = 0

        async def handler(controller, event):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                first_handler_started.set()
                try:
                    await asyncio.sleep(5)
                except asyncio.CancelledError:
                    first_handler_cancelled.set()
                    raise
            else:
                controller.stop()

        waiter = SessionWaiter(DefaultSessionFilter(), "session_cancel_dt", False)
        stop_calls = self._install_stop_spy(waiter)

        register_task = asyncio.create_task(waiter.register_wait(handler, timeout=30))
        await _wait_for_session("session_cancel_dt")

        event1 = make_event("session_cancel_dt")
        trigger1_task = asyncio.create_task(
            SessionWaiter.trigger("session_cancel_dt", event1)
        )
        await asyncio.wait_for(first_handler_started.wait(), timeout=5)

        event2 = make_event("session_cancel_dt")
        await SessionWaiter.trigger("session_cancel_dt", event2)
        await asyncio.wait_for(first_handler_cancelled.wait(), timeout=5)

        for err in stop_calls:
            assert not isinstance(err, asyncio.CancelledError), (
                f"stop() must not be called with CancelledError, got {err!r}"
            )

        future = waiter.session_controller.future
        if future.done():
            exc = future.exception()
            assert not isinstance(exc, asyncio.CancelledError), (
                f"future exception must not be CancelledError, got {exc!r}"
            )

        await asyncio.wait_for(trigger1_task, timeout=5)
        await asyncio.wait_for(register_task, timeout=5)


class TestSessionWaiterHandlerException:
    """handler 普通异常向上传播。"""

    @pytest.mark.asyncio
    async def test_handler_exception_propagates_to_register_wait(self):
        handler_executed = asyncio.Event()

        async def handler(controller, event):  # noqa: ARG001
            handler_executed.set()
            raise ValueError("handler error")

        waiter = SessionWaiter(DefaultSessionFilter(), "session_exc", False)
        register_task = asyncio.create_task(waiter.register_wait(handler, timeout=30))
        await _wait_for_session("session_exc")

        event = make_event("session_exc")
        await SessionWaiter.trigger("session_exc", event)

        assert handler_executed.is_set()

        # register_wait re-raises the ValueError surfaced via stop(e).
        with pytest.raises(ValueError, match="handler error"):
            await asyncio.wait_for(register_task, timeout=5)

        # The future itself carries the ValueError.
        assert waiter.session_controller.future.done()
        exc = waiter.session_controller.future.exception()
        assert isinstance(exc, ValueError)
        assert "handler error" in str(exc)
