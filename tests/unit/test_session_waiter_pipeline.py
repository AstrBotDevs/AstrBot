"""Session waiters are dispatched by the core pipeline after access checks."""

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import Plain
from astrbot.core.pipeline.process_stage import stage as processing
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.waking_check import stage as waking
from astrbot.core.pipeline.whitelist_check.stage import WhitelistCheckStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.utils.session_waiter import (
    USER_SESSIONS,
    DefaultSessionFilter,
    SessionController,
    SessionFilter,
    SessionWaiter,
)


@pytest.mark.asyncio
async def test_stopping_session_waiter_wakes_timeout_task():
    controller = SessionController()
    holding_started = asyncio.Event()
    holding_finished = asyncio.Event()
    original_holding = controller._holding

    async def track_holding(event, timeout):
        holding_started.set()
        try:
            await original_holding(event, timeout)
        finally:
            holding_finished.set()

    controller._holding = track_holding
    controller.keep(timeout=60, reset_timeout=True)
    await holding_started.wait()
    controller.stop()

    await asyncio.wait_for(holding_finished.wait(), timeout=1)
    assert controller.future.done()


@pytest.mark.asyncio
async def test_keep_after_stop_does_not_start_timeout_task():
    controller = SessionController()
    controller.stop()

    try:
        controller.keep(timeout=60, reset_timeout=True)
        assert controller.current_event is None
    finally:
        controller.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("private", "state"),
    [
        (False, "waiting"),
        (True, "waiting"),
        (False, "custom"),
        (False, "blocked"),
        (False, "expired"),
        (False, "unmatched"),
        (False, "ordinary"),
    ],
)
async def test_session_waiter_pipeline(monkeypatch, private, state):
    """Preserve wakeup, access checks, custom IDs, and ordinary dispatch.

    Args:
        monkeypatch: Isolate waiters and plugin handler discovery.
        private: Whether the input is a private rather than group message.
        state: Waiting, blocked, expired, unmatched, custom, or ordinary input.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(admins_id=[], wake_prefix=["/"], plugin_set=[])
    config["platform_settings"].update(
        friend_message_needs_wake_prefix=True,
        unique_session=False,
        enable_id_white_list=state == "blocked",
        id_whitelist=["another-session"],
    )
    context = SimpleNamespace(
        astrbot_config=config, astrbot_config_id="test", db_helper=None
    )
    context.plugin_manager = SimpleNamespace(
        context=SimpleNamespace(get_config=lambda **_: config)
    )
    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE if private else MessageType.GROUP_MESSAGE
    message.sender = MessageMember(user_id="user", nickname="User")
    message.message = [Plain("/next" if state == "ordinary" else "next")]
    event = AstrMessageEvent(
        message.message[0].text,
        message,
        PlatformMetadata(id="test", name="test", description="Test"),
        "session",
    )

    class SenderFilter(SessionFilter):
        def filter(self, event):
            return event.get_sender_id()

    session_filter = SenderFilter() if state == "custom" else DefaultSessionFilter()
    session_id = session_filter.filter(event)
    waiter = SessionWaiter(session_filter, session_id, False)
    waiter.handler = AsyncMock()
    if state == "expired":
        waiter.session_controller.stop()
    if state not in {"unmatched", "ordinary"}:
        monkeypatch.setitem(USER_SESSIONS, session_id, waiter)
    for module in (waking, processing):
        monkeypatch.setattr(module, "FILTERS", [session_filter, session_filter])
    monkeypatch.setattr(
        waking.star_handlers_registry, "get_handlers_by_event_type", lambda *a, **kw: []
    )

    wake = waking.WakingCheckStage()
    whitelist = WhitelistCheckStage()
    await wake.initialize(context)
    await whitelist.initialize(context)
    process = processing.ProcessStage()
    process.ctx = context
    process.star_request_sub_stage = SimpleNamespace(process=AsyncMock())

    async def agent(current):
        current.set_extra("agent_called", True)
        yield

    process.agent_sub_stage = SimpleNamespace(process=agent)
    preprocess = AsyncMock(
        side_effect=lambda current: current.set_extra("preprocessed", True)
    )
    scheduler = object.__new__(PipelineScheduler)
    scheduler.stages = [wake, whitelist, SimpleNamespace(process=preprocess), process]
    await scheduler._process_stages(event)

    consumed = state in {"waiting", "custom"}
    assert waiter.handler.await_count == int(consumed)
    process.star_request_sub_stage.process.assert_not_called()
    assert bool(event.get_extra("agent_called", False)) == (state == "ordinary")
    if consumed:
        waiter.handler.assert_awaited_once_with(waiter.session_controller, event)
        assert event.is_wake and not event.is_at_or_wake_command
        assert event.get_extra("preprocessed") and event.is_stopped()
    elif state != "ordinary":
        preprocess.assert_not_awaited()
        assert event.is_stopped()


@pytest.mark.asyncio
async def test_reentrant_register_wait_supersedes_without_clobbering_new_waiter(
    monkeypatch,
):
    """Replacing an active waiter stops the old one without removing the new one."""
    from astrbot.core.utils import session_waiter as sw

    monkeypatch.setattr(sw, "USER_SESSIONS", {})
    monkeypatch.setattr(sw, "FILTERS", [])

    shared_filter = DefaultSessionFilter()
    waiter_1 = SessionWaiter(shared_filter, "s1", False)
    waiter_2 = SessionWaiter(shared_filter, "s1", False)

    async def noop_handler(controller, _event):
        controller.stop()

    sw.FILTERS.append(shared_filter)
    task_1 = asyncio.create_task(waiter_1.register_wait(noop_handler, timeout=30))
    await asyncio.sleep(0)
    assert sw.USER_SESSIONS["s1"] is waiter_1
    assert len(waiter_1.session_controller._holding_tasks) == 1

    sw.FILTERS.append(shared_filter)
    task_2 = asyncio.create_task(waiter_2.register_wait(noop_handler, timeout=30))
    await asyncio.sleep(0)

    # First waiter must finish without clobbering waiter_2 or its shared filter.
    await asyncio.wait_for(task_1, timeout=1.0)
    assert sw.USER_SESSIONS.get("s1") is waiter_2
    assert sw.FILTERS == [shared_filter]
    assert waiter_1.session_controller._holding_tasks == set()

    waiter_2._cleanup()
    await asyncio.wait_for(task_2, timeout=1.0)
    assert sw.USER_SESSIONS == {}
    assert sw.FILTERS == []
    assert waiter_2.session_controller._holding_tasks == set()


@pytest.mark.asyncio
async def test_cleanup_is_idempotent_with_shared_filters(monkeypatch):
    """Calling _cleanup repeatedly removes only the waiter's single filter entry."""
    from astrbot.core.utils import session_waiter as sw

    monkeypatch.setattr(sw, "USER_SESSIONS", {})
    monkeypatch.setattr(sw, "FILTERS", [])

    shared_filter = DefaultSessionFilter()
    other_waiter = SessionWaiter(shared_filter, "s2", False)
    sw.FILTERS.extend([shared_filter, shared_filter])
    sw.USER_SESSIONS["s2"] = other_waiter

    superseded = SessionWaiter(shared_filter, "s2", False)
    superseded._cleanup()
    superseded._cleanup()

    assert sw.USER_SESSIONS.get("s2") is other_waiter
    assert sw.FILTERS == [shared_filter]
