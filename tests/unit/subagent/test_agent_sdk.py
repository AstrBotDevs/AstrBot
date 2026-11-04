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
from astrbot.core.astr_agent_runtime import session as native_session
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
    monkeypatch.setattr(native_session, "record_agent_stats", AsyncMock())
    monkeypatch.setattr(native_session.Metric, "upload", AsyncMock())
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
    assert first[-1].type == "turn.finished"
    assert any(
        event.type == "message.completed"
        and "".join(part.text for part in event.payload.content if part.type == "plain")
        == "Done"
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


@pytest.mark.asyncio
@pytest.mark.parametrize("delegated", [False, True])
async def test_native_sessions_commit_whole_turn_after_execution(sdk, delegated):
    """Main and child histories remain unchanged until a complete turn settles.

    Args:
        sdk: Native runtime with isolated storage and model responses.
        delegated: Whether to execute a private child or the main conversation.
    """
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.astr_agent_runtime.main_session import MainAgentInput

    class EchoTool(FunctionTool):
        async def call(self, context):
            return "tool output"

    tool = EchoTool(name="echo", description="Echo", parameters={})
    sdk.manager.func_list.append(tool)
    sdk.root.delegable_tools = ToolSet([tool])
    sdk.config["agent"]["config"]["subagents"]["enabled"] = True
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def respond(**kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return LLMResponse(
                role="assistant",
                tools_call_name=["echo"],
                tools_call_ids=["echo-call"],
                tools_call_args=[{}],
            )
        entered.set()
        await release.wait()
        return LLMResponse(role="assistant", completion_text="Done")

    sdk.provider.text_chat.side_effect = respond
    if delegated:
        agent = await sdk.native.spawn_agent(
            sdk.root, [{"type": "plain", "text": "Initial"}]
        )
        session = await sdk.native.open_session(
            sdk.scope.umo, session_id=agent["conversation_id"]
        )
        turn = None
    else:
        session = await sdk.native.open_session(
            sdk.scope.umo, session_id=sdk.conversation.cid
        )
        turn = await session.run_turn(
            MainAgentInput(
                event=sdk.event,
                permissions=sdk.root.permissions,
                content=[PlainInput(text="Initial")],
            )
        )
    try:
        await asyncio.wait_for(entered.wait(), 3)
        assert await session.history() == []
        release.set()
        if turn is not None:
            assert (await turn.result()).text == "Done"
        else:
            result = await sdk.service.wait(sdk.root, [agent["agent_id"]], 2000, "all")
            assert result["agents"][0]["result"] == "Done"
        history = await session.history()
        assert "Initial" in str(history)
        assert "tool output" in str(history)
        assert any(message.get("tool_call_id") == "echo-call" for message in history)
        assert history[-1]["role"] == "assistant"
    finally:
        release.set()


@pytest.mark.asyncio
async def test_context_exposes_agent_facade_for_runtime_registration(environment):
    """Plugin registration reaches delegation without exposing internal services.

    Args:
        environment: Runtime services with an isolated plugin Context and store.
    """
    env = environment
    for name in ("subagents", "agent_configs", "agent_runtimes", "agent_runtime"):
        assert not hasattr(env.context, name)
    external = type(env.memory)()
    external.close = AsyncMock(wraps=external.close)
    env.context.agent.register_runtime("external", external)
    assert env.runtimes["external"] is external
    with pytest.raises(ValueError, match="already registered"):
        env.context.agent.register_runtime("external", external)
    with pytest.raises(TypeError, match="AgentRuntime"):
        env.context.agent.register_runtime("invalid", object())
    assert "invalid" not in env.runtimes
    selected = await env.save_agent("External", runtime="external")
    agent = await env.native.spawn_agent(
        env.root,
        [{"type": "plain", "text": "Task"}],
        config_id=selected.config_id,
    )
    result = await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert result["agents"][0]["state"] == "completed"
    assert env.store.get(agent["agent_id"], env.scope).runtime == "external"
    await env.context.agent.close()
    with pytest.raises(RuntimeError, match="unavailable"):
        env.context.agent.register_runtime("closed", type(env.memory)())
    await env.service.close()
    external.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_history_save_failure_is_not_reported_as_success(sdk):
    """Execution completion waits for history, with a stable persistence failure."""
    sdk.context.conversation_manager.update_conversation.side_effect = RuntimeError(
        "storage unavailable"
    )
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Persist this turn")],
        send_to_user=False,
    )
    result = await run.result()
    assert result.status == TurnStatus.FAILED
    assert result.error.code == "history_save_failed"
    events = [event async for event in run.events()]
    terminal = [event for event in events if event.type == "turn.finished"]
    assert len(terminal) == 1
    assert terminal[0].payload.result == result


@pytest.mark.asyncio
async def test_usage_events_are_snapshots_of_the_reported_requests(sdk):
    """Final usage and event snapshots must not multiply request charges."""
    from astrbot.core.provider.entities import TokenUsage

    sdk.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            completion_text="Done",
            usage=TokenUsage(input_other=10, input_cached=2, output=3),
        )
    ]
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Usage")],
        send_to_user=False,
    )
    result = await run.result()
    events = [event async for event in run.events()]
    requests = [event.payload for event in events if event.type == "request.finished"]
    assert len(requests) == 1
    assert result.usage.tokens.input_tokens == 12
    assert result.usage.tokens.cached_input_tokens == 2
    assert result.usage.tokens.total_tokens == 15
    assert result.usage.source == "requests"
    assert result.usage.complete
    snapshots = [
        event.payload.usage for event in events if event.type == "usage.updated"
    ]
    assert snapshots[-1] == result.usage
    assert all(snapshot.tokens.total_tokens == 15 for snapshot in snapshots)


@pytest.mark.asyncio
@pytest.mark.parametrize("send_to_user", [False, True])
async def test_registered_runtime_runs_without_native_request_construction(
    sdk, monkeypatch, send_to_user
):
    """The SDK admits public input and presents a foreign runtime's final output."""
    from astrbot.core.agent.runtime import AgentInput
    from astrbot.core.astr_agent_runtime.main_agent import builder

    sdk.config["agent"] = {"runtime": "memory", "config": {"model": "external"}}
    monkeypatch.setattr(
        builder,
        "build_main_agent",
        AsyncMock(side_effect=AssertionError("Native builder must not run")),
    )
    opened = []
    original = sdk.memory.open_session

    async def open_session(*args, **kwargs):
        opened.append(copy.deepcopy(kwargs.get("options")))
        return await original(*args, **kwargs)

    monkeypatch.setattr(sdk.memory, "open_session", open_session)
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="External reply")],
        send_to_user=send_to_user,
    )
    result = await run.result()
    assert result.text == "External reply"
    assert type(sdk.memory.inputs[0]) is AgentInput
    assert sdk.memory.inputs[0].plugin_tools is not None
    assert opened == [{"config": {"model": "external"}}]
    events = [event async for event in run.events()]
    assert all(event.session.runtime == "memory" for event in events)
    assert sdk.platform_send.await_count == int(send_to_user)
    if send_to_user:
        assert sdk.platform_send.await_args.args[1].get_plain_text() == "External reply"
    sdk.provider.text_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_follow_up_stays_bound_after_profile_runtime_changes(sdk):
    """Existing session handles continue their own runtime after profile edits."""
    sdk.config["agent"] = {"runtime": "memory", "config": {}}
    first = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="First")],
        send_to_user=False,
    )
    await first.result()
    sdk.config["agent"]["runtime"] = "astrbot"
    second = await first.follow_up(input_message=[PlainInput(text="Second")])
    assert second.session is first.session
    assert (await second.result()).text == "Second"
    sdk.provider.text_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_queued_input_rechecks_core_admission(sdk):
    """Core admission is enforced by the common session execution boundary."""
    sdk.config["agent"] = {"runtime": "memory", "config": {}}
    sdk.memory.release = asyncio.Event()
    first = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="First")],
        send_to_user=False,
    )
    await asyncio.wait_for(sdk.memory.started.get(), 2)
    queued = await first.follow_up(input_message=[PlainInput(text="Queued")])
    sdk.config["provider_settings"]["enable"] = False
    sdk.memory.release.set()
    await first.result()
    assert (await queued.result()).reason == "skipped"
    assert len(sdk.memory.inputs) == 1


@pytest.mark.asyncio
async def test_unregistered_runtime_fails_explicitly(sdk):
    sdk.config["agent"] = {"runtime": "missing", "config": {}}
    with pytest.raises(RuntimeError, match="Agent runtime unavailable: missing"):
        await sdk.context.agent.run_turn(
            umo=sdk.event.unified_msg_origin,
            input_message=[PlainInput(text="Input")],
            send_to_user=False,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("targeted_wakeup", [False, True])
async def test_message_pipeline_accepts_a_core_only_runtime(
    sdk, monkeypatch, targeted_wakeup
):
    """A runtime implementation needs only Core input, session and output contracts."""
    from astrbot.core.agent.output import PlainOutput
    from astrbot.core.agent.input import format_input_content
    from astrbot.core.agent.runtime import (
        AgentRuntime,
        AgentSessionRef,
        AgentSession,
        AgentInput,
        TurnResult,
    )
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        AgentRequestSubStage,
    )
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
    from astrbot.core.astr_agent_runtime.main_agent import builder

    inputs = []

    class CoreSession(AgentSession):
        async def execute_turn(self, turn):
            inputs.append(turn.input)
            text = (
                format_input_content(turn.input.content)
                if turn.input.content is not None
                else turn.input.event.message_str
            )
            return TurnResult(content=(PlainOutput(text=text),))

        async def history(self):
            return []

    class CoreRuntime(AgentRuntime):
        async def open_session(self, umo, *, session_id=None, options=None, input=None):
            assert options == (None if targeted_wakeup else {"config": {"model": "remote"}})
            assert session_id == ("external-session" if targeted_wakeup else None)
            return CoreSession("external-session", umo, runtime_name="external")

        async def close(self):
            pass

    sdk.context.agent.register_runtime("external", CoreRuntime())
    sdk.config["agent"] = {"runtime": "external", "config": {"model": "remote"}}
    sdk.config["provider_settings"]["wake_prefix"] = "ask "
    monkeypatch.setattr(
        builder,
        "build_main_agent",
        AsyncMock(side_effect=AssertionError("Native builder must not run")),
    )
    if targeted_wakeup:
        # An existing runtime session survives switching the profile to a legacy path.
        sdk.config["agent"] = {"runtime": "dify", "config": {}}
        event = AgentWakeupEvent(
            context=sdk.context,
            session=sdk.event.session,
            platform_meta=sdk.event.platform_meta,
            prompt="External platform input",
            source="plugin",
            agent_session=AgentSessionRef("external", "external-session"),
        )
    else:
        event = AstrMessageEvent(
            "ask   External platform input  \n",
            sdk.event.message_obj,
            sdk.event.platform_meta,
            sdk.event.session_id,
        )
    event.send_typing = AsyncMock()
    event.stop_typing = AsyncMock()
    event.send = AsyncMock()
    stage = AgentRequestSubStage()
    await stage.initialize(
        PipelineContext(
            sdk.config,
            sdk.context._star_manager,
            "profile",
            agent_runtimes=sdk.runtimes,
        )
    )
    outputs = []
    async for _ in stage.process(event):
        if event.get_result():
            outputs.append(event.get_result().get_plain_text())
    assert outputs == [
        "External platform input" if targeted_wakeup else "  External platform input  \n"
    ]
    assert type(inputs[0]) is AgentInput
    assert inputs[0].plugin_tools is not None
    assert not hasattr(inputs[0], "admit")
    assert not hasattr(inputs[0], "provider_wake_prefix")
    if not targeted_wakeup:
        assert event.message_str == "ask   External platform input  \n"
    sdk.provider.text_chat.assert_not_awaited()


@pytest.mark.asyncio
async def test_queued_foreign_input_refreshes_plugin_tools_and_skills(sdk, monkeypatch):
    """Revoking a profile plugin affects the next admitted turn's contributions."""
    from astrbot.core.skills.skill_manager import SkillInfo, SkillManager
    from astrbot.core.star import agent_capabilities

    sdk.config["agent"] = {"runtime": "memory", "config": {}}
    sdk.config["plugin_set"] = ["Allowed"]
    plugin = SimpleNamespace(
        name="Allowed", root_dir_name="allowed", activated=True, reserved=False
    )
    monkeypatch.setattr(agent_capabilities, "star_registry", [plugin])
    monkeypatch.setitem(agent_capabilities.star_map, "plugin.scope", plugin)
    tool = FunctionTool(
        name="scoped_tool",
        description="Scoped",
        parameters={"type": "object", "properties": {}},
        handler_module_path="plugin.scope",
    )
    sdk.context.get_llm_tool_manager().func_list.append(tool)
    skill = SkillInfo(
        name="scoped_skill",
        description="Scoped",
        path="SKILL.md",
        active=True,
        source_type="plugin",
        plugin_name="allowed",
    )
    monkeypatch.setattr(SkillManager, "list_skills", lambda *args, **kwargs: [skill])
    sdk.memory.release = asyncio.Event()
    first = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="First")],
        send_to_user=False,
    )
    await asyncio.wait_for(sdk.memory.started.get(), 2)
    assert sdk.memory.inputs[0].plugin_tools.get_tool("scoped_tool") is not None
    assert [entry.name for entry in sdk.memory.inputs[0].plugin_skills] == [
        "scoped_skill"
    ]
    queued = await first.follow_up(input_message=[PlainInput(text="Second")])
    sdk.config["plugin_set"] = []
    sdk.memory.release.set()
    await first.result()
    assert (await queued.result()).status == TurnStatus.COMPLETED
    assert sdk.memory.inputs[1].plugin_tools.get_tool("scoped_tool") is None
    assert sdk.memory.inputs[1].plugin_skills == []
