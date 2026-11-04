"""Programmatic main turns using real Core policy, native loops and output stages."""

import asyncio
import copy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from astrbot.api.agents import (
    AgentPermissions,
    FileInput,
    ImageInput,
    PlainInput,
    SessionState,
    TurnStatus,
)
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_runtime import main_session
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.tools.message_tools import SendMessageToUserTool
from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.platform.astr_message_event import event_context
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.star.session_llm_manager import SessionServiceManager
from astrbot.core.star.star_handler import EventType


@pytest_asyncio.fixture
async def sdk(environment, monkeypatch):
    """Use actual request construction and history writes with an offline model.

    Args:
        environment: Existing native runtime and Context fixture.
        monkeypatch: External service and telemetry patch manager.

    Yields:
        The configured SDK host and observable platform sends.
    """
    env = environment
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["provider_settings"]["streaming_response"] = False
    config["provider_settings"]["datetime_system_prompt"] = False
    config["agent"]["config"]["subagents"]["enabled"] = False
    env.config = config
    env.context.get_config = lambda **kwargs: config
    env.context.get_using_provider_async = AsyncMock(return_value=env.provider)
    env.context.get_using_tts_provider_async = AsyncMock(return_value=None)
    env.context._star_manager = SimpleNamespace(context=env.context)
    env.context.persona_manager.resolve_selected_persona = AsyncMock(
        return_value=(None, None, None, False)
    )
    env.conversation.persona_id = None
    env.conversations = {env.conversation.cid: env.conversation}
    env.context.conversation_manager.get_conversation.side_effect = lambda umo, cid: (
        env.conversations.get(cid)
    )

    async def save(umo, cid, *, history, **kwargs):
        env.conversations[cid].history = json.dumps(history)

    env.context.conversation_manager.update_conversation.side_effect = save
    env.platform_send = AsyncMock()
    env.context.platform_manager.platform_insts[0].send_by_session = env.platform_send
    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(main_session, "record_main_stats", AsyncMock())
    monkeypatch.setattr(main_session.Metric, "upload", AsyncMock())
    try:
        yield env
    finally:
        await env.context.agent.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("send_to_user", [True, False])
async def test_output_observers_do_not_change_delivery_or_history(sdk, send_to_user):
    """Save both modes and allow independent event readers without duplicate sends.

    Args:
        sdk: Offline host using real output stages.
        send_to_user: Whether Core automatically presents the runtime output.
    """
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Video analysis complete")],
        send_to_user=send_to_user,
    )
    result = await asyncio.wait_for(run.result(), 3)
    assert result.status == TurnStatus.COMPLETED
    assert result.text == "Done"
    assert sdk.platform_send.await_count == int(send_to_user)
    first = [event async for event in run.events()]
    second = [event async for event in run.events()]
    assert first == second
    assert first[-1].type == "turn_finished"
    assert any(
        event.type == "llm_result" and event.data["chain"].get_plain_text() == "Done"
        for event in first
    )
    history = json.loads(sdk.conversation.history)
    assert history[0]["role"] == "user"
    assert history[-1]["content"] == [{"type": "text", "text": "Done"}]
    assert sdk.context.agent is sdk.context.agent


@pytest.mark.asyncio
async def test_follow_up_queues_and_retains_conversation_and_output_policy(sdk):
    """Bind follow-ups to their original conversation and read newly saved history.

    Args:
        sdk: Offline host with switchable conversation selection.
    """
    entered, release = asyncio.Queue(), asyncio.Event()

    async def respond(**kwargs):
        await entered.put(copy.deepcopy(kwargs["contexts"]))
        await release.wait()
        return LLMResponse(role="assistant", completion_text="First reply")

    sdk.provider.text_chat.side_effect = respond
    first = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="First input")],
        send_to_user=False,
    )
    await asyncio.wait_for(entered.get(), 3)
    sdk.conversations["other"] = SimpleNamespace(
        cid="other", user_id=first.session.umo, history="[]", persona_id=None
    )
    sdk.context.conversation_manager.get_curr_conversation_id.return_value = "other"
    second = await first.follow_up(input_message=[PlainInput(text="Second input")])
    assert second.session is first.session
    assert first.session.state == SessionState.RUNNING
    assert first.session.pending_turn_count == 1
    assert not second.send_to_user
    release.set()
    await asyncio.wait_for(first.result(), 3)
    next_history = await asyncio.wait_for(entered.get(), 3)
    assert "First reply" in json.dumps(next_history)
    await asyncio.wait_for(second.result(), 3)
    assert first.session.state == SessionState.IDLE
    assert first.session.pending_turn_count == 0
    assert sdk.conversations["other"].history == "[]"
    sdk.platform_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_queued_input_rechecks_ai_admission(sdk):
    """An input waiting behind another turn must respect newly disabled AI.

    Args:
        sdk: Offline host with mutable session configuration.
    """
    entered, release = asyncio.Event(), asyncio.Event()

    async def respond(**kwargs):
        entered.set()
        await release.wait()
        return LLMResponse(role="assistant", completion_text="Done")

    sdk.provider.text_chat.side_effect = respond
    first = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="First")],
        send_to_user=False,
    )
    await asyncio.wait_for(entered.wait(), 3)
    second = await first.follow_up(input_message=[PlainInput(text="Second")])
    sdk.config["provider_settings"]["enable"] = False
    release.set()
    await asyncio.wait_for(first.result(), 3)
    assert (await asyncio.wait_for(second.result(), 3)).reason == "skipped"
    assert sdk.provider.text_chat.await_count == 1
    assert "Second" not in sdk.conversation.history


@pytest.mark.asyncio
async def test_disabled_automatic_output_does_not_intercept_explicit_sends(sdk):
    """Keep event, tool and Context sends explicit when automatic output is off.

    Args:
        sdk: Offline host whose provider simulates framework tool output.
    """
    tool_results = []

    async def respond(**kwargs):
        from astrbot.core.platform.astr_message_event import current_message_event

        event = current_message_event.get()
        await event.send(MessageChain().message("Direct tool message"))
        wrapper = ContextWrapper(
            context=AstrAgentContext(context=sdk.context, event=event)
        )
        tool_results.append(
            await SendMessageToUserTool().call(
                wrapper,
                messages=[
                    {"type": "plain", "text": "Builtin message"},
                    {"type": "image", "url": "https://example.invalid/result.png"},
                ],
            )
        )
        assert await sdk.context.send_message(
            event.unified_msg_origin, MessageChain().message("Explicit plugin message")
        )
        assert not await sdk.context.send_message(
            "missing:FriendMessage:alice", MessageChain().message("No adapter")
        )
        return LLMResponse(role="assistant", completion_text="Final reply")

    sdk.provider.text_chat.side_effect = respond
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Deliver results")],
        send_to_user=False,
    )
    assert (await asyncio.wait_for(run.result(), 3)).status == TurnStatus.COMPLETED
    assert sdk.platform_send.await_count == 3
    chains = [call.args[1] for call in sdk.platform_send.await_args_list]
    assert [chain.get_plain_text() for chain in chains] == [
        "Direct tool message",
        "Builtin message",
        "Explicit plugin message",
    ]
    assert tool_results[0].startswith("Message sent to session")
    assert isinstance(chains[1].chain[1], Image)
    assert run.runtime_turn.input.event._has_send_oper


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_at", [None, "waiting", "request"])
async def test_core_and_request_hooks_run_once_and_can_stop_input(
    sdk, monkeypatch, stop_at
):
    """Preserve event/ProviderRequest hooks for SDK input and honor termination.

    Args:
        sdk: Real native request and SDK host.
        monkeypatch: Hook dispatcher patch manager.
        stop_at: Optional hook at which to stop the input.
    """
    from astrbot.core.astr_agent_runtime.main_agent import builder
    from astrbot.core.pipeline import context_utils

    calls = []

    async def hook(event, kind, *args):
        calls.append(kind)
        if kind == EventType.OnLLMRequestEvent:
            args[0].prompt += " with plugin context"
        stop = (
            stop_at == "waiting"
            and kind == EventType.OnWaitingLLMRequestEvent
            or stop_at == "request"
            and kind == EventType.OnLLMRequestEvent
        )
        if stop:
            event.stop_event()
        return stop

    monkeypatch.setattr(context_utils, "call_event_hook", hook)
    monkeypatch.setattr(builder, "call_event_hook", hook)
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Analyze")],
        send_to_user=False,
    )
    result = await asyncio.wait_for(run.result(), 3)
    assert calls.count(EventType.OnWaitingLLMRequestEvent) == 1
    assert calls.count(EventType.OnLLMRequestEvent) == int(stop_at != "waiting")
    if stop_at is not None:
        assert result.reason == "skipped"
        sdk.provider.text_chat.assert_not_awaited()
        assert sdk.conversation.history == "[]"
    else:
        assert "Analyze with plugin context" in sdk.conversation.history


@pytest.mark.asyncio
async def test_source_permissions_and_shutdown_cancellation(sdk):
    """Inherit trusted caller identity and stop active SDK work on shutdown.

    Args:
        sdk: Offline host with a blocked model call.
    """
    entered = asyncio.Event()

    async def respond(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    sdk.provider.text_chat.side_effect = respond
    sdk.event.role = "admin"
    sdk.event.set_extra("_api_key_allow_admin_role", False)
    with event_context(sdk.event):
        run = await sdk.context.agent.run_turn(
            umo=sdk.event.unified_msg_origin,
            input_message=[PlainInput(text="Work")],
            send_to_user=False,
        )
        assert run.runtime_turn.input.event.get_sender_id() == "alice"
        assert run.runtime_turn.input.permissions == AgentPermissions()
        await asyncio.wait_for(entered.wait(), 3)
        await asyncio.wait_for(sdk.context.agent.close(), 3)
    assert (await run.result()).status == TurnStatus.CANCELLED
    assert sdk.conversation.history == "[]"


@pytest.mark.asyncio
async def test_steering_reuses_native_safe_boundary(sdk, monkeypatch):
    """Submit SDK text to the actual runner and settle its persistence receipt.

    Args:
        sdk: Offline native runtime and SDK integration.
        monkeypatch: Dispatcher patch manager for steering hook output.
    """
    from astrbot.core.pipeline import context_utils

    entered, release = asyncio.Event(), asyncio.Event()
    waiting = 0

    async def hook(event, kind, *args):
        nonlocal waiting
        if kind == EventType.OnWaitingLLMRequestEvent:
            waiting += 1
            if waiting == 2:
                await event.send(MessageChain().message("Steering notification"))
        return False

    monkeypatch.setattr(context_utils, "call_event_hook", hook)

    class WaitTool(FunctionTool):
        async def call(self, context):
            entered.set()
            await release.wait()
            return "Tool completed"

    sdk.manager.func_list.append(
        WaitTool(name="wait_for_result", description="Wait for a result", parameters={})
    )
    sdk.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["wait_for_result"],
            tools_call_ids=["call-1"],
            tools_call_args=[{}],
        ),
        LLMResponse(role="assistant", completion_text="Done"),
    ]
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Analyze")],
        send_to_user=False,
    )
    await asyncio.wait_for(entered.wait(), 3)
    receipt = await run.steer(input_message=[PlainInput(text="Focus on safety")])
    assert receipt is not None
    release.set()
    await asyncio.wait_for(run.result(), 3)
    assert await receipt
    assert "Focus on safety" in sdk.conversation.history
    sdk.platform_send.assert_awaited_once()
    assert (
        sdk.platform_send.await_args.args[1].get_plain_text() == "Steering notification"
    )
    assert await run.steer(input_message=[PlainInput(text="Too late")]) is None


@pytest.mark.asyncio
async def test_portable_media_uses_the_normal_input_preprocessor(sdk, tmp_path):
    """Keep image and file input on the same preparation path as normal messages.

    Args:
        sdk: Offline native host using real media preprocessing.
        tmp_path: Temporary directory for local attachments.
    """
    from PIL import Image as PILImage

    image = tmp_path / "frame.png"
    document = tmp_path / "notes.txt"
    PILImage.new("RGB", (4, 4), "blue").save(image)
    document.write_text("Safety notes", encoding="utf-8")
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[
            PlainInput(text="Analyze these attachments"),
            ImageInput(path=str(image)),
            FileInput(path=str(document), text="notes.txt"),
        ],
        send_to_user=False,
    )
    assert (await asyncio.wait_for(run.result(), 3)).status == TurnStatus.COMPLETED
    model_input = json.dumps(sdk.provider.text_chat.await_args.kwargs["contexts"])
    assert "image_url" in model_input
    assert "notes.txt" in model_input
    assert document.exists() and image.exists()
