"""Session waiters are dispatched by the core pipeline after access checks."""

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.i18n import MESSAGES
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import At, File, Image, Plain
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


def make_event(components, text="", session="group"):
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.self_id = "bot"
    message.sender = MessageMember(user_id="sender", nickname="Sender")
    message.message = components
    event = AstrMessageEvent(
        text,
        message,
        PlatformMetadata(id="test", name="test", description="Test"),
        session,
    )
    event.is_at_or_wake_command = any(isinstance(c, At) for c in components)
    event.set_extra("activated_handlers", ["empty_mention"])
    return event


async def wait_until(predicate):
    # Observe the real registry; it has no registration/cleanup notification API.
    async with asyncio.timeout(1):
        while not predicate():  # noqa: ASYNC110
            await asyncio.sleep(0)


@pytest_asyncio.fixture
async def empty_mention_flow(monkeypatch):
    sessions, filters = {}, []
    for module in (waiting, processing):
        monkeypatch.setattr(module, "USER_SESSIONS", sessions)
        monkeypatch.setattr(module, "FILTERS", filters)
    controllers = []
    original_keep = waiting.SessionController.keep

    def keep(controller, *args, **kwargs):
        controllers.append(controller)
        return original_keep(controller, *args, **kwargs)

    monkeypatch.setattr(waiting.SessionController, "keep", keep)
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["platform_settings"].update(
        empty_mention_waiting=True, empty_mention_waiting_need_reply=True
    )
    config["wake_prefix"] = ["/"]
    config["provider_ltm_settings"]["group_icl_enable"] = False
    queue = asyncio.Queue()
    main = Main.__new__(Main)
    main.context = SimpleNamespace(
        get_config=lambda **kwargs: config,
        get_locale=AsyncMock(return_value="en-US"),
        get_event_queue=lambda: queue,
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value=None),
            new_conversation=AsyncMock(return_value="conversation"),
        ),
    )
    main.group_chat_context = GroupChatContext(None, main.context)
    started, release = asyncio.Event(), asyncio.Event()
    calls, tasks = [], []

    async def plugin(event):
        # Keep the generator owned by this consumer when it is cancelled.
        handler = main.handle_empty_mention(event)
        try:
            async for result in handler:
                yield result
        finally:
            await handler.aclose()

    async def agent(event):
        if isinstance(event.get_extra("provider_request"), ProviderRequest):
            started.set()
            await release.wait()
            calls.append("greeting")
        else:
            calls.append("follow-up")
        event._has_send_oper = True
        yield

    process = processing.ProcessStage()
    process.ctx = SimpleNamespace(astrbot_config=config)
    process.star_request_sub_stage = SimpleNamespace(process=plugin)
    process.agent_sub_stage = SimpleNamespace(process=agent)

    async def consume(event):
        async for _ in process.process(event):
            pass

    def start(event):
        task = asyncio.create_task(consume(event))
        tasks.append(task)
        return task

    try:
        yield SimpleNamespace(
            main=main,
            config=config,
            sessions=sessions,
            filters=filters,
            queue=queue,
            started=started,
            release=release,
            calls=calls,
            consume=consume,
            start=start,
        )
    finally:
        release.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # Let nested generators finalize before releasing the existing timers.
        await wait_until(lambda: not sessions)
        for controller in controllers:
            if controller.current_event:
                controller.current_event.set()
        await asyncio.sleep(0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("components", "expected", "enabled"),
    [
        ([At(qq="bot")], True, True),
        ([At(qq="bot"), Plain("")], True, True),
        ([At(qq="bot"), Plain(" \t\n")], True, True),
        ([At(qq="bot"), Plain("question")], False, True),
        ([At(qq="bot"), Plain(""), Image(file="test.png")], False, True),
        ([At(qq="bot"), File(name="test", file="test.txt")], False, True),
        ([Image(file="test.png")], False, True),
        ([At(qq="other"), Plain("")], False, True),
        ([At(qq="bot"), Plain("")], False, False),
        ([Plain("/")], True, True),
        ([At(qq="bot"), At(qq="bot"), Plain("")], False, True),
    ],
)
async def test_classification_preserves_message_chain(
    empty_mention_flow, components, expected, enabled
):
    empty_mention_flow.config["platform_settings"].update(
        empty_mention_waiting=enabled, empty_mention_waiting_need_reply=False
    )
    event = make_event(components)
    snapshot = copy.deepcopy(components)
    task = empty_mention_flow.start(event)
    await wait_until(lambda: bool(empty_mention_flow.sessions) or task.done())
    assert bool(empty_mention_flow.sessions) is expected
    assert event.get_messages() is components
    assert components == snapshot
    if expected:
        assert (
            next(iter(empty_mention_flow.sessions.values())).session_controller.timeout
            == 60
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [None, "", " \t\n"])
@pytest.mark.parametrize("during_greeting", [True, False])
async def test_follow_up_is_redispatched_once(
    empty_mention_flow, text, during_greeting
):
    components = [At(qq="bot")]
    if text is not None:
        components.append(Plain(text))
    if not during_greeting:
        empty_mention_flow.release.set()
    original = empty_mention_flow.start(make_event(components))
    await asyncio.wait_for(empty_mention_flow.started.wait(), 1)
    assert empty_mention_flow.sessions, (
        "The waiter must exist before the model greeting completes"
    )

    follow_up = make_event([Plain("question")], "question")
    await empty_mention_flow.consume(follow_up)
    assert follow_up.is_stopped()
    assert empty_mention_flow.queue.qsize() == 1
    replay = empty_mention_flow.queue.get_nowait()
    assert replay is not follow_up and not replay.is_stopped()
    assert isinstance(replay.get_messages()[0], At)
    assert replay.message_str == "question"
    # The waking stage recognizes the inserted At on redispatch.
    replay.is_at_or_wake_command = True
    await empty_mention_flow.consume(replay)
    assert empty_mention_flow.calls.count("follow-up") == 1
    empty_mention_flow.release.set()
    await asyncio.wait_for(original, 1)
    assert empty_mention_flow.sessions == {} and empty_mention_flow.filters == []


@pytest.mark.asyncio
async def test_silent_waiting_does_not_request_a_greeting(empty_mention_flow):
    empty_mention_flow.config["platform_settings"][
        "empty_mention_waiting_need_reply"
    ] = False
    original = empty_mention_flow.start(make_event([At(qq="bot"), Plain("")]))
    await wait_until(lambda: bool(empty_mention_flow.sessions) or original.done())
    assert (
        empty_mention_flow.sessions
        and not empty_mention_flow.started.is_set()
        and not empty_mention_flow.calls
    )
    await empty_mention_flow.consume(make_event([Plain("question")], "question"))
    replay = empty_mention_flow.queue.get_nowait()
    replay.is_at_or_wake_command = True
    await empty_mention_flow.consume(replay)
    await asyncio.wait_for(original, 1)
    assert empty_mention_flow.calls == ["follow-up"]
    assert empty_mention_flow.sessions == {} and empty_mention_flow.filters == []


@pytest.mark.asyncio
async def test_closing_handler_during_greeting_cleans_waiter(empty_mention_flow):
    handler = empty_mention_flow.main.handle_empty_mention(make_event([At(qq="bot")]))
    try:
        assert isinstance(await anext(handler), ProviderRequest)
        assert empty_mention_flow.sessions
    finally:
        await handler.aclose()
    assert empty_mention_flow.sessions == {} and empty_mention_flow.filters == []


@pytest.mark.asyncio
async def test_cancelling_silent_wait_cleans_waiter(empty_mention_flow):
    empty_mention_flow.config["platform_settings"][
        "empty_mention_waiting_need_reply"
    ] = False
    original = empty_mention_flow.start(make_event([At(qq="bot")]))
    await wait_until(lambda: bool(empty_mention_flow.sessions))
    original.cancel()
    with pytest.raises(asyncio.CancelledError):
        await original
    assert empty_mention_flow.sessions == {} and empty_mention_flow.filters == []


@pytest.mark.asyncio
async def test_cancelling_greeting_pipeline_cleans_waiter(empty_mention_flow):
    original = empty_mention_flow.start(make_event([At(qq="bot")]))
    await asyncio.wait_for(empty_mention_flow.started.wait(), 1)
    assert empty_mention_flow.sessions
    original.cancel()
    with pytest.raises(asyncio.CancelledError):
        await original
    await wait_until(lambda: not empty_mention_flow.sessions)
    assert empty_mention_flow.filters == [] and empty_mention_flow.queue.empty()


@pytest.mark.asyncio
async def test_greeting_setup_error_keeps_waiting_until_handler_closes(
    empty_mention_flow,
):
    manager = empty_mention_flow.main.context.conversation_manager
    manager.get_curr_conversation_id.side_effect = RuntimeError("test failure")
    handler = empty_mention_flow.main.handle_empty_mention(make_event([At(qq="bot")]))
    try:
        fallback = await anext(handler)
        assert fallback.get_plain_text() == MESSAGES["en-US"]["empty_mention"]
        assert empty_mention_flow.sessions
    finally:
        await handler.aclose()
    assert empty_mention_flow.sessions == {} and empty_mention_flow.filters == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [True, False])
async def test_timeout_cleans_waiter_without_follow_up(empty_mention_flow, reply):
    empty_mention_flow.config["platform_settings"][
        "empty_mention_waiting_need_reply"
    ] = reply
    original = empty_mention_flow.start(make_event([At(qq="bot")]))
    await wait_until(lambda: bool(empty_mention_flow.sessions))
    controller = next(iter(empty_mention_flow.sessions.values())).session_controller
    # Exercise the real timeout path without waiting sixty wall-clock seconds.
    await controller._holding(asyncio.Event(), 0)
    empty_mention_flow.release.set()
    await asyncio.wait_for(original, 1)
    assert (
        empty_mention_flow.queue.empty() and "follow-up" not in empty_mention_flow.calls
    )
    assert empty_mention_flow.sessions == {} and empty_mention_flow.filters == []


@pytest.mark.asyncio
async def test_concurrent_follow_ups_only_consume_waiter_once(empty_mention_flow):
    original = empty_mention_flow.start(make_event([At(qq="bot")]))
    await asyncio.wait_for(empty_mention_flow.started.wait(), 1)
    assert empty_mention_flow.sessions
    await asyncio.gather(
        empty_mention_flow.consume(make_event([Plain("first")], "first")),
        empty_mention_flow.consume(make_event([Plain("second")], "second")),
    )
    assert empty_mention_flow.queue.qsize() == 1
    empty_mention_flow.release.set()
    await asyncio.wait_for(original, 1)


@pytest.mark.asyncio
async def test_other_conversation_does_not_consume_waiter(empty_mention_flow):
    original = empty_mention_flow.start(make_event([At(qq="bot")]))
    await asyncio.wait_for(empty_mention_flow.started.wait(), 1)
    assert empty_mention_flow.sessions
    other = make_event([Plain("question")], "question", session="other-group")
    await empty_mention_flow.consume(other)
    assert (
        empty_mention_flow.queue.empty()
        and not other.is_stopped()
        and empty_mention_flow.sessions
    )
    await empty_mention_flow.consume(make_event([Plain("question")], "question"))
    assert empty_mention_flow.queue.qsize() == 1
    empty_mention_flow.release.set()
    await asyncio.wait_for(original, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("lookup_fails", [False, True])
async def test_empty_mention_keeps_context_boundary_during_lookup(
    empty_mention_flow, lookup_fails
):
    """Keep earlier chat in the greeting and replay a fast follow-up once.

    Args:
        empty_mention_flow: Real message processing with an isolated session registry.
        lookup_fails: Whether to fall back to a plain greeting after the lookup.
    """
    flow = empty_mention_flow
    flow.config["provider_ltm_settings"]["group_icl_enable"] = True
    context = flow.main.group_chat_context
    await context.handle_message(
        make_event([Plain("before-mention")], "before-mention")
    )
    lookup_started, release_lookup = asyncio.Event(), asyncio.Event()

    async def lookup(_umo):
        lookup_started.set()
        await release_lookup.wait()
        if lookup_fails:
            raise RuntimeError("Conversation lookup failed")
        return None

    flow.main.context.conversation_manager.get_curr_conversation_id.side_effect = lookup
    mention = make_event([At(qq="bot"), Plain("")])
    handler = flow.main.handle_empty_mention(mention)
    greeting = asyncio.create_task(anext(handler))
    try:
        await asyncio.wait_for(lookup_started.wait(), 1)
        assert mention.get_extra("_group_context_record_id")
        await context.handle_message(make_event([Plain("later-chat")], "later-chat"))
        follow_up = make_event([Plain("question")], "question")
        await flow.consume(follow_up)
        assert follow_up.is_stopped()
        assert flow.queue.empty()

        release_lookup.set()
        reply = await asyncio.wait_for(greeting, 1)
        assert flow.queue.qsize() == 1
        replay = flow.queue.get_nowait()
        assert replay.message_str == "question"
        assert isinstance(replay.get_messages()[0], At)

        if lookup_fails:
            assert reply.get_plain_text() == MESSAGES["en-US"]["empty_mention"]
            return

        assert isinstance(reply, ProviderRequest)
        injected = [part.text for part in reply.extra_user_content_parts]
        assert len(injected) == 1
        assert "before-mention" in injected[0]
        assert "later-chat" not in injected[0] and "question" not in injected[0]

        # The regular request hook must not consume the later chat a second time.
        await flow.main.decorate_llm_req(mention, reply)
        assert [part.text for part in reply.extra_user_content_parts] == injected
        await context.handle_message(replay)
        next_request = replay.request_llm(prompt="question", session_id="conversation")
        await flow.main.decorate_llm_req(replay, next_request)
        next_context = [part.text for part in next_request.extra_user_content_parts]
        assert len(next_context) == 1 and "later-chat" in next_context[0]
        assert "before-mention" not in next_context[0]
    finally:
        release_lookup.set()
        if not greeting.done():
            greeting.cancel()
        await asyncio.gather(greeting, return_exceptions=True)
        await handler.aclose()
    assert flow.sessions == {} and flow.filters == [] and flow.queue.empty()
