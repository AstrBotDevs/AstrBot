from __future__ import annotations

import asyncio
import importlib

import pytest

from astrbot_sdk._internal.testing_support import (
    MockCapabilityRouter,
    MockContext,
    MockMessageEvent,
    MockPeer,
)
from astrbot_sdk._internal.invocation_context import caller_plugin_scope
from astrbot_sdk.context import CancelToken, Context
from astrbot_sdk.events import MessageEvent
from astrbot_sdk.protocol.messages import InvokeMessage
from astrbot_sdk.runtime.handler_dispatcher import HandlerDispatcher
from astrbot_sdk.session_waiter import (
    SessionController,
    SessionWaiterManager,
    _mark_session_waiter_handler_task,
    _unmark_session_waiter_handler_task,
    session_waiter,
)

session_waiter_module = importlib.import_module("astrbot_sdk.session_waiter")


def _attach_waiter_manager(ctx: MockContext) -> SessionWaiterManager:
    manager = SessionWaiterManager(plugin_id=ctx.plugin_id, peer=ctx.peer)
    setattr(ctx.peer, "_session_waiter_manager", manager)
    return manager


@pytest.mark.asyncio
async def test_session_waiter_register_task_pattern_is_non_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = MockContext()
    manager = _attach_waiter_manager(ctx)
    warnings: list[tuple[object, ...]] = []
    received: list[str] = []

    monkeypatch.setattr(
        session_waiter_module.logger,
        "warning",
        lambda *args: warnings.append(args),
    )

    @session_waiter(timeout=30)
    async def waiter(
        controller: SessionController,
        event: MessageEvent,
    ) -> None:
        received.append(event.text)
        controller.stop()

    initial = MockMessageEvent(text="/bind", session_id="session-1", context=ctx)
    progress = ["before"]
    with caller_plugin_scope(ctx.plugin_id):
        background_task = await ctx.register_task(waiter(initial), "waiter:collect")
    progress.append("after")

    assert progress == ["before", "after"]
    assert not background_task.done()

    for _ in range(5):
        if manager.has_waiter(initial):
            break
        await asyncio.sleep(0)

    assert manager.has_waiter(initial)

    followup = MockMessageEvent(text="alice", session_id="session-1", context=ctx)
    await manager.dispatch(followup)
    await background_task

    assert received == ["alice"]
    assert not manager.has_waiter(initial)
    assert warnings == []


@pytest.mark.asyncio
async def test_session_waiter_warns_on_direct_await_in_handler_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ctx = MockContext()
    manager = _attach_waiter_manager(ctx)
    warnings: list[tuple[object, ...]] = []
    received: list[str] = []

    monkeypatch.setattr(
        session_waiter_module.logger,
        "warning",
        lambda *args: warnings.append(args),
    )

    @session_waiter(timeout=30)
    async def waiter(
        controller: SessionController,
        event: MessageEvent,
    ) -> None:
        received.append(event.text)
        controller.stop()

    initial = MockMessageEvent(text="/bind", session_id="session-2", context=ctx)

    async def direct_wait() -> None:
        current_task = asyncio.current_task()
        assert current_task is not None
        _mark_session_waiter_handler_task(current_task)
        try:
            await waiter(initial)
        finally:
            _unmark_session_waiter_handler_task(current_task)

    with caller_plugin_scope(ctx.plugin_id):
        wait_task = asyncio.create_task(direct_wait())

    for _ in range(5):
        if manager.has_waiter(initial):
            break
        await asyncio.sleep(0)

    assert manager.has_waiter(initial)

    followup = MockMessageEvent(text="bob", session_id="session-2", context=ctx)
    await manager.dispatch(followup)
    await wait_task

    assert received == ["bob"]
    assert warnings == [
        (
            "Direct await on session_waiter blocks the current handler dispatch; "
            'prefer `await ctx.register_task(waiter(...), "...")`: '
            "plugin_id={} session_key={}",
            "test-plugin",
            "session-2",
        )
    ]


@pytest.mark.asyncio
async def test_session_waiter_warns_on_direct_await_in_redispatched_waiter_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    peer = MockPeer(MockCapabilityRouter())
    dispatcher = HandlerDispatcher(plugin_id="test-plugin", peer=peer, handlers=[])
    ctx = Context(peer=peer, plugin_id="test-plugin")
    warnings: list[tuple[object, ...]] = []
    received: list[tuple[str, str]] = []

    monkeypatch.setattr(
        session_waiter_module.logger,
        "warning",
        lambda *args: warnings.append(args),
    )

    @session_waiter(timeout=30)
    async def second_wait(
        controller: SessionController,
        event: MessageEvent,
    ) -> None:
        received.append(("second", event.text))
        controller.stop()

    @session_waiter(timeout=30)
    async def first_wait(
        controller: SessionController,
        event: MessageEvent,
    ) -> None:
        received.append(("first", event.text))
        await second_wait(event)
        controller.stop()

    initial_event = MessageEvent.from_payload(
        {
            "type": "message",
            "event_type": "message",
            "text": "/bind",
            "session_id": "session-redispatch",
            "user_id": "tester",
            "platform": "test",
            "platform_id": "test",
            "message_type": "private",
            "raw": {"event_type": "message"},
        },
        context=ctx,
    )
    with caller_plugin_scope(ctx.plugin_id):
        waiter_task = await ctx.register_task(first_wait(initial_event), "waiter:first")

    for _ in range(10):
        if dispatcher.has_active_waiter(initial_event):
            break
        await asyncio.sleep(0)

    redispatch_task = asyncio.create_task(
        dispatcher.invoke(
            InvokeMessage(
                id="req-session-waiter-1",
                capability="handler.invoke",
                input={
                    "handler_id": "__sdk_session_waiter__",
                    "event": {
                        **initial_event.to_payload(),
                        "text": "alice",
                    },
                    "args": {},
                },
            ),
            CancelToken(),
        )
    )

    for _ in range(10):
        if any(
            args and str(args[0]).startswith("Direct await on session_waiter")
            for args in warnings
        ):
            break
        await asyncio.sleep(0)

    assert redispatch_task.done() is False
    redispatch_task.cancel()
    waiter_task.cancel()
    await asyncio.gather(redispatch_task, waiter_task, return_exceptions=True)

    assert received == [("first", "alice")]
    assert any(
        args
        == (
            "Direct await on session_waiter blocks the current handler dispatch; "
            'prefer `await ctx.register_task(waiter(...), "...")`: '
            "plugin_id={} session_key={}",
            "test-plugin",
            "session-redispatch",
        )
        for args in warnings
    )
