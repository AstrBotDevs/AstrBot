"""Active replies must wait for message listeners to prepare or handle the event."""

import copy
from sys import maxsize
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.builtin_stars.astrbot.group_chat_context import GroupChatContext
from astrbot.builtin_stars.astrbot.main import Main
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.db.po import Conversation
from astrbot.core.message.components import Plain
from astrbot.core.pipeline.process_stage.method.star_request import StarRequestSubStage
from astrbot.core.pipeline.process_stage.stage import AgentRequestSubStage, ProcessStage
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.pipeline.scheduler import PipelineScheduler
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import (
    EventType,
    StarHandlerMetadata,
    StarHandlerRegistry,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "behavior",
    [
        "inject",
        "stop",
        "suppress",
        "reply",
        "explicit",
        "explicit_silent",
        "miss",
        "provider_disabled",
        "wake",
    ],
)
async def test_active_reply_waits_for_listeners(monkeypatch, behavior):
    """Exercise real listener dispatch, proactive selection, scheduling, and sending.

    Args:
        monkeypatch: Isolate plugin metadata and outbound metrics.
        behavior: Listener behavior or reply configuration to exercise.
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
    request_contexts = []

    async def listener(current):
        """Prepare context or handle the message before the default reply.

        Args:
            current: Message being dispatched.
        """
        order.append("listener")
        if current._has_send_oper:
            order.append("skipped")
            return
        current.set_extra("plugin_context", "ready")
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

    async def agent(current, wake_prefix):
        """Observe request-time plugin context without calling a remote model.

        Args:
            current: Message whose request is being executed.
            wake_prefix: Additional provider wake prefix.
        """
        order.append("agent")
        requests.append(current.get_extra("provider_request"))
        request_contexts.append(current.get_extra("plugin_context"))
        if behavior != "explicit_silent":
            current.set_result(current.plain_result("model reply"))
        yield

    original_send = event.send

    async def send(chain):
        """Record delivery while preserving the real event send state.

        Args:
            chain: Reply passed by RespondStage.
        """
        order.append("send")
        await original_send(chain)

    monkeypatch.setattr(event, "send", send)
    monkeypatch.setattr(
        "astrbot.core.platform.astr_message_event.Metric.upload", AsyncMock()
    )
    registry = StarHandlerRegistry()
    for name, handler, priority in (
        ("builtin", builtin.on_message, maxsize - 2),
        ("plugin", listener, -230000),
    ):
        module = f"test_active_reply_{name}"
        monkeypatch.setitem(
            star_map, module, SimpleNamespace(name=name, display_name=name)
        )
        registry.append(
            StarHandlerMetadata(
                EventType.AdapterMessageEvent,
                name,
                name,
                module,
                handler,
                [],
                extras_configs={"priority": priority},
            )
        )
    event.set_extra("activated_handlers", registry._handlers)
    process = ProcessStage()
    process.ctx = context
    process.star_request_sub_stage = StarRequestSubStage()
    await process.star_request_sub_stage.initialize(context)
    process.agent_sub_stage = AgentRequestSubStage()
    process.agent_sub_stage.ctx = context
    process.agent_sub_stage.config = config
    process.agent_sub_stage.prov_wake_prefix = ""
    process.agent_sub_stage.agent_sub_stage = SimpleNamespace(process=agent)
    monkeypatch.setattr(
        "astrbot.core.star.session_llm_manager.SessionServiceManager.should_process_llm_request",
        AsyncMock(return_value=True),
    )
    respond = RespondStage()
    await respond.initialize(context)
    scheduler = object.__new__(PipelineScheduler)
    scheduler.stages = [process, respond]

    await scheduler._process_stages(event)

    if behavior in {"inject", "explicit", "wake"}:
        assert order == ["listener", "agent", "send"]
    elif behavior == "explicit_silent":
        assert order == ["listener", "agent"]
    elif behavior == "reply":
        assert order == ["listener", "send"]
    else:
        assert order == ["listener"]
    assert request_contexts == ["ready"] * len(requests)
    if behavior == "inject":
        assert requests[0].conversation is conversation
        assert requests[0].prompt == "hello"
    elif behavior in {"explicit", "explicit_silent"}:
        assert requests[0].prompt == "explicit request"
