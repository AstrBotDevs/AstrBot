"""Dispatch failures and logging retain observable behavior at boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.core import event_bus as event_bus_module
from astrbot.core.event_bus import EventBus
from astrbot.core.message.components import Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


@pytest.fixture
def make_event():
    def create(text="message", sender="Alice", session="room", platform="adapter"):
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.sender = MessageMember(user_id="user-123", nickname=sender)
        message.self_id = "self"
        message.session_id = session
        message.message = [Plain(text)]
        message.message_str = text
        message.raw_message = text
        return AstrMessageEvent(
            text,
            message,
            PlatformMetadata(name="test", description="Test", id=platform),
            session,
        )

    return create


async def dispatch_until(bus, completed):
    task = asyncio.create_task(bus.dispatch())
    try:
        await asyncio.wait_for(completed.wait(), 2)
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_scheduler_failure_is_reported_and_following_event_still_completes(
    make_event, monkeypatch
):
    processed = asyncio.Event()
    first = make_event("fail")
    second = make_event("succeed")
    failure = RuntimeError("pipeline failed")

    async def execute(event):
        if event is first:
            raise failure
        processed.set()

    scheduler = SimpleNamespace(
        ctx=SimpleNamespace(astrbot_config={}), execute=AsyncMock(side_effect=execute)
    )
    manager = SimpleNamespace(
        get_conf_info=Mock(return_value={"id": "main", "name": "Main"})
    )
    logger = Mock()
    monkeypatch.setattr(event_bus_module, "logger", logger)
    bus = EventBus(asyncio.Queue(), {"main": scheduler}, manager)
    await bus.event_queue.put(first)
    await bus.event_queue.put(second)
    await dispatch_until(bus, processed)

    assert [call.args[0] for call in scheduler.execute.await_args_list] == [
        first,
        second,
    ]
    logger.error.assert_called_once_with("Pipeline task failed.", exc_info=failure)
    assert bus._pending_tasks == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_scheduler", [None, False])
async def test_missing_scheduler_is_logged_without_blocking_later_routed_events(
    make_event, monkeypatch, missing_scheduler
):
    processed = asyncio.Event()

    async def execute(_event):
        processed.set()

    scheduler = SimpleNamespace(
        ctx=SimpleNamespace(astrbot_config={}), execute=AsyncMock(side_effect=execute)
    )
    manager = SimpleNamespace(
        get_conf_info=Mock(
            side_effect=[
                {"id": "orphan", "name": "Orphan"},
                {"id": "main", "name": "Main"},
            ]
        )
    )
    mapping = {"main": scheduler}
    if missing_scheduler is None:
        mapping["orphan"] = None
    logger = Mock()
    monkeypatch.setattr(event_bus_module, "logger", logger)
    bus = EventBus(asyncio.Queue(), mapping, manager)
    orphan = make_event("orphan")
    routed = make_event("routed")
    await bus.event_queue.put(orphan)
    await bus.event_queue.put(routed)
    await dispatch_until(bus, processed)

    scheduler.execute.assert_awaited_once_with(routed)
    logger.error.assert_called_once()
    assert "orphan" in logger.error.call_args.args[0]
    assert bus.event_queue.empty()


@pytest.mark.asyncio
async def test_missing_profile_name_uses_the_profile_identifier(
    make_event, monkeypatch
):
    processed = asyncio.Event()

    async def execute(_event):
        processed.set()

    scheduler = SimpleNamespace(
        ctx=SimpleNamespace(astrbot_config={}), execute=AsyncMock(side_effect=execute)
    )
    manager = SimpleNamespace(get_conf_info=Mock(return_value={"id": "profile-id"}))
    bus = EventBus(asyncio.Queue(), {"profile-id": scheduler}, manager)
    log_event = Mock()
    monkeypatch.setattr(bus, "_print_event", log_event)
    event = make_event(session="")
    await bus.event_queue.put(event)
    await dispatch_until(bus, processed)

    manager.get_conf_info.assert_called_once_with("adapter:FriendMessage:")
    scheduler.execute.assert_awaited_once_with(event)
    log_event.assert_called_once_with(event, "profile-id")


@pytest.mark.parametrize("sender", [None, "", "Alice"])
def test_event_log_contains_sender_and_structured_platform_fields(
    make_event, monkeypatch, sender
):
    event = make_event("Hello", sender=sender)
    logger = Mock()
    monkeypatch.setattr(event_bus_module, "logger", logger)
    bus = EventBus(asyncio.Queue(), {}, SimpleNamespace())
    bus._print_event(event, "Main")
    expected_sender = "Alice/user-123" if sender else "user-123"
    logger.info.assert_called_once_with(
        f"[Main] [adapter(test)] {expected_sender}: Hello",
        extra={
            "category": "user_chat",
            "platform_id": "adapter",
            "platform_type": "test",
        },
    )


def test_non_message_event_keeps_its_log_category_and_literal_characters(
    make_event, monkeypatch
):
    event = make_event("Hello\nWorld", sender="User{}|", platform="test@#$")
    event.event_kind = "cron"
    logger = Mock()
    monkeypatch.setattr(event_bus_module, "logger", logger)
    bus = EventBus(asyncio.Queue(), {}, SimpleNamespace())
    bus._print_event(event, "Config[1]")
    logger.info.assert_called_once_with(
        "[Config[1]] [test@#$(test)] User{}|/user-123: Hello\nWorld",
        extra={"category": "cron", "platform_id": "test@#$", "platform_type": "test"},
    )
