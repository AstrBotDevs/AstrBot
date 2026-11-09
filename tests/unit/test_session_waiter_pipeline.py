"""Session waiters are dispatched by the core pipeline after access checks."""

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
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from astrbot.core.utils.session_waiter import (
    USER_SESSIONS,
    DefaultSessionFilter,
    SessionFilter,
    SessionWaiter,
)


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
    monkeypatch.setattr(
        SessionPluginManager, "filter_handlers_by_session", AsyncMock(return_value=[])
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
