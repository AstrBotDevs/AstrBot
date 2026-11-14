"""Regression coverage for empty mentions and waiter registration timing."""

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import At, File, Image, Plain
from astrbot.core.pipeline.process_stage import stage as processing
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils import session_waiter as waiting


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
async def flow(monkeypatch):
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
    queue = asyncio.Queue()
    main = Main.__new__(Main)
    main.context = SimpleNamespace(
        get_config=lambda **kwargs: config,
        get_event_queue=lambda: queue,
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value=None),
            new_conversation=AsyncMock(return_value="conversation"),
        ),
    )
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
    flow, components, expected, enabled
):
    flow.config["platform_settings"].update(
        empty_mention_waiting=enabled, empty_mention_waiting_need_reply=False
    )
    event = make_event(components)
    snapshot = copy.deepcopy(components)
    task = flow.start(event)
    await wait_until(lambda: bool(flow.sessions) or task.done())
    assert bool(flow.sessions) is expected
    assert event.get_messages() is components
    assert components == snapshot
    if expected:
        assert next(iter(flow.sessions.values())).session_controller.timeout == 60


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [None, "", " \t\n"])
@pytest.mark.parametrize("during_greeting", [True, False])
async def test_follow_up_is_redispatched_once(flow, text, during_greeting):
    components = [At(qq="bot")]
    if text is not None:
        components.append(Plain(text))
    if not during_greeting:
        flow.release.set()
    original = flow.start(make_event(components))
    await asyncio.wait_for(flow.started.wait(), 1)
    assert flow.sessions, "The waiter must exist before the model greeting completes"

    follow_up = make_event([Plain("question")], "question")
    await flow.consume(follow_up)
    assert follow_up.is_stopped()
    assert flow.queue.qsize() == 1
    replay = flow.queue.get_nowait()
    assert replay is not follow_up and not replay.is_stopped()
    assert isinstance(replay.get_messages()[0], At)
    assert replay.message_str == "question"
    # The waking stage recognizes the inserted At on redispatch.
    replay.is_at_or_wake_command = True
    await flow.consume(replay)
    assert flow.calls.count("follow-up") == 1
    flow.release.set()
    await asyncio.wait_for(original, 1)
    assert flow.sessions == {} and flow.filters == []


@pytest.mark.asyncio
async def test_silent_waiting_does_not_request_a_greeting(flow):
    flow.config["platform_settings"]["empty_mention_waiting_need_reply"] = False
    original = flow.start(make_event([At(qq="bot"), Plain("")]))
    await wait_until(lambda: bool(flow.sessions) or original.done())
    assert flow.sessions and not flow.started.is_set() and not flow.calls
    await flow.consume(make_event([Plain("question")], "question"))
    replay = flow.queue.get_nowait()
    replay.is_at_or_wake_command = True
    await flow.consume(replay)
    await asyncio.wait_for(original, 1)
    assert flow.calls == ["follow-up"]
    assert flow.sessions == {} and flow.filters == []


@pytest.mark.asyncio
async def test_closing_handler_during_greeting_cleans_waiter(flow):
    handler = flow.main.handle_empty_mention(make_event([At(qq="bot")]))
    try:
        assert isinstance(await anext(handler), ProviderRequest)
        assert flow.sessions
    finally:
        await handler.aclose()
    assert flow.sessions == {} and flow.filters == []


@pytest.mark.asyncio
async def test_cancelling_silent_wait_cleans_waiter(flow):
    flow.config["platform_settings"]["empty_mention_waiting_need_reply"] = False
    original = flow.start(make_event([At(qq="bot")]))
    await wait_until(lambda: bool(flow.sessions))
    original.cancel()
    with pytest.raises(asyncio.CancelledError):
        await original
    assert flow.sessions == {} and flow.filters == []


@pytest.mark.asyncio
async def test_cancelling_greeting_pipeline_cleans_waiter(flow):
    original = flow.start(make_event([At(qq="bot")]))
    await asyncio.wait_for(flow.started.wait(), 1)
    assert flow.sessions
    original.cancel()
    with pytest.raises(asyncio.CancelledError):
        await original
    await wait_until(lambda: not flow.sessions)
    assert flow.filters == [] and flow.queue.empty()


@pytest.mark.asyncio
async def test_greeting_setup_error_keeps_waiting_until_handler_closes(flow):
    manager = flow.main.context.conversation_manager
    manager.get_curr_conversation_id.side_effect = RuntimeError("test failure")
    handler = flow.main.handle_empty_mention(make_event([At(qq="bot")]))
    try:
        fallback = await anext(handler)
        assert not isinstance(fallback, ProviderRequest)
        assert flow.sessions
    finally:
        await handler.aclose()
    assert flow.sessions == {} and flow.filters == []


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [True, False])
async def test_timeout_cleans_waiter_without_follow_up(flow, reply):
    flow.config["platform_settings"]["empty_mention_waiting_need_reply"] = reply
    original = flow.start(make_event([At(qq="bot")]))
    await wait_until(lambda: bool(flow.sessions))
    controller = next(iter(flow.sessions.values())).session_controller
    # Exercise the real timeout path without waiting sixty wall-clock seconds.
    await controller._holding(asyncio.Event(), 0)
    flow.release.set()
    await asyncio.wait_for(original, 1)
    assert flow.queue.empty() and "follow-up" not in flow.calls
    assert flow.sessions == {} and flow.filters == []


@pytest.mark.asyncio
async def test_concurrent_follow_ups_only_consume_waiter_once(flow):
    original = flow.start(make_event([At(qq="bot")]))
    await asyncio.wait_for(flow.started.wait(), 1)
    assert flow.sessions
    await asyncio.gather(
        flow.consume(make_event([Plain("first")], "first")),
        flow.consume(make_event([Plain("second")], "second")),
    )
    assert flow.queue.qsize() == 1
    flow.release.set()
    await asyncio.wait_for(original, 1)


@pytest.mark.asyncio
async def test_other_conversation_does_not_consume_waiter(flow):
    original = flow.start(make_event([At(qq="bot")]))
    await asyncio.wait_for(flow.started.wait(), 1)
    assert flow.sessions
    other = make_event([Plain("question")], "question", session="other-group")
    await flow.consume(other)
    assert flow.queue.empty() and not other.is_stopped() and flow.sessions
    await flow.consume(make_event([Plain("question")], "question"))
    assert flow.queue.qsize() == 1
    flow.release.set()
    await asyncio.wait_for(original, 1)
