"""Cron wakeups preserve their target, permissions and delivery accounting."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest

from astrbot.core.agent_wakeup import wake_main_agent
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform import agent_wakeup_event as wakeups
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    streaming_response_event,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


@pytest.fixture
def cron_target():
    session = MessageSession.from_str("test-adapter:GroupMessage:room:alice")
    metadata = PlatformMetadata(
        name="test", description="Test adapter", id="test-adapter"
    )
    queue = asyncio.Queue()
    context = SimpleNamespace(
        send_message=AsyncMock(return_value=True),
        get_platform_inst=Mock(return_value=SimpleNamespace(meta=lambda: metadata)),
        get_event_queue=Mock(return_value=queue),
    )
    return context, session, metadata, queue


@pytest.fixture
def cron_event(cron_target):
    context, session, metadata, _ = cron_target
    return AgentWakeupEvent(
        context=context,
        session=session,
        platform_meta=metadata,
        prompt="Run the scheduled check.",
        source="cron",
        source_id="job-1",
        role="admin",
    )


def test_cron_wakeup_preserves_the_real_target_instead_of_a_synthetic_platform(
    cron_event, cron_target
):
    context, session, metadata, _ = cron_target
    assert cron_event.context_obj is context
    assert cron_event.session is session
    assert cron_event.platform_meta is metadata
    assert cron_event.unified_msg_origin == str(session)
    assert cron_event.message_obj.type == MessageType.GROUP_MESSAGE
    assert cron_event.session_id == "room:alice"


def test_cron_wakeup_preserves_prompt_and_resolved_permissions(cron_event):
    assert cron_event.source == "cron"
    assert cron_event.source_id == "job-1"
    assert cron_event.role == "admin"
    assert cron_event.message_str == "Run the scheduled check."
    assert [part.text for part in cron_event.get_messages()] == [
        "Run the scheduled check."
    ]
    assert cron_event.is_wake is True
    assert cron_event.is_at_or_wake_command is True
    assert cron_event.get_extra("_session_resolved") is True
    assert cron_event.get_extra("_role_resolved") is True
    assert cron_event.get_extra("enable_streaming") is False


def test_cron_wakeup_generates_an_explicit_message_identity(cron_target, monkeypatch):
    context, session, metadata, _ = cron_target
    monkeypatch.setattr(wakeups.uuid, "uuid4", lambda: UUID(int=42))
    event = AgentWakeupEvent(
        context=context,
        session=session,
        platform_meta=metadata,
        prompt="check",
        source="cron",
    )
    assert event.message_obj.message_id == UUID(int=42).hex
    assert event.message_obj.sender.user_id == "astrbot"
    assert event.message_obj.sender.nickname == "System"


@pytest.mark.parametrize("invalid_source", ["", "timer", "external"])
def test_wakeup_rejects_unknown_sources(cron_target, invalid_source):
    context, session, metadata, _ = cron_target
    with pytest.raises(ValueError, match="Unsupported agent wakeup source"):
        AgentWakeupEvent(
            context=context,
            session=session,
            platform_meta=metadata,
            prompt="check",
            source=invalid_source,
        )


def test_wakeup_rejects_mismatched_adapter_metadata(cron_target):
    context, session, _, _ = cron_target
    with pytest.raises(ValueError, match="must match"):
        AgentWakeupEvent(
            context=context,
            session=session,
            platform_meta=PlatformMetadata(
                name="test", description="Other", id="other"
            ),
            prompt="check",
            source="cron",
        )


@pytest.mark.asyncio
async def test_cron_submission_queues_one_event_for_the_original_umo(cron_target):
    context, session, _, queue = cron_target
    await wake_main_agent(
        context,
        umo=str(session),
        user_prompt="Scheduled input",
        source="cron",
        source_id="job-7",
        role="member",
    )
    assert queue.qsize() == 1
    event = queue.get_nowait()
    assert isinstance(event, AgentWakeupEvent)
    assert event.unified_msg_origin == str(session)
    assert event.source_id == "job-7"
    assert event.message_str == "Scheduled input"
    assert event.role == "member"
    context.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancelled_cron_submission_does_not_resolve_or_enqueue(cron_target):
    context, session, _, queue = cron_target
    stopped = asyncio.Event()
    stopped.set()
    await wake_main_agent(
        context,
        umo=str(session),
        user_prompt="Cancelled input",
        source="cron",
        stop_signal=stopped,
    )
    context.get_platform_inst.assert_not_called()
    assert queue.empty()


@pytest.mark.asyncio
async def test_missing_target_adapter_fails_without_enqueuing(cron_target):
    context, session, _, queue = cron_target
    context.get_platform_inst.return_value = None
    with pytest.raises(ValueError, match="not found"):
        await wake_main_agent(
            context, umo=str(session), user_prompt="check", source="cron"
        )
    assert queue.empty()


@pytest.mark.asyncio
async def test_successful_send_uses_exact_target_and_records_once(
    cron_event, cron_target, monkeypatch
):
    context, session, _, _ = cron_target
    record_send = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send", record_send)
    chain = MessageChain([Plain("response")])
    previous = streaming_response_event.get()
    await cron_event.send(chain)
    context.send_message.assert_awaited_once_with(session, chain)
    record_send.assert_awaited_once_with(chain)
    assert streaming_response_event.get() is previous


@pytest.mark.asyncio
async def test_unsent_message_is_not_recorded_as_delivered(
    cron_event, cron_target, monkeypatch
):
    context, _, _, _ = cron_target
    context.send_message.return_value = False
    record_send = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send", record_send)
    await cron_event.send(MessageChain([Plain("response")]))
    record_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_failure_restores_streaming_context_and_propagates(
    cron_event, cron_target, monkeypatch
):
    context, _, _, _ = cron_target
    context.send_message.side_effect = RuntimeError("delivery failed")
    record_send = AsyncMock()
    monkeypatch.setattr(AstrMessageEvent, "send", record_send)
    previous = streaming_response_event.get()
    with pytest.raises(RuntimeError, match="delivery failed"):
        await cron_event.send(MessageChain([Plain("response")]))
    assert streaming_response_event.get() is previous
    record_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_none_has_no_delivery_side_effect(cron_event, cron_target):
    context, _, _, _ = cron_target
    await cron_event.send(None)
    context.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_streaming_chunks_are_buffered_into_one_complete_delivery(
    cron_event, cron_target, monkeypatch
):
    context, session, _, _ = cron_target
    monkeypatch.setattr(AstrMessageEvent, "send", AsyncMock())

    async def chunks():
        yield MessageChain([Plain("first ")])
        yield MessageChain([])
        yield MessageChain([Plain("second")])

    await cron_event.send_streaming(chunks())
    context.send_message.assert_awaited_once()
    actual_session, message = context.send_message.await_args.args
    assert actual_session is session
    assert [part.text for part in message.chain] == ["first second"]


@pytest.mark.asyncio
async def test_empty_stream_has_no_delivery(cron_event, cron_target):
    context, _, _, _ = cron_target

    async def chunks():
        yield MessageChain([])

    await cron_event.send_streaming(chunks())
    context.send_message.assert_not_awaited()
