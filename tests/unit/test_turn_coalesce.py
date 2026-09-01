"""Turn coalescing: discard-on-command, waiter bypass, forged flush, cancel."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.pipeline.turn_coalesce.stage import TurnCoalesceStage
from astrbot.core.pipeline.turn_router import (
    MANAGER_FLUSH_TOKEN,
    is_manager_flush,
    strip_inbound_flush_flags,
)
from astrbot.core.pipeline.turn_window import TurnWindowManager
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.platform.sources.webchat.webchat_event import WebChatMessageEvent
from astrbot.core.webchat.queue_manager import WebChatQueueManager


def _event(text: str, *, message_id: str = "1", extras=None) -> AstrMessageEvent:
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "bot"
    message.session_id = "user"
    message.message_id = message_id
    message.sender = MessageMember("user", "user")
    message.message = []
    message.message_str = text
    event = AstrMessageEvent(
        text,
        message,
        PlatformMetadata(name="test", description="test", id="test"),
        "user",
    )
    if extras:
        for key, value in extras.items():
            event.set_extra(key, value)
    return event


@pytest.mark.asyncio
async def test_command_discards_buffer_without_flush():
    queued: list[AstrMessageEvent] = []
    manager = TurnWindowManager(lambda event: queued.append(event) or True)
    first = _event("hello", message_id="a")
    first.set_extra("should_run_llm", True)
    manager.accept(first, wait_seconds=10, max_total_seconds=12)
    command = _event("/help", message_id="b")
    command.set_extra("should_run_command", True)
    manager.discard(command)
    await asyncio.sleep(0)
    assert queued == []
    assert manager.has_open_window(manager.window_key(first)) is False


@pytest.mark.asyncio
async def test_recall_clears_empty_window():
    manager = TurnWindowManager(lambda event: True)
    fragment = _event("hello", message_id="mid-1")
    manager.accept(fragment, wait_seconds=10, max_total_seconds=12)
    manager.recall("mid-1")
    assert manager.has_open_window(manager.window_key(fragment)) is False


@pytest.mark.asyncio
async def test_waiter_bypasses_coalesce():
    stage = TurnCoalesceStage()
    dispatched = []

    async def dispatch(event):
        dispatched.append(event)
        return True

    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "inbound_coalesce": {"enable": True, "private": True, "wait_seconds": 2}
            },
            execution_context=SimpleNamespace(
                session_waiter_registry=SimpleNamespace(dispatch=dispatch),
                turn_window_manager=TurnWindowManager(lambda event: True),
            ),
        )
    )
    event = _event("hello")
    event.set_extra("should_run_llm", True)
    await stage.process(event)
    assert dispatched == [event]
    assert event.is_stopped() is True


@pytest.mark.asyncio
async def test_flush_enqueues_once():
    queued: list[AstrMessageEvent] = []
    manager = TurnWindowManager(lambda event: queued.append(event) or True)
    first = _event("one", message_id="1")
    second = _event("two", message_id="2")
    manager.accept(first, wait_seconds=0.01, max_total_seconds=1)
    manager.accept(second, wait_seconds=0.01, max_total_seconds=1)
    await asyncio.sleep(0.05)
    assert len(queued) == 1
    flush = queued[0]
    assert flush.message_str == "one\ntwo"
    assert flush.message_obj.message_id == "2"
    assert is_manager_flush(flush._extras) is True


def test_forged_flush_is_stripped():
    extras = {
        "turn_flush": True,
        "route_kind": "turn_flush",
        MANAGER_FLUSH_TOKEN: "forged",
    }
    strip_inbound_flush_flags(extras)
    assert is_manager_flush(extras) is False
    assert "turn_flush" not in extras


@pytest.mark.asyncio
async def test_cancel_does_not_leak_tasks():
    manager = TurnWindowManager(lambda event: True)
    event = _event("hello")
    manager.accept(event, wait_seconds=30, max_total_seconds=30)
    await manager.terminate()
    assert manager._windows == {}
    assert manager._tasks == set() or all(task.done() for task in manager._tasks)


@pytest.mark.asyncio
async def test_coalesce_stage_buffers_private_llm_when_enabled():
    queued: list = []
    manager = TurnWindowManager(lambda event: queued.append(event) or True)
    stage = TurnCoalesceStage()
    await stage.initialize(
        SimpleNamespace(
            astrbot_config={
                "inbound_coalesce": {
                    "enable": True,
                    "private": True,
                    "wait_seconds": 2.0,
                    "max_total_seconds": 12.0,
                }
            },
            execution_context=SimpleNamespace(
                session_waiter_registry=SimpleNamespace(
                    dispatch=AsyncMock(return_value=False)
                ),
                turn_window_manager=manager,
            ),
        )
    )
    event = _event("hello")
    event.set_extra("should_run_llm", True)
    await stage.process(event)
    assert event.is_stopped() is True
    assert event.get_extra("skip_empty_completion") is True
    assert manager.has_open_window(manager.window_key(event)) is True
    assert queued == []
    await manager.terminate()


@pytest.mark.asyncio
async def test_flush_clones_webchat_event_without_reinvoking_constructor():
    queued: list[AstrMessageEvent] = []
    manager = TurnWindowManager(lambda event: queued.append(event) or True)
    queue_manager = WebChatQueueManager()
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.self_id = "webchat"
    message.session_id = "webchat!astrbot!conv-1"
    message.message_id = "req-1"
    message.sender = MessageMember("astrbot", "astrbot")
    message.message = []
    message.message_str = "hello"
    event = WebChatMessageEvent(
        "hello",
        message,
        PlatformMetadata(name="webchat", description="webchat", id="webchat"),
        "webchat!astrbot!conv-1",
        queue_manager,
        Path("unused-attachments"),
    )
    event.set_extra("should_run_llm", True)

    manager.accept(event, wait_seconds=0.01, max_total_seconds=1)
    await asyncio.sleep(0.05)

    assert len(queued) == 1
    flush = queued[0]
    assert isinstance(flush, WebChatMessageEvent)
    assert flush is not event
    assert flush._webchat_queue_manager is queue_manager
    assert flush._attachments_dir == Path("unused-attachments")
    assert flush.message_str == "hello"
    assert is_manager_flush(flush._extras) is True
    await manager.terminate()
