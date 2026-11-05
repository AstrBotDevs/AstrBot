"""Tests for turn-level delivery ownership across pipeline stages."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.pipeline.respond import stage as respond_stage
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    event_context,
)
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.star.context import Context
from astrbot.core.star.star_handler import EventType


def _make_event() -> AstrMessageEvent:
    """Build a wake event for delivery ownership tests."""
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.session_id = "session"
    message.sender = MessageMember(user_id="user", nickname="User")
    message.message = [Plain("hello")]
    event = AstrMessageEvent(
        "hello",
        message,
        PlatformMetadata(id="test", name="test", description="Test"),
        "session",
    )
    event.is_at_or_wake_command = True
    return event


@pytest.mark.asyncio
async def test_context_send_marks_only_the_current_event_session() -> None:
    """Successful direct sends claim delivery only for the active session."""
    event = _make_event()
    platform = SimpleNamespace(
        meta=lambda: SimpleNamespace(id="test"),
        send_by_session=AsyncMock(),
    )
    context = SimpleNamespace(
        platform_manager=SimpleNamespace(platform_insts=[platform]),
        get_config=lambda **_kwargs: {},
    )

    with event_context(event):
        assert await Context.send_message(
            context,
            event.unified_msg_origin,
            MessageChain([Plain("direct")]),
        )
        assert event.has_sent_to_user()

    other_event = _make_event()
    with event_context(other_event):
        assert await Context.send_message(
            context,
            "test:FriendMessage:other",
            MessageChain([Plain("other")]),
        )
        assert not other_event.has_sent_to_user()

    empty_event = _make_event()
    with event_context(empty_event):
        assert await Context.send_message(
            context,
            empty_event.unified_msg_origin,
            MessageChain(),
        )
        assert not empty_event.has_sent_to_user()


@pytest.mark.asyncio
async def test_process_stage_skips_default_agent_after_delivery_or_stop() -> None:
    """Delivered or explicitly stopped events must not resume the default agent."""
    event = _make_event()
    stage = ProcessStage()
    stage.ctx = SimpleNamespace(
        astrbot_config={"provider_settings": {"enable": True}},
    )
    calls = 0

    async def agent(_event):
        nonlocal calls
        calls += 1
        if False:
            yield

    stage.agent_sub_stage = SimpleNamespace(process=agent)

    event.mark_sent_to_user()
    async for _ in stage.process(event):
        pass
    assert calls == 0

    stopped_event = _make_event()
    stopped_event.stop_event()
    stopped_event.clear_result()
    async for _ in stage.process(stopped_event):
        pass
    assert calls == 0

    ordinary_event = _make_event()
    async for _ in stage.process(ordinary_event):
        pass
    assert calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("delivered", "hook_calls"), [(False, 0), (True, 1)])
async def test_empty_result_preserves_after_send_after_direct_delivery(
    monkeypatch,
    delivered: bool,
    hook_calls: int,
) -> None:
    """An empty result dispatches post-send hooks only after a real delivery."""
    event = _make_event()
    if delivered:
        event.mark_sent_to_user()
    event.set_result(MessageEventResult())
    call_hook = AsyncMock(return_value=False)
    monkeypatch.setattr(respond_stage, "call_event_hook", call_hook)
    stage = respond_stage.RespondStage()
    stage.config = {"provider_settings": {}}
    stage.platform_settings = {"path_mapping": []}
    stage.enable_seg = False

    await stage.process(event)

    assert call_hook.await_count == hook_calls
    if delivered:
        call_hook.assert_awaited_once_with(event, EventType.OnAfterMessageSentEvent)
        assert event.get_result() is None
