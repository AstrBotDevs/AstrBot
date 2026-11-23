"""Dispatch real events and drain their owned tasks before shutdown returns."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from astrbot.core import event_bus as event_bus_module
from astrbot.core.event_bus import EventBus
from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


@pytest.fixture
def make_event():
    def create(platform_id="bot", session_id="room", text="message"):
        message = AstrBotMessage()
        message.type = MessageType.GROUP_MESSAGE
        message.self_id = platform_id
        message.sender = MessageMember(user_id="alice", nickname="Alice")
        message.group_id = session_id
        message.session_id = session_id
        message.message = [Plain(text)]
        message.message_str = text
        message.raw_message = text
        return AstrMessageEvent(
            text,
            message,
            PlatformMetadata(name="aiocqhttp", description="Test", id=platform_id),
            session_id,
        )

    return create


@pytest_asyncio.fixture
async def spawn_task():
    tasks = []

    def spawn(coroutine):
        task = asyncio.create_task(coroutine)
        tasks.append(task)
        return task

    yield spawn
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.fixture
def make_bus(monkeypatch):
    registry = SimpleNamespace(stop_platform=AsyncMock())
    monkeypatch.setattr(event_bus_module, "active_event_registry", registry)

    def create(execute, config=None):
        scheduler = SimpleNamespace(
            ctx=SimpleNamespace(astrbot_config=config or {}),
            execute=AsyncMock(side_effect=execute),
        )
        manager = SimpleNamespace(
            get_conf_info=Mock(return_value={"id": "main", "name": "Main"})
        )
        bus = EventBus(asyncio.Queue(), {"main": scheduler}, manager)
        return bus, scheduler, manager, registry

    return create


@pytest.mark.asyncio
async def test_dispatch_routes_again_after_finalizing_the_session(
    make_event, make_bus, spawn_task
):
    processed = asyncio.Event()

    async def execute(_event):
        processed.set()

    bus, original_scheduler, manager, _ = make_bus(
        execute, {"platform_settings": {"unique_session": True}}
    )
    isolated_scheduler = SimpleNamespace(
        ctx=SimpleNamespace(astrbot_config={}),
        execute=AsyncMock(side_effect=execute),
    )
    bus.pipeline_scheduler_mapping["isolated"] = isolated_scheduler
    manager.get_conf_info.side_effect = [
        {"id": "main", "name": "Main"},
        {"id": "isolated", "name": "Isolated"},
    ]
    event = make_event()
    await bus.event_queue.put(event)
    spawn_task(bus.dispatch())
    await asyncio.wait_for(processed.wait(), 2)

    assert [call.args[0] for call in manager.get_conf_info.call_args_list] == [
        "bot:GroupMessage:room",
        "bot:GroupMessage:alice_room",
    ]
    assert event.unified_msg_origin == "bot:GroupMessage:alice_room"
    assert event.get_extra("_session_isolated") is True
    original_scheduler.execute.assert_not_awaited()
    isolated_scheduler.execute.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_dispatch_cancellation_waits_for_child_cleanup_and_blocks_late_events(
    make_event, make_bus, spawn_task
):
    entered = asyncio.Event()
    cleanup_entered = asyncio.Event()
    allow_cleanup = asyncio.Event()
    cleaned = asyncio.Event()

    async def execute(_event):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleanup_entered.set()
            await allow_cleanup.wait()
            cleaned.set()

    bus, scheduler, _, _ = make_bus(execute)
    first = make_event(text="first")
    late = make_event(text="late")
    await bus.event_queue.put(first)
    dispatch = spawn_task(bus.dispatch())
    try:
        await asyncio.wait_for(entered.wait(), 2)
        dispatch.cancel()
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        assert not dispatch.done()
        assert not cleaned.is_set()
        await bus.event_queue.put(late)
        allow_cleanup.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(dispatch, 2)
    finally:
        allow_cleanup.set()

    assert cleaned.is_set()
    assert bus._pending_tasks == {}
    scheduler.execute.assert_awaited_once_with(first)
    assert bus.event_queue.get_nowait() is late
    await bus.dispatch()
    scheduler.execute.assert_awaited_once_with(first)


@pytest.mark.asyncio
async def test_stop_platform_drains_only_its_tasks_and_rejects_later_events(
    make_event, make_bus, spawn_task
):
    entered = {name: asyncio.Event() for name in ("bot", "bot-other")}
    cleaned = {name: asyncio.Event() for name in entered}
    cleanup_entered = asyncio.Event()
    allow_cleanup = asyncio.Event()
    marker_processed = asyncio.Event()

    async def execute(event):
        if event.message_str == "marker":
            marker_processed.set()
            return
        platform = event.get_platform_id()
        entered[platform].set()
        try:
            await asyncio.Event().wait()
        finally:
            if platform == "bot":
                cleanup_entered.set()
                await allow_cleanup.wait()
            cleaned[platform].set()

    bus, scheduler, _, registry = make_bus(execute)
    target = make_event("bot")
    other = make_event("bot-other")
    await bus.event_queue.put(target)
    await bus.event_queue.put(other)
    spawn_task(bus.dispatch())
    try:
        await asyncio.wait_for(
            asyncio.gather(*(signal.wait() for signal in entered.values())), 2
        )
        stopping = spawn_task(bus.stop_platform("bot"))
        await asyncio.wait_for(cleanup_entered.wait(), 2)
        assert not stopping.done()
        assert not cleaned["bot-other"].is_set()
        allow_cleanup.set()
        await asyncio.wait_for(stopping, 2)
        assert cleaned["bot"].is_set()
        assert not cleaned["bot-other"].is_set()

        late = make_event("bot", text="late")
        marker = make_event("bot-other", text="marker")
        await bus.event_queue.put(late)
        await bus.event_queue.put(marker)
        await asyncio.wait_for(marker_processed.wait(), 2)
        assert [call.args[0] for call in scheduler.execute.await_args_list] == [
            target,
            other,
            marker,
        ]
        registry.stop_platform.assert_awaited_once_with("bot")
    finally:
        allow_cleanup.set()


@pytest.mark.asyncio
async def test_stop_platform_retains_other_queued_events_in_their_original_order(
    make_event, make_bus
):
    bus, scheduler, _, registry = make_bus(AsyncMock())
    events = [
        make_event("bot"),
        make_event("bot-other", text="first retained"),
        make_event("BOT", text="second retained"),
        make_event("bot"),
    ]
    for event in events:
        await bus.event_queue.put(event)
    await bus.stop_platform("bot")
    assert [bus.event_queue.get_nowait(), bus.event_queue.get_nowait()] == events[1:3]
    assert bus.event_queue.empty()
    assert bus.stopped_platforms == {"bot"}
    scheduler.execute.assert_not_awaited()
    registry.stop_platform.assert_awaited_once_with("bot")
