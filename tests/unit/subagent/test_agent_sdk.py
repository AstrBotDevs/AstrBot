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
from astrbot.core.platform.astr_message_event import current_message_event, event_context
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
    """Save both modes and allow independent event readers without duplicate sends."""
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Video analysis complete")],
        send_to_user=send_to_user,
    )
    result = await asyncio.wait_for(run.result(), 3)
    assert result.status == TurnStatus.COMPLETED
    assert result.text == "Done"
    assert sdk.platform_send.await_count == int(send_to_user)
    events = [event async for event in run.events()]
    assert events[-1].type == "turn.finished"
    assert events[-1].payload.result == result
    history = json.loads(sdk.conversation.history)
    assert history[0]["role"] == "user"
    assert history[-1]["content"] == [{"type": "text", "text": "Done"}]


@pytest.mark.asyncio
async def test_follow_up_queues_and_retains_conversation_and_output_policy(sdk):
    """Bind follow-ups to their original conversation and read newly saved history."""
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
        cid="other", user_id=sdk.event.unified_msg_origin, history="[]", persona_id=None
    )
    sdk.context.conversation_manager.get_curr_conversation_id.return_value = "other"
    second = await first.follow_up(input_message=[PlainInput(text="Second input")])
    assert second.session.ref == first.session.ref
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
    """An input waiting behind another turn must respect newly disabled AI."""
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
    """Keep event, tool and Context sends explicit when automatic output is off."""

    async def respond(**kwargs):
        from astrbot.core.platform.astr_message_event import current_message_event

        event = current_message_event.get()
        wrapper = ContextWrapper(
            context=AstrAgentContext(context=sdk.context, event=event)
        )
        await SendMessageToUserTool().call(
            wrapper,
            messages=[
                {"type": "plain", "text": "Builtin message"},
                {"type": "image", "url": "https://example.invalid/result.png"},
            ],
        )
        assert await sdk.context.send_message(
            event.unified_msg_origin, MessageChain().message("Explicit plugin message")
        )
        return LLMResponse(role="assistant", completion_text="Final reply")

    sdk.provider.text_chat.side_effect = respond
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Deliver results")],
        send_to_user=False,
    )
    assert (await asyncio.wait_for(run.result(), 3)).status == TurnStatus.COMPLETED
    chains = [call.args[1] for call in sdk.platform_send.await_args_list]
    assert [chain.get_plain_text() for chain in chains] == [
        "Builtin message",
        "Explicit plugin message",
    ]
    assert isinstance(chains[0].chain[1], Image)


@pytest.mark.asyncio
@pytest.mark.parametrize("stop_at", [None, "waiting", "request"])
async def test_core_and_request_hooks_run_once_and_can_stop_input(
    sdk, monkeypatch, stop_at
):
    """Preserve event/ProviderRequest hooks for SDK input and honor termination."""
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
    """Inherit trusted caller identity and stop active SDK work on shutdown."""
    entered = asyncio.Event()

    observed = []

    async def respond(**kwargs):
        observed.append(current_message_event.get())
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
        await asyncio.wait_for(entered.wait(), 3)
        assert observed[0].get_sender_id() == "alice"
        assert observed[0].role == "member"
        await asyncio.wait_for(sdk.context.agent.close(), 3)
    assert (await run.result()).status == TurnStatus.CANCELLED
    assert sdk.conversation.history == "[]"


@pytest.mark.asyncio
async def test_stop_targets_registered_turns_across_runtimes(sdk):
    """Stop native and external work by UMO even after the profile changes."""
    from astrbot.builtin_stars.builtin_commands.commands.conversation import (
        ConversationCommands,
    )
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        AgentRequestSubStage,
    )
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

    entered = asyncio.Event()

    async def respond(**kwargs):
        entered.set()
        await asyncio.Event().wait()

    sdk.provider.text_chat.side_effect = respond
    native = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="Native input")],
        send_to_user=False,
    )
    await asyncio.wait_for(entered.wait(), 3)
    queued = await native.follow_up(input_message=[PlainInput(text="Queued input")])

    sdk.config["agent"] = {"runtime": "memory", "config": {}}
    sdk.config["provider_settings"]["wake_prefix"] = "ask "
    sdk.memory.release = asyncio.Event()
    event = AstrMessageEvent(
        "ask External input",
        sdk.event.message_obj,
        sdk.event.platform_meta,
        sdk.event.session_id,
    )
    stage = AgentRequestSubStage()
    await stage.initialize(
        PipelineContext(
            sdk.config,
            sdk.context._star_manager,
            "profile",
            agent_runtimes=sdk.runtimes,
        )
    )
    platform_turn = asyncio.create_task(anext(stage.process(event)))
    session_id, _ = await asyncio.wait_for(sdk.memory.started.get(), 3)
    external = sdk.memory.handles[session_id]
    external.request_stop_turn = AsyncMock(return_value=False)
    external.cancel_turn = AsyncMock()

    sdk.config["agent"]["runtime"] = "dify"
    commands = ConversationCommands(sdk.context)
    await commands.stop(sdk.event)
    await commands.stop(sdk.event)

    first, second, _ = await asyncio.wait_for(
        asyncio.gather(
            native.result(), queued.result(), platform_turn, return_exceptions=True
        ),
        3,
    )
    assert first.status == second.status == TurnStatus.CANCELLED
    assert platform_turn.cancelled()
    external.request_stop_turn.assert_awaited_once()
    external.cancel_turn.assert_awaited_once()
    assert "Output stopped." in sdk.conversation.history
    assert "Queued input" not in sdk.conversation.history
    sdk.provider.text_chat.assert_awaited_once()


@pytest.mark.asyncio
async def test_steering_reuses_native_safe_boundary(sdk):
    """Submit SDK text to the actual runner and settle its persistence receipt."""
    entered, release = asyncio.Event(), asyncio.Event()

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
    assert await run.steer(input_message=[PlainInput(text="Too late")]) is None


@pytest.mark.asyncio
async def test_portable_media_uses_the_normal_input_preprocessor(sdk, tmp_path):
    """Keep image and file input on the same preparation path as normal messages."""
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
    """Main and child histories remain unchanged until a complete turn settles."""
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
    sdk.memory.open_session = AsyncMock(wraps=sdk.memory.open_session)
    run = await sdk.context.agent.run_turn(
        umo=sdk.event.unified_msg_origin,
        input_message=[PlainInput(text="External reply")],
        send_to_user=send_to_user,
    )
    result = await run.result()
    assert result.text == "External reply"
    assert type(sdk.memory.inputs[0]) is AgentInput
    assert sdk.memory.inputs[0].plugin_tools is not None
    assert sdk.memory.open_session.call_args.kwargs["options"] == {
        "config": {"model": "external"}
    }
    events = [event async for event in run.events()]
    assert all(event.session.runtime == "memory" for event in events)
    assert sdk.platform_send.await_count == int(send_to_user)
    if send_to_user:
        assert sdk.platform_send.await_args.args[1].get_plain_text() == "External reply"
    sdk.config["agent"]["runtime"] = "astrbot"
    follow_up = await run.follow_up(
        input_message=[PlainInput(text="Continue")], send_to_user=False
    )
    assert follow_up.session.ref == run.session.ref
    assert (await follow_up.result()).text == "Continue"
    sdk.provider.text_chat.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("targeted_wakeup", [False, True])
async def test_message_pipeline_accepts_a_core_only_runtime(
    sdk, monkeypatch, targeted_wakeup
):
    """A runtime implementation needs only Core input, session and output contracts."""
    from astrbot.core.agent.runtime import AgentSessionRef
    from astrbot.core.astr_agent_runtime.main_agent import builder
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.process_stage.method.agent_request import (
        AgentRequestSubStage,
    )
    from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

    sdk.memory.open_session = AsyncMock(wraps=sdk.memory.open_session)
    sdk.config["agent"] = {"runtime": "memory", "config": {"model": "remote"}}
    sdk.config["provider_settings"]["wake_prefix"] = "ask "
    monkeypatch.setattr(
        builder,
        "build_main_agent",
        AsyncMock(side_effect=AssertionError("Native builder must not run")),
    )
    if targeted_wakeup:
        # An existing runtime session survives switching the profile to a legacy path.
        session = await sdk.memory.open_session(sdk.event.unified_msg_origin)
        sdk.config["agent"] = {"runtime": "dify", "config": {}}
        event = AgentWakeupEvent(
            context=sdk.context,
            session=sdk.event.session,
            platform_meta=sdk.event.platform_meta,
            prompt="External platform input",
            source="plugin",
            agent_session=AgentSessionRef("memory", session.id),
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
        "External platform input"
        if targeted_wakeup
        else "  External platform input  \n"
    ]
    assert sdk.memory.open_session.call_args.kwargs["options"] == (
        None if targeted_wakeup else {"config": {"model": "remote"}}
    )
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
