"""Tests for synthetic cron event send accounting."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.cron.events import CronMessageEvent
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.star.context import Context


@pytest.fixture
def cron_event(monkeypatch):
    """Create a real event with controlled transport and metric upload.

    Args:
        monkeypatch: Replaces network metric upload.

    Returns:
        Event, transport mock and metric mock.
    """
    send = AsyncMock(return_value=True)
    metric = AsyncMock()
    monkeypatch.setattr("astrbot.core.platform.astr_message_event.Metric.upload", metric)
    event = CronMessageEvent(
        context=SimpleNamespace(send_message=send),
        session=MessageSession.from_str("test:FriendMessage:session-1"),
        message="scheduled task",
    )
    return event, send, metric


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcomes", [[False], [True], [False, True], [True, False], [False, False]]
)
@pytest.mark.parametrize("streaming", [False, True])
async def test_send_accounting_respects_context_result(cron_event, outcomes, streaming):
    event, send, metric = cron_event
    send.side_effect = outcomes

    async def chunks():
        for _ in outcomes:
            yield MessageChain().message("result")

    if streaming:
        await event.send_streaming(chunks())
    else:
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
@pytest.mark.parametrize("prior_send", [False, True])
async def test_send_exception_preserves_accounting(cron_event, prior_send):
    event, send, metric = cron_event
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
async def test_none_message_does_not_send(cron_event):
    event, send, metric = cron_event
    await event.send(None)
    await asyncio.sleep(0)

    assert event._has_send_oper is False
    send.assert_not_awaited()
    metric.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_platform_does_not_record_send(cron_event, caplog):
    event, _, metric = cron_event
    context = object.__new__(Context)
    context.platform_manager = SimpleNamespace(platform_insts=[])
    event.context_obj = context

    await event.send(MessageChain().message("result"))
    await asyncio.sleep(0)

    assert event._has_send_oper is False
    metric.assert_not_awaited()
    assert "cannot find platform" in caplog.text
