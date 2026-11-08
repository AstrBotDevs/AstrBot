import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.runtime import AgentSessionRef, InputReceipt, TurnResult
from astrbot.core.astr_agent_runtime import AstrAgentRuntime
from astrbot.core.astr_agent_runtime.main_agent import subagent
from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
from astrbot.core.astr_agent_runtime.subagents.store import AgentState, SubAgentStore
from astrbot.core.provider.entities import ProviderRequest
from astrbot.core.utils.active_event_registry import active_event_registry


@pytest.mark.asyncio
@pytest.mark.parametrize("parent_runtime", ["astrbot", "memory"])
async def test_result_steers_only_the_direct_parent_and_commits_after_receipt(
    environment,
    parent_runtime,
):
    env = environment
    parent = (
        await env.native.open_session(
            env.scope.umo, session_id=env.scope.conversation_id
        )
        if parent_runtime == "astrbot"
        else await env.memory.open_session(env.scope.umo)
    )
    parent_ref = AgentSessionRef(parent_runtime, parent.id)
    env.root.agent_session = parent_ref
    receipt = InputReceipt()
    submitted = asyncio.Event()

    def steer(input):
        submitted.set()
        assert input.content[0].type == "plain"
        assert "[Subagent results]" in input.content[0].text
        return receipt

    async def settled():
        parent.active_turn = None
        return TurnResult()

    parent.active_turn = SimpleNamespace(
        steer=MagicMock(side_effect=steer),
        result=settled,
        input=SimpleNamespace(event=env.event),
    )
    other = SimpleNamespace(steer=MagicMock(side_effect=AssertionError("Wrong parent")))
    env.native._active_main[env.scope.umo] = other
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Finished"}], runtime="memory"
    )
    await asyncio.wait_for(submitted.wait(), 1)
    assert agent["agent_id"] not in env.service._workers
    record = env.store.get(agent["agent_id"], env.scope)
    assert record.parent == parent_ref
    assert record.current.delivery == "pending"
    assert env.context.get_event_queue().empty()
    assert not env.wrapper.messages
    receipt.resolve(True)
    await asyncio.gather(*list(env.service.delivery._notifications.values()))
    assert record.current.delivery == "committed"
    other.steer.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("accepted", [False, True])
async def test_unconsumed_steering_queues_results_for_the_same_parent(
    environment, accepted
):
    env = environment
    parent = await env.native.open_session(
        env.scope.umo, session_id=env.scope.conversation_id
    )
    receipt = InputReceipt()
    attempted, release = asyncio.Event(), asyncio.Event()

    def steer(input):
        attempted.set()
        return receipt if accepted else None

    async def settled():
        await release.wait()
        parent.active_turn = None
        return TurnResult()

    parent.active_turn = SimpleNamespace(
        steer=steer, result=settled, input=SimpleNamespace(event=env.event)
    )
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Result body"}], runtime="memory"
    )
    await asyncio.wait_for(attempted.wait(), 1)
    assert agent["agent_id"] not in env.service._workers
    assert env.context.get_event_queue().empty()
    env.context.conversation_manager.get_curr_conversation_id.return_value = (
        "another-conversation"
    )
    receipt.resolve(False)
    release.set()
    await asyncio.gather(*list(env.service.delivery._notifications.values()))
    event = env.context.get_event_queue().get_nowait()
    assert event.agent_session == AgentSessionRef("astrbot", env.scope.conversation_id)
    assert "Result body" in event.message_str
    assert event.get_sender_id() == env.event.get_sender_id()
    assert event.unified_msg_origin == env.scope.umo
    assert env.store.get(agent["agent_id"], env.scope).current.delivery == "pending"


@pytest.mark.asyncio
@pytest.mark.parametrize("saved", [False, True])
@pytest.mark.parametrize("with_parent", [False, True])
async def test_restart_reconciles_result_receipts_from_parent_history(
    environment, saved, with_parent
):
    env = environment
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Finished"}], runtime="memory"
    )
    results = await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    if saved:
        env.conversation.history = json.dumps(results)
    await env.service.close()
    if not with_parent:
        row = await env.db.get_preference(
            "subagent_session", env.scope.umo, agent["agent_id"]
        )
        data = dict(row.value)
        data.pop("parent")
        data["scope"]["sender_id"] = data["owner"].pop("sender_id")
        await env.db.insert_preference_or_update(
            "subagent_session", env.scope.umo, agent["agent_id"], data
        )
    while not env.context.get_event_queue().empty():
        env.context.get_event_queue().get_nowait()
    restarted = SubAgentService(SubAgentStore(env.db), {"memory": env.memory})
    native = AstrAgentRuntime(
        env.context, agent_configs=env.agent_configs, subagents=restarted
    )
    restarted.runtimes["astrbot"] = native
    env.root.runtime = native
    await restarted.start(env.context)
    await asyncio.gather(*list(restarted.delivery._notifications.values()))
    assert env.context.get_event_queue().empty() == saved
    restored = restarted.store.get(agent["agent_id"], env.scope)
    assert restored.parent == AgentSessionRef("astrbot", env.scope.conversation_id)
    assert restored.runtime == "memory"
    assert restored.current.delivery == ("committed" if saved else "pending")
    assert restored.owner["sender_id"] == env.event.get_sender_id()
    if not saved:
        event = env.context.get_event_queue().get_nowait()
        assert event.get_sender_id() == env.event.get_sender_id()


@pytest.mark.asyncio
async def test_shutdown_and_restart_do_not_replay_unfinished_prompts(environment):
    env = environment
    env.memory.release = asyncio.Event()
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Running"}], runtime="memory"
    )
    conversation_id, _ = await asyncio.wait_for(env.memory.started.get(), 1)
    await env.service.send(
        env.root, agent["agent_id"], [{"type": "plain", "text": "Queued"}]
    )
    await env.service.close()
    restarted = SubAgentService(SubAgentStore(env.db), {"memory": env.memory})
    env.native.subagents = restarted
    await restarted.start(env.context)
    record = restarted.store.get(agent["agent_id"], env.scope)
    assert all(turn.state == AgentState.INTERRUPTED for turn in record.turns)
    assert len(env.memory.sessions[conversation_id]) == 1
    assert not restarted._workers
    env.memory.release.set()
    await restarted.send(
        env.root, record.agent_id, [{"type": "plain", "text": "Resume"}]
    )
    result = await restarted.wait(env.root, [record.agent_id], 2000, "all")
    assert result["agents"][0]["result"] == "Resume"
    assert record.conversation_id == conversation_id
    assert [batch[0]["text"] for batch in env.memory.sessions[conversation_id]] == [
        "Running",
        "Resume",
    ]


@pytest.mark.asyncio
async def test_native_history_survives_service_and_runner_restart(environment):
    env = environment
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Remember this"}]
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    await env.service.close()
    restarted = SubAgentService(SubAgentStore(env.db), {})
    native = AstrAgentRuntime(
        env.context, agent_configs=env.agent_configs, subagents=restarted
    )
    restarted.runtimes["astrbot"] = native
    env.root.runtime = native
    await restarted.start(env.context)
    await restarted.send(
        env.root, agent["agent_id"], [{"type": "plain", "text": "Continue"}]
    )
    result = await restarted.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert result["agents"][0]["state"] == "completed"
    assert "Remember this" in str(env.provider.text_chat.call_args.kwargs["contexts"])
    assert "Continue" in str(env.provider.text_chat.call_args.kwargs["contexts"])


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["deleted", "stopped"])
async def test_deleted_or_stopped_parents_are_not_woken(environment, reason):
    env = environment
    if reason == "deleted":
        env.context.conversation_manager.get_conversation.return_value = None
    else:
        active_event_registry.get_background_stop_signal(env.event).set()
    if reason == "stopped":
        with pytest.raises(ValueError, match="stopped"):
            await env.service.spawn(
                env.root, [{"type": "plain", "text": "Finished"}], runtime="memory"
            )
        return
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Finished"}], runtime="memory"
    )
    await env.service._workers[agent["agent_id"]]
    await asyncio.gather(*list(env.service.delivery._notifications.values()))
    assert env.context.get_event_queue().empty()


@pytest.mark.asyncio
@pytest.mark.parametrize("read_result", [False, True])
async def test_native_parent_waits_for_child_without_blocking_delivery(
    environment, monkeypatch, read_result
):
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.agent.runtime import AgentPermissions
    from astrbot.core.agent.tool import FunctionTool, ToolSet
    from astrbot.core.astr_agent_runtime import session as native_session
    from astrbot.core.astr_agent_runtime.context import AstrAgentContext
    from astrbot.core.astr_agent_runtime.hooks import MainAgentHooks
    from astrbot.core.astr_agent_runtime.main_agent import (
        MainAgentBuildConfig,
        MainAgentBuildResult,
        builder,
    )
    from astrbot.core.astr_agent_runtime.main_session import MainAgentInput
    from astrbot.core.astr_agent_runtime.runner import AgentRunner
    from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
    from astrbot.core.provider.entities import LLMResponse

    env = environment
    child_done, release, offered = asyncio.Event(), asyncio.Event(), asyncio.Event()
    child_ids = []
    parent = await env.native.open_session(
        env.scope.umo, session_id=env.scope.conversation_id
    )
    original_steer = parent.steer_turn

    def steer(turn, input):
        offered.set()
        return original_steer(turn, input)

    monkeypatch.setattr(parent, "steer_turn", steer)

    class WaitForChild(FunctionTool):
        async def call(self, context, **kwargs):
            child = await env.service.spawn(
                context.context,
                [{"type": "plain", "text": "Child answer"}],
                runtime="memory",
            )
            child_ids.append(child["agent_id"])
            if read_result:
                result = await env.service.wait(context.context, child_ids, 2000, "all")
                reply = json.dumps(result)
            else:
                await env.service._workers[child["agent_id"]]
                reply = "The tool finished"
            child_done.set()
            await release.wait()
            return reply

    async def build(*, req, **kwargs):
        req.func_tool = ToolSet(
            [WaitForChild(name="wait_for_child", description="Wait", parameters={})]
        )
        runner = AgentRunner()
        await runner.reset(
            provider=env.provider,
            request=req,
            run_context=ContextWrapper(
                context=AstrAgentContext(context=env.context, event=env.event)
            ),
            tool_executor=FunctionToolExecutor(),
            agent_hooks=MainAgentHooks(req),
            streaming=False,
        )
        return MainAgentBuildResult(runner, req, env.provider)

    async def save(umo, cid, **kwargs):
        env.conversation.history = json.dumps(kwargs["history"])

    env.context.conversation_manager.update_conversation.side_effect = save
    env.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["wait_for_child"],
            tools_call_ids=["one"],
            tools_call_args=[{}],
        ),
        LLMResponse(role="assistant", completion_text="Finished parent"),
    ]
    monkeypatch.setattr(builder, "build_main_agent", build)
    monkeypatch.setattr(native_session, "record_agent_stats", AsyncMock())
    monkeypatch.setattr(native_session.Metric, "upload", AsyncMock())
    turn = await parent.run_turn(
        MainAgentInput(
            event=env.event,
            permissions=AgentPermissions.from_event(env.event),
            request=ProviderRequest(
                prompt="Parent task", conversation=env.conversation
            ),
            build_config=MainAgentBuildConfig(
                tool_call_timeout=5, streaming_response=False
            ),
        )
    )
    await asyncio.wait_for(child_done.wait(), 2)
    if not read_result:
        await asyncio.wait_for(offered.wait(), 2)
        assert "Child answer" not in str(parent._runner.run_context.messages)
    assert not turn.done
    release.set()
    assert (await asyncio.wait_for(turn.result(), 2)).text == "Finished parent"
    await asyncio.wait_for(
        asyncio.gather(*list(env.service.delivery._notifications.values())), 2
    )
    assert env.store.get(child_ids[0], env.scope).current.delivery == "committed"
    assert "Child answer" in env.conversation.history
    assert env.context.get_event_queue().empty()


@pytest.mark.asyncio
async def test_idle_result_runs_through_pipeline_once_and_commits_to_parent(
    environment, monkeypatch
):
    import copy

    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.astr_agent_runtime import session as native_session
    from astrbot.core.astr_agent_runtime.context import AstrAgentContext
    from astrbot.core.astr_agent_runtime.hooks import MainAgentHooks
    from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildResult, builder
    from astrbot.core.astr_agent_runtime.main_agent.request import prepare_request
    from astrbot.core.astr_agent_runtime.runner import AgentRunner
    from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
    from astrbot.core.config.default import DEFAULT_CONFIG
    from astrbot.core.event_bus import EventBus
    from astrbot.core.pipeline.context import PipelineContext
    from astrbot.core.pipeline.scheduler import PipelineScheduler
    from astrbot.core.star.session_llm_manager import SessionServiceManager

    env = environment
    config = copy.deepcopy(DEFAULT_CONFIG)
    config["agent"]["config"]["subagents"] = env.config
    config["provider_settings"]["streaming_response"] = False
    env.context.get_config = lambda **_: config
    env.context.send_message = AsyncMock(return_value=True)
    monkeypatch.setattr(
        env.context, "get_using_tts_provider_async", AsyncMock(return_value=None)
    )
    committed = asyncio.Event()
    save_record = env.store.save

    async def persist(record):
        await save_record(record)
        if record.current.delivery == "committed":
            committed.set()

    monkeypatch.setattr(env.store, "save", persist)

    async def save(umo, cid, **kwargs):
        env.conversation.history = json.dumps(kwargs["history"])

    async def build(*, event, config, req=None, collected_input=None, **kwargs):
        prepared = await prepare_request(
            event, env.context, config, env.provider, req, collected_input
        )
        if not await subagent.apply_subagents(
            prepared.request, env.context, event, runtime=env.native
        ):
            return None
        runner = AgentRunner()
        await runner.reset(
            provider=env.provider,
            request=prepared.request,
            run_context=ContextWrapper(
                context=AstrAgentContext(context=env.context, event=event)
            ),
            tool_executor=FunctionToolExecutor(),
            agent_hooks=MainAgentHooks(prepared.request),
            streaming=False,
        )
        return MainAgentBuildResult(runner, prepared.request, env.provider)

    env.context.conversation_manager.update_conversation.side_effect = save
    monkeypatch.setattr(builder, "build_main_agent", build)
    monkeypatch.setattr(native_session, "record_agent_stats", AsyncMock())
    monkeypatch.setattr(native_session.Metric, "upload", AsyncMock())
    monkeypatch.setattr(
        SessionServiceManager,
        "should_process_llm_request",
        AsyncMock(return_value=True),
    )
    monkeypatch.setattr(
        SessionServiceManager, "is_session_enabled", AsyncMock(return_value=True)
    )
    scheduler = PipelineScheduler(
        PipelineContext(
            config,
            SimpleNamespace(context=env.context),
            "test",
            agent_runtimes=env.runtimes,
        )
    )
    await scheduler.initialize()
    bus = EventBus(
        env.context.get_event_queue(),
        {"test": scheduler},
        SimpleNamespace(get_conf_info=lambda _: {"id": "test"}),
    )
    dispatcher = asyncio.create_task(bus.dispatch())
    try:
        agent = await env.service.spawn(
            env.root, [{"type": "plain", "text": "Completed child"}], runtime="memory"
        )
        await env.service._workers[agent["agent_id"]]

        await asyncio.wait_for(committed.wait(), 3)
        await asyncio.gather(*list(bus._pending_tasks))
        assert env.provider.text_chat.await_count == 1
        assert (
            env.store.get(agent["agent_id"], env.scope).current.delivery == "committed"
        )
        assert "Completed child" in env.conversation.history
        env.context.send_message.assert_awaited_once()
    finally:
        dispatcher.cancel()
        for task in list(bus._pending_tasks):
            task.cancel()
        await asyncio.gather(
            dispatcher, *list(bus._pending_tasks), return_exceptions=True
        )
