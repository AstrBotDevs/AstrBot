"""Session control forwards registered waiters and queues mention follow-ups."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from astrbot.builtin_stars.session_controller import main as session_controller
from astrbot.core.message.components import At, Plain
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata


@pytest.fixture
def controller():
    queue = asyncio.Queue()
    context = SimpleNamespace(
        get_config=Mock(
            return_value={
                "platform_settings": {
                    "empty_mention_waiting": True,
                    "empty_mention_waiting_need_reply": False,
                },
                "wake_prefix": ["/bot"],
            }
        ),
        get_event_queue=Mock(return_value=queue),
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(), new_conversation=AsyncMock()
        ),
    )
    return session_controller.Main(context), context, queue


@pytest.fixture
def make_event():
    def create(parts, text=""):
        message = AstrBotMessage()
        message.type = MessageType.FRIEND_MESSAGE
        message.self_id = "bot"
        message.sender = MessageMember(user_id="alice", nickname="Alice")
        message.session_id = "alice"
        message.message = parts
        message.message_str = text
        message.raw_message = text
        return AstrMessageEvent(
            text,
            message,
            PlatformMetadata(name="test", description="Test", id="test"),
            "alice",
        )

    return create


@pytest.mark.asyncio
async def test_only_registered_waiter_is_triggered(controller, make_event, monkeypatch):
    main, _, _ = controller
    event = make_event([Plain("question")], "question")
    trigger = AsyncMock()
    monkeypatch.setattr(session_controller.SessionWaiter, "trigger", trigger)
    monkeypatch.setattr(
        session_controller,
        "FILTERS",
        [
            SimpleNamespace(filter=Mock(return_value="missing")),
            SimpleNamespace(filter=Mock(return_value="active")),
        ],
    )
    monkeypatch.setattr(session_controller, "USER_SESSIONS", {"active": object()})

    await main.handle_session_control_agent(event)

    trigger.assert_awaited_once_with("active", event)
    assert event.is_stopped()


@pytest.mark.asyncio
async def test_nonmatching_session_continues_normal_processing(
    controller, make_event, monkeypatch
):
    main, _, _ = controller
    event = make_event([Plain("question")], "question")
    trigger = AsyncMock()
    monkeypatch.setattr(session_controller.SessionWaiter, "trigger", trigger)
    monkeypatch.setattr(
        session_controller,
        "FILTERS",
        [
            SimpleNamespace(filter=Mock(return_value="different")),
        ],
    )
    monkeypatch.setattr(session_controller, "USER_SESSIONS", {"active": object()})

    await main.handle_session_control_agent(event)

    trigger.assert_not_awaited()
    assert not event.is_stopped()


@pytest.mark.asyncio
async def test_nonempty_mention_does_not_open_a_follow_up_waiter(
    controller, make_event, monkeypatch
):
    main, context, queue = controller
    event = make_event([At(qq="bot"), Plain("question")], "question")
    waiter = Mock()
    monkeypatch.setattr(session_controller, "session_waiter", waiter)
    assert [item async for item in main.handle_empty_mention(event)] == []
    waiter.assert_not_called()
    context.conversation_manager.new_conversation.assert_not_awaited()
    assert queue.empty()


@pytest.mark.asyncio
async def test_empty_mention_follow_up_is_requeued_with_wakeup_identity(
    controller, make_event, monkeypatch
):
    main, _, queue = controller
    initial = make_event([At(qq="bot")])
    follow_up = make_event([Plain("question")], "question")
    stop = Mock()

    def immediate_waiter(timeout):
        assert timeout == 60

        def decorate(callback):
            async def wait(event):
                assert event is initial
                await callback(SimpleNamespace(stop=stop), follow_up)

            return wait

        return decorate

    monkeypatch.setattr(session_controller, "session_waiter", immediate_waiter)
    assert [item async for item in main.handle_empty_mention(initial)] == []
    assert queue.qsize() == 1
    queued = queue.get_nowait()
    assert queued is not follow_up
    assert queued.unified_msg_origin == follow_up.unified_msg_origin
    assert queued.message_str == "question"
    assert isinstance(queued.get_messages()[0], At)
    assert str(queued.get_messages()[0].qq) == "bot"
    assert queued.get_messages()[1].text == "question"
    assert initial.is_stopped()
    assert follow_up.is_stopped()
    stop.assert_called_once()
