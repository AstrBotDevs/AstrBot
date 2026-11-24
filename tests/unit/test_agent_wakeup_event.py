"""Tests for programmatic wakeup event send accounting."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot import logger
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.star.context import Context


@pytest.fixture
def wakeup_event(monkeypatch):
    """Create a real event with controlled transport and metric upload.

    Args:
        monkeypatch: Replaces network metric upload.

    Returns:
        Event, transport mock and metric mock.
    """
    send = AsyncMock(return_value=True)
    metric = AsyncMock()
    monkeypatch.setattr(
        "astrbot.core.platform.astr_message_event.Metric.upload", metric
    )
    event = AgentWakeupEvent(
        context=SimpleNamespace(send_message=send),
        session=MessageSession.from_str("test:FriendMessage:session-1"),
        platform_meta=PlatformMetadata(
            id="test", name="test-platform", description="Test"
        ),
        prompt="scheduled task",
        source="cron",
        source_id="job-1",
    )
    return event, send, metric


@pytest.mark.parametrize("source", ["cron", "background_task", "plugin"])
@pytest.mark.parametrize("message_type", list(MessageType))
def test_wakeup_keeps_target_identity_separate_from_its_source(source, message_type):
    """Keep target routing and permissions independent of the synthetic sender.

    Args:
        source: Mechanism initiating the wakeup.
        message_type: Message type belonging to the target session.
    """
    session = MessageSession("target", message_type, "target-session")
    metadata = PlatformMetadata(id="target", name="webchat", description="Target")
    event = AgentWakeupEvent(
        context=SimpleNamespace(),
        session=session,
        platform_meta=metadata,
        prompt="Continue the task.",
        source=source,
        source_id="source-id",
    )

    assert isinstance(event, AstrMessageEvent)
    assert event.session is session
    assert event.unified_msg_origin == str(session)
    assert event.get_message_type() == message_type
    assert event.platform_meta is event.platform is metadata
    assert event.get_platform_name() == "webchat"
    assert event.get_platform_id() == "target"
    assert event.source == source
    assert event.source_id == "source-id"
    assert event.message_str == event.message_obj.message_str == "Continue the task."
    assert event.get_messages()[0].text == "Continue the task."
    assert event.get_sender_id() == "astrbot"
    assert event.get_sender_name() == "System"
    assert event.role == "member"
    assert event.is_wake and event.is_at_or_wake_command
    assert event.get_extra("enable_streaming") is False


def test_wakeup_preserves_the_resolved_permission_role(wakeup_event):
    """Use the framework's explicit role independently of system sender identity.

    Args:
        wakeup_event: Event and controlled delivery services.
    """
    original, _, _ = wakeup_event
    event = AgentWakeupEvent(
        context=original.context_obj,
        session=original.session,
        platform_meta=original.platform_meta,
        prompt="Continue an authorized task.",
        source="background_task",
        role="admin",
    )
    assert event.role == "admin"
    assert event.get_sender_id() == original.get_sender_id()
    assert event.source_id is None


@pytest.mark.parametrize(
    ("source", "platform_id", "error"),
    [
        ("unsupported", "target", "Unsupported agent wakeup source"),
        ("plugin", "other", "metadata must match the target session"),
    ],
)
def test_wakeup_rejects_invalid_origin_or_target(source, platform_id, error):
    """Reject invalid routing before creating a trace or running any agent.

    Args:
        source: Proposed trigger mechanism.
        platform_id: Adapter identity supplied for the target.
        error: Expected validation error.
    """
    with pytest.raises(ValueError, match=error):
        AgentWakeupEvent(
            context=SimpleNamespace(),
            session=MessageSession.from_str("target:FriendMessage:session"),
            platform_meta=PlatformMetadata(
                id=platform_id, name="webchat", description="Target"
            ),
            prompt="Continue.",
            source=source,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcomes", [[False], [True], [False, True], [True, False], [False, False]]
)
async def test_send_accounting_respects_context_result(wakeup_event, outcomes):
    event, send, metric = wakeup_event
    send.side_effect = outcomes

    sent = False
    for outcome in outcomes:
        assert await event.send(MessageChain().message("result")) is None
        sent = sent or outcome
        assert event._has_send_oper is sent
    await asyncio.sleep(0)

    assert event._has_send_oper is any(outcomes)
    assert send.await_count == len(outcomes)
    assert metric.await_count == sum(outcomes)


@pytest.mark.asyncio
@pytest.mark.parametrize("empty_chunk", [False, True])
async def test_empty_stream_does_not_send(wakeup_event, empty_chunk):
    """Do not record a delivery for an empty stream or an empty break frame."""
    event, send, metric = wakeup_event

    async def chunks():
        if empty_chunk:
            yield MessageChain(type="break")

    await event.send_streaming(chunks())
    send.assert_not_awaited()
    metric.assert_not_awaited()
    assert event._has_send_oper is False


@pytest.mark.asyncio
@pytest.mark.parametrize("prior_send", [False, True])
async def test_send_exception_preserves_accounting(wakeup_event, prior_send):
    event, send, metric = wakeup_event
    event._has_send_oper = prior_send
    error = OSError("controlled transport error")
    send.side_effect = error

    with pytest.raises(OSError) as caught:
        await event.send(MessageChain().message("result"))
    await asyncio.sleep(0)

    assert caught.value is error
    assert event._has_send_oper is prior_send
    metric.assert_not_awaited()


@pytest.mark.asyncio
async def test_none_message_does_not_send(wakeup_event):
    event, send, metric = wakeup_event
    await event.send(None)
    await asyncio.sleep(0)

    assert event._has_send_oper is False
    send.assert_not_awaited()
    metric.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_platform_does_not_record_send(wakeup_event, caplog, monkeypatch):
    # AstrBot disables propagation, so attach pytest's handler directly.
    monkeypatch.setattr(logger, "handlers", [*logger.handlers, caplog.handler])
    event, _, metric = wakeup_event
    context = object.__new__(Context)
    context.platform_manager = SimpleNamespace(platform_insts=[])
    event.context_obj = context

    await event.send(MessageChain().message("result"))
    await asyncio.sleep(0)

    assert event._has_send_oper is False
    metric.assert_not_awaited()
    assert "cannot find platform" in caplog.text
