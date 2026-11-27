"""Active replies must wait for message listeners to prepare or handle the event."""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.db.po import Conversation
from astrbot.core.message.components import Plain
from astrbot.core.pipeline.process_stage.method.star_request import StarRequestSubStage
from astrbot.core.pipeline.process_stage.stage import ProcessStage
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, StarHandlerMetadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("behavior", "expected_order", "expected_sends"),
    [
        ("pass_through", ["listener", "agent"], 1),
        ("stop", ["listener"], 0),
        ("suppress", ["listener"], 0),
        ("reply", ["listener"], 1),
        ("explicit", ["listener", "agent"], 1),
        ("explicit_silent", ["listener", "agent"], 0),
        ("miss", ["listener"], 0),
        ("provider_disabled", ["listener"], 0),
        ("wake", ["listener", "agent"], 1),
    ],
)
async def test_active_reply_waits_for_listeners(
    monkeypatch, behavior, expected_order, expected_sends
):
    """Exercise real listener dispatch, proactive selection, scheduling, and sending.

    Args:
        monkeypatch: Isolate plugin metadata and outbound metrics.
        behavior: Listener behavior or reply configuration to exercise.
        expected_order: Listener and agent execution order.
        expected_sends: Number of replies delivered.
    """
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_ltm_settings"]["group_icl_enable"] = False
    config["provider_ltm_settings"]["active_reply"].update(
        enable=True,
        method="possibility_reply",
        possibility_reply=0.0 if behavior == "miss" else 1.0,
        whitelist=[],
    )
    config["provider_settings"]["enable"] = behavior != "provider_disabled"
    config["platform_settings"]["segmented_reply"]["enable"] = False
    conversation = Conversation(platform_id="test", user_id="test", cid="test")
    context = SimpleNamespace(
        astrbot_config=config,
        get_config=lambda **kwargs: config,
        get_using_provider_async=AsyncMock(return_value=object()),
        conversation_manager=SimpleNamespace(
            get_curr_conversation_id=AsyncMock(return_value="test"),
            get_conversation=AsyncMock(return_value=conversation),
        ),
    )
    builtin = Main.__new__(Main)
    builtin.context = context
    builtin.group_chat_context = GroupChatContext(None, context)
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "group"
    message.sender = MessageMember(user_id="user", nickname="User")
    message.message = [Plain("hello")]
    event = AstrMessageEvent(
        "hello",
        message,
        PlatformMetadata(id="test", name="test", description="Test"),
        "group",
    )
    event.plugins_name = []
    event.is_at_or_wake_command = behavior == "wake"
    order = []
    requests = []

    async def listener(current):
        """Handle the message or allow the default reply to proceed.

        Args:
            current: Message being dispatched.
        """
        order.append("listener")
        if current._has_send_oper:
            order.append("skipped")
            return
        if behavior == "stop":
            current.stop_event()
        elif behavior == "suppress":
            current.should_call_llm(True)
        elif behavior == "reply":
            yield current.plain_result("plugin reply")
        elif behavior in {"explicit", "explicit_silent"}:
            # Disabling the default reply must not block an explicit request.
            if behavior == "explicit":
                current.should_call_llm(True)
            yield current.request_llm(prompt="explicit request")

    async def agent(current):
        """Record requests and supply a reply without calling a remote model.

        Args:
            current: Message whose request is being executed.
        """
        order.append("agent")
        requests.append(current.get_extra("provider_request"))
        if behavior != "explicit_silent":
            current.set_result(current.plain_result("model reply"))
        yield

    monkeypatch.setattr(event, "send", AsyncMock(wraps=event.send))
    monkeypatch.setattr(
        "astrbot.core.platform.astr_message_event.Metric.upload", AsyncMock()
    )
    monkeypatch.setitem(
        star_map, __name__, SimpleNamespace(name="test", display_name="Test")
    )
    # WakingCheckStage supplies handlers in descending priority order.
    event.set_extra(
        "activated_handlers",
        [
            StarHandlerMetadata(
                EventType.AdapterMessageEvent, name, name, __name__, handler, []
            )
            for name, handler in [("builtin", builtin.on_message), ("plugin", listener)]
        ],
    )
    process = ProcessStage()
    process.ctx = context
    process.star_request_sub_stage = StarRequestSubStage()
    await process.star_request_sub_stage.initialize(context)
    process.agent_sub_stage = SimpleNamespace(process=agent)
    respond = RespondStage()
    await respond.initialize(context)
    scheduler = object.__new__(PipelineScheduler)
    scheduler.stages = [process, respond]

    await scheduler._process_stages(event)

    assert order == expected_order
    assert event.send.await_count == expected_sends
    if behavior == "pass_through":
        assert requests[0].conversation is conversation
        assert requests[0].prompt == "hello"
    elif behavior in {"explicit", "explicit_silent"}:
        assert requests[0].prompt == "explicit request"
