"""Session waiters are dispatched by the core pipeline after access checks."""

import asyncio
import copy
from contextlib import aclosing
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import At, Image, Plain
from astrbot.core.pipeline.process_stage import stage as processing
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.pipeline.waking_check import stage as waking
from astrbot.core.pipeline.whitelist_check.stage import WhitelistCheckStage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils import session_waiter as waiting
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


@pytest.fixture
def empty_mention(monkeypatch):
    monkeypatch.setattr(waiting, "USER_SESSIONS", {})
    monkeypatch.setattr(waiting, "FILTERS", [])
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["platform_settings"].update(
        empty_mention_waiting=True, empty_mention_waiting_need_reply=True
    )
    config["provider_ltm_settings"]["group_icl_enable"] = False
    queue = asyncio.Queue()
    main = Main.__new__(Main)
    main.context = SimpleNamespace(
        get_config=lambda **_: config,
        get_locale=AsyncMock(return_value="en-US"),
        get_event_queue=lambda: queue,
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value="conversation"),
            get_conversation=AsyncMock(return_value=None),
        ),
    )
    main.group_chat_context = GroupChatContext(None, main.context)
    return main, config, queue


def make_group_event(*components, text=""):
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.self_id = "bot"
    message.sender = MessageMember(user_id="sender", nickname="Sender")
    message.message = list(components)
    return AstrMessageEvent(
        text,
        message,
        PlatformMetadata(id="test", name="test", description="Test"),
        "group",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tail", "should_wait"),
    [
        ([Plain("")], True),
        ([Plain(" \t")], True),
        ([Plain("question")], False),
        ([Plain(""), Image(file="test.png")], False),
    ],
)
async def test_empty_mention_classification(empty_mention, tail, should_wait):
    main, _, _ = empty_mention
    event = make_group_event(At(qq="bot"), *tail)
    chain = event.get_messages()
    original = copy.deepcopy(chain)
    async with aclosing(main.handle_empty_mention(event)) as handler:
        reply = await anext(handler, None)
        assert isinstance(reply, ProviderRequest) is should_wait
        assert bool(waiting.USER_SESSIONS) is should_wait
        assert event.get_messages() is chain and chain == original
    assert not waiting.USER_SESSIONS and not waiting.FILTERS


@pytest.mark.asyncio
@pytest.mark.parametrize("group_context_enabled", [False, True])
async def test_empty_mention_captures_follow_up_during_greeting(
    empty_mention, group_context_enabled
):
    main, config, queue = empty_mention
    config["provider_ltm_settings"]["group_icl_enable"] = group_context_enabled
    context = main.group_chat_context
    mention = make_group_event(At(qq="bot"))
    follow_up = make_group_event(Plain("follow-up"), text="follow-up")
    if group_context_enabled:
        await context.handle_message(
            make_group_event(Plain("earlier-chat"), text="earlier-chat")
        )

    # Deliver a follow-up at the lookup await without sleeps or a fake pipeline.
    async def deliver_during_lookup(origin):
        await context.handle_message(
            make_group_event(Plain("later-chat"), text="later-chat")
        )
        await SessionWaiter.trigger(origin, follow_up)
        queued_during_lookup.append(not queue.empty())
        return "conversation"

    queued_during_lookup = []
    if group_context_enabled:
        main.context.conversation_manager.get_curr_conversation_id.side_effect = (
            deliver_during_lookup
        )
    async with aclosing(main.handle_empty_mention(mention)) as handler:
        greeting = await anext(handler)
        if group_context_enabled:
            assert queued_during_lookup == [False]
        else:
            await SessionWaiter.trigger(mention.unified_msg_origin, follow_up)
        assert follow_up.is_stopped()
        assert queue.qsize() == 1
        replay = queue.get_nowait()
        assert replay.message_str == "follow-up" and not replay.is_stopped()
        assert isinstance(replay.get_messages()[0], At)

        if group_context_enabled:
            await main.decorate_llm_req(mention, greeting)
            (part,) = greeting.extra_user_content_parts
            assert "earlier-chat" in part.text and "later-chat" not in part.text
            await context.handle_message(replay)
            next_request = replay.request_llm(
                prompt="follow-up", session_id="conversation"
            )
            await main.decorate_llm_req(replay, next_request)
            (part,) = next_request.extra_user_content_parts
            assert "later-chat" in part.text and "earlier-chat" not in part.text

        assert await anext(handler, None) is None
    assert not waiting.USER_SESSIONS and not waiting.FILTERS and queue.empty()
