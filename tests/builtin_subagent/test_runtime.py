import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.builtin_stars.astrbot_plugin_subagent.context import SubAgentContext
from astrbot.builtin_stars.astrbot_plugin_subagent.execution import SubAgentExecutor
from astrbot.builtin_stars.astrbot_plugin_subagent.runtime import SubAgentState
from astrbot.builtin_stars.astrbot_plugin_subagent.store import SubAgentStore
from astrbot.builtin_stars.astrbot_plugin_subagent.tools import (
    SUBAGENT_TOOL_NAMES,
    CancelAgentTool,
    GetAgentResultTool,
    SendAgentMessageTool,
    SpawnAgentTool,
    SubAgentTemplate,
    WaitAgentTool,
)
from astrbot.core.agent.agent import Agent
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.provider.func_tool_manager import _PermissionGuardedTool
from astrbot.core.provider.provider import Provider
from astrbot.core.utils.session_lock import session_lock_manager


@pytest.mark.asyncio
async def test_spawn_parallel_private_context_and_wait_timeout(environment):
    env = environment
    started = asyncio.Queue()
    release = asyncio.Event()

    async def run(**kwargs):
        await started.put(kwargs)
        await release.wait()
        return LLMResponse(role="assistant", completion_text=kwargs["prompt"])

    env.context.tool_loop_agent = run
    tool = SpawnAgentTool([])
    env.wrapper.messages.append(Message(role="user", content="Main-only secret"))
    replies = [
        json.loads(await tool.call(env.wrapper, task=task)) for task in ("A", "B")
    ]
    calls = [await asyncio.wait_for(started.get(), 1) for _ in replies]
    assert all("Main-only secret" not in str(call["contexts"]) for call in calls)
    assert all(call["run_context"] is not env.wrapper for call in calls)
    assert calls[0]["run_context"] is not calls[1]["run_context"]
    ids = [reply["agent_id"] for reply in replies]
    waiting = json.loads(await WaitAgentTool().call(env.wrapper, ids, timeout_ms=0))
    assert waiting["timed_out"]
    assert all(not env.runtime._instances[id_].execution_task.done() for id_ in ids)
    release.set()
    finished = json.loads(
        await WaitAgentTool().call(env.wrapper, ids, timeout_ms=1000, mode="all")
    )
    assert not finished["timed_out"]
    assert {item["result"] for item in finished["agents"]} == {"A", "B"}
    assert len(finished["receipts"]) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "expert_provider,kwargs,expected_name,expected_provider",
    [
        (None, {}, "worker", "model"),
        (
            None,
            {"name": "  资料检索  ", "provider_id": " alternate "},
            "资料检索",
            "alternate",
        ),
        ("expert-model", {"template": "expert"}, "expert", "expert-model"),
        (None, {"template": "expert"}, "expert", "model"),
        (
            "expert-model",
            {"template": "expert", "name": "reviewer"},
            "reviewer",
            "expert-model",
        ),
        (
            "expert-model",
            {"template": "expert", "provider_id": "alternate"},
            "expert",
            "alternate",
        ),
        (
            "expert-model",
            {"template": "expert", "name": "reviewer", "provider_id": "alternate"},
            "reviewer",
            "alternate",
        ),
    ],
)
async def test_spawn_name_and_provider_overrides_are_private_and_persist(
    environment, expert_provider, kwargs, expected_name, expected_provider
):
    env = environment
    calls = []

    async def run(**arguments):
        calls.append(arguments)
        return LLMResponse(role="assistant", completion_text="Done")

    env.context.tool_loop_agent = run
    expert = SubAgentTemplate(
        Agent(name="expert", instructions="Expert instructions", tools=[]),
        provider_id=expert_provider,
    )
    tool = SpawnAgentTool([expert])
    assert {"name", "provider_id"} <= tool.parameters["properties"].keys()
    reply = json.loads(await tool.call(env.wrapper, task="Task", **kwargs))
    assert reply["name"] == expected_name
    assert reply["provider_id"] == expected_provider
    worker = env.runtime._instances[reply["agent_id"]]
    assert worker.to_dict()["provider_id"] == expected_provider
    await asyncio.wait_for(worker.execution_task, 2)
    assert worker.state == SubAgentState.COMPLETED
    assert worker.to_dict()["name"] == expected_name
    assert worker.provider_id == expected_provider
    assert calls[0]["chat_provider_id"] == expected_provider
    assert expert.agent.name == "expert"
    assert expert.provider_id == expert_provider
    if "template" in kwargs:
        assert calls[0]["system_prompt"] == "Expert instructions"

    await SendAgentMessageTool().call(env.wrapper, worker.agent_id, "Continue")
    await asyncio.wait_for(worker.execution_task, 2)
    assert worker.agent.name == expected_name
    assert calls[1]["chat_provider_id"] == expected_provider
    await env.runtime.checkpoint()
    row = await env.db.get_preference(
        "subagent_runtime",
        env.runtime.storage_scope[0],
        json.dumps(env.runtime.storage_scope[1:]),
    )
    entry = next(
        item for item in row.value["workers"] if item["agent_id"] == worker.agent_id
    )
    assert entry["name"] == expected_name
    assert entry["provider_id"] == expected_provider


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["name", "provider_id"])
@pytest.mark.parametrize("value", ["", "   ", 123])
async def test_spawn_rejects_invalid_overrides_before_creating_worker(
    environment, field, value
):
    with pytest.raises(ValueError, match=field):
        await SpawnAgentTool([]).call(
            environment.wrapper, task="Task", **{field: value}
        )
    assert not environment.runtime._instances


@pytest.mark.asyncio
async def test_spawn_catalog_refreshes_in_real_provider_schemas(environment):
    env = environment
    spawn = env.plugin.spawn_tool
    env.context.provider_manager.provider_insts = [
        SimpleNamespace(
            provider_config={"id": "fast", "api_key": "private-provider-key"},
            get_model=lambda: "fast-model",
        ),
        SimpleNamespace(
            provider_config={"id": "deep", "api_base": "private-provider-url"},
            get_model=lambda: "reasoning-model",
        ),
    ]
    req = ProviderRequest(conversation=env.conversation)
    await env.plugin.prepare_request(env.event, req)
    schemas = req.func_tool.openai_schema()
    parameters = next(
        tool["function"]["parameters"]
        for tool in schemas
        if tool["function"]["name"] == "spawn_agent"
    )
    choice = parameters["properties"]["provider_id"]
    assert choice["enum"] == ["fast", "deep"]
    assert "fast-model" in choice["description"]
    assert "reasoning-model" in choice["description"]
    assert "private-provider" not in json.dumps(schemas)
    anthropic = next(
        tool
        for tool in req.func_tool.anthropic_schema()
        if tool["name"] == "spawn_agent"
    )
    assert anthropic["input_schema"]["properties"]["provider_id"] == choice

    # Provider removal and model edits appear on the next request.
    env.context.provider_manager.provider_insts = [
        SimpleNamespace(
            provider_config={"id": "fast"}, get_model=lambda: "updated-model"
        )
    ]
    updated = ProviderRequest(conversation=env.conversation)
    await env.plugin.prepare_request(env.event, updated)
    current = updated.func_tool.get_tool("spawn_agent").parameters["properties"][
        "provider_id"
    ]
    assert current["enum"] == ["fast"]
    assert "updated-model" in current["description"]
    assert "reasoning-model" not in current["description"]
    assert choice["enum"] == ["fast", "deep"]
    assert env.plugin.spawn_tool is spawn

    # Revalidate against the live catalog, even for a choice advertised earlier.
    with pytest.raises(ValueError, match='Available chat provider IDs: \\["fast"\\]'):
        await spawn.call(env.wrapper, task="Task", provider_id="deep")
    assert not env.runtime._instances

    env.context.provider_manager.provider_insts = []
    empty = ProviderRequest(conversation=env.conversation)
    await env.plugin.prepare_request(env.event, empty)
    choice = empty.func_tool.get_tool("spawn_agent").parameters["properties"][
        "provider_id"
    ]
    assert "enum" not in choice
    assert "No chat providers" in choice["description"]
    assert "provider_id" not in spawn.parameters["required"]
    with pytest.raises(ValueError, match="Available chat provider IDs: \\[\\]"):
        await spawn.call(env.wrapper, task="Task", provider_id="fast")


@pytest.mark.asyncio
async def test_main_hooks_keep_tools_and_bind_context(environment):
    env = environment
    original = FunctionTool(name="shared", description="Shared", parameters={})
    req = ProviderRequest(func_tool=ToolSet([original]), conversation=env.conversation)
    await env.plugin.prepare_request(env.event, req)
    assert set(req.func_tool.names()) == SUBAGENT_TOOL_NAMES | {"shared"}
    assert isinstance(req.func_tool.get_tool("spawn_agent"), _PermissionGuardedTool)
    wrapper = ContextWrapper(
        context=AstrAgentContext(context=env.context, event=env.event)
    )
    wrapper.runner = SimpleNamespace(req=req)
    await env.plugin.begin(env.event, wrapper)
    assert isinstance(wrapper.context, SubAgentContext)
    assert wrapper.context.delegable_tools.names() == ["shared"]
    assert not env.runtime.parent_idle.is_set()
    await env.plugin.done(env.event, wrapper, None)
    assert env.runtime.parent_idle.is_set()


@pytest.mark.asyncio
async def test_workers_coexist_with_legacy_experts_without_delegating(environment):
    from astrbot.core.subagent_orchestrator import SubAgentOrchestrator

    env = environment
    env.context.persona_manager.get_persona_v3_by_id.return_value = None
    orchestrator = SubAgentOrchestrator(env.manager, env.context.persona_manager)
    await orchestrator.reload_from_config(
        {"agents": [{"name": "legacy_expert", "tools": []}]}
    )
    env.context.subagent_orchestrator = orchestrator
    legacy = orchestrator.handoffs[0]
    shared = FunctionTool(name="shared", description="Shared", parameters={})
    env.manager.func_list.append(legacy)
    env.wrapper.context.delegable_tools = ToolSet([legacy, shared])
    calls = []

    async def run(**kwargs):
        calls.append(kwargs)
        return LLMResponse(role="assistant", completion_text="Worker completed")

    env.context.tool_loop_agent = run
    reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Independent"))
    worker = env.runtime._instances[reply["agent_id"]]
    await asyncio.wait_for(worker.execution_task, 2)
    assert worker.state == SubAgentState.COMPLETED
    assert calls[0]["tools"].names() == ["shared"]
    assert env.context.subagent_orchestrator.handoffs == [legacy]
    assert legacy.active


@pytest.mark.asyncio
async def test_sdk_reuses_worker_wrapper_and_steers_real_loop(environment):
    env = environment
    tool_started, release = asyncio.Event(), asyncio.Event()

    class BlockingTool(FunctionTool):
        async def call(self, context, **kwargs):
            tool_started.set()
            await release.wait()
            return "tool output"

    tool = BlockingTool(name="blocking", description="Wait", parameters={})
    env.wrapper.context.delegable_tools.add_tool(tool)
    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "model", "modalities": ["tool_use"]}
    provider.get_model.return_value = "test-model"
    provider.text_chat = AsyncMock(
        side_effect=[
            LLMResponse(
                role="assistant",
                tools_call_name=["blocking"],
                tools_call_ids=["one"],
                tools_call_args=[{}],
            ),
            LLMResponse(role="assistant", completion_text="Finished"),
        ]
    )
    env.context.provider_manager.get_provider_by_id = AsyncMock(return_value=provider)
    reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Worker task"))
    worker = env.runtime._instances[reply["agent_id"]]
    await asyncio.wait_for(tool_started.wait(), 2)
    assert worker.runner is worker.run_context.runner
    await SendAgentMessageTool().call(env.wrapper, worker.agent_id, "New instruction")
    release.set()
    await asyncio.wait_for(worker.execution_task, 3)
    assert worker.state == SubAgentState.COMPLETED
    assert worker.turn_id == 1
    assert "New instruction" in json.dumps(
        provider.text_chat.call_args_list[1].kwargs["contexts"]
    )
    assert len(worker.run_context.messages) >= 4


@pytest.mark.asyncio
async def test_followup_after_complete_preserves_worker_history(environment):
    env = environment
    calls = []

    async def run(**kwargs):
        calls.append(kwargs)
        wrapper = kwargs["run_context"]
        wrapper.messages = list(kwargs["contexts"] or [])
        if kwargs["prompt"]:
            wrapper.messages.append(Message(role="user", content=kwargs["prompt"]))
        wrapper.messages.append(Message(role="assistant", content="First result"))
        return LLMResponse(role="assistant", completion_text="done")

    env.context.tool_loop_agent = run
    reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Initial task"))
    worker = env.runtime._instances[reply["agent_id"]]
    await worker.execution_task
    await SendAgentMessageTool().call(env.wrapper, worker.agent_id, "Continue")
    await worker.execution_task
    assert worker.turn_id == 2
    assert "Initial task" in str(calls[1]["contexts"])
    assert "Continue" in str(calls[1]["contexts"])
    assert len(env.runtime._completions) == 2


@pytest.mark.asyncio
async def test_followup_during_final_response_starts_next_turn(environment):
    env = environment
    started, release = asyncio.Event(), asyncio.Event()
    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "model", "modalities": ["tool_use"]}
    provider.get_model.return_value = "test-model"
    calls = []

    async def response(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            started.set()
            await release.wait()
        return LLMResponse(role="assistant", completion_text="done")

    provider.text_chat = response
    env.context.provider_manager.get_provider_by_id = AsyncMock(return_value=provider)
    reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Initial"))
    worker = env.runtime._instances[reply["agent_id"]]
    await asyncio.wait_for(started.wait(), 2)
    await SendAgentMessageTool().call(env.wrapper, worker.agent_id, "Late input")
    first = worker.execution_task
    release.set()
    await asyncio.wait_for(first, 2)
    await asyncio.wait_for(worker.execution_task, 2)
    assert worker.turn_id == 2
    assert "Late input" in str(calls[1]["contexts"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "environment", ["test:FriendMessage:alice", "test:GroupMessage:team"], indirect=True
)
async def test_idle_delivery_waits_for_history_save_and_original_conversation(
    environment,
):
    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    worker.finish(SubAgentState.COMPLETED, result="Result")
    env.runtime.publish_result(worker)
    async with session_lock_manager.acquire_lock(env.event.unified_msg_origin):
        delivery = asyncio.create_task(
            SubAgentExecutor._dispatch_subagent_results(env.wrapper)
        )
        await asyncio.sleep(0)
        assert env.queue.empty()
    await asyncio.wait_for(delivery, 1)
    event = env.queue.get_nowait()
    assert event.get_message_type() == env.event.get_message_type()
    assert event.get_extra("_subagent_wakeup") == env.runtime.storage_scope
    assert event.get_sender_id() == env.event.get_sender_id()
    req = ProviderRequest(conversation=env.conversation)
    await env.plugin.prepare_request(event, req)
    assert not event.is_stopped()
    env.runtime.receive_results(env.wrapper)
    assert env.wrapper.messages[-1].role == "user"
    assert "[subagent-result:" in str(env.wrapper.messages[-1].content)


@pytest.mark.asyncio
async def test_receipts_survive_restart_only_after_saved_history(environment):
    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    worker.finish(SubAgentState.COMPLETED, result="Result")
    env.runtime.publish_result(worker)
    receipt = json.loads(await GetAgentResultTool().call(env.wrapper, worker.agent_id))[
        "receipt"
    ]
    row = await env.db.get_preference(
        "subagent_runtime",
        env.runtime.storage_scope[0],
        json.dumps(env.runtime.storage_scope[1:]),
    )
    restored = env.plugin.orchestrator.store._restore(
        row.value, env.wrapper.context, env.runtime.storage_scope
    )
    assert (worker.agent_id, 1) in restored._pending_results
    await env.plugin.orchestrator.store.reconcile(env.runtime, json.dumps([receipt]))
    row = await env.db.get_preference(
        "subagent_runtime",
        env.runtime.storage_scope[0],
        json.dumps(env.runtime.storage_scope[1:]),
    )
    restored = env.plugin.orchestrator.store._restore(
        row.value, env.wrapper.context, env.runtime.storage_scope
    )
    assert not restored._pending_results


@pytest.mark.asyncio
async def test_cancel_queued_worker_and_no_recursive_controls(environment):
    env = environment
    env.context.tool_loop_agent = AsyncMock(
        return_value=LLMResponse(role="assistant", completion_text="done")
    )
    reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Task"))
    worker = env.runtime._instances[reply["agent_id"]]
    with pytest.raises(ValueError, match="cannot spawn"):
        await SpawnAgentTool([]).call(worker.run_context, task="Recursive")
    await CancelAgentTool().call(env.wrapper, worker.agent_id)
    await asyncio.gather(worker.execution_task, return_exceptions=True)
    await asyncio.sleep(0)
    assert worker.state == SubAgentState.CANCELLED
    assert not env.context.tool_loop_agent.called


@pytest.mark.asyncio
async def test_restore_running_marks_interrupted_without_replaying(environment):
    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    await env.runtime.checkpoint()
    store = SubAgentStore(env.db)
    other = SubAgentContext(
        context=env.context, event=env.event, conversation_id="original"
    )
    await store.bind(other)
    restored = other.subagent_runtime._instances[worker.agent_id]
    assert restored.state == SubAgentState.INTERRUPTED
    assert restored.execution_task is None


@pytest.mark.asyncio
async def test_sdk_rejects_wrapper_from_another_event(environment):
    env = environment
    provider = MagicMock(spec=Provider)
    env.context.provider_manager.get_provider_by_id = AsyncMock(return_value=provider)
    env.wrapper.context.event = MagicMock()
    with pytest.raises(ValueError, match="must belong"):
        await env.context.tool_loop_agent(
            event=env.event, chat_provider_id="model", run_context=env.wrapper
        )


@pytest.mark.asyncio
async def test_runtime_view_uses_standard_plugin_request(environment):
    from starlette.requests import Request

    from astrbot.api.web import PluginRequest, bind_request_context

    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"),
        parent_context=env.wrapper,
        task="Task",
        provider_id="model",
    )
    worker.run_context.messages.append(Message(role="user", content="Worker task"))
    raw = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/runtime",
            "headers": [],
            "query_string": f"agent_id={worker.agent_id}".encode(),
        }
    )
    with bind_request_context(PluginRequest(raw, username="admin")):
        response = await env.plugin.runtime_view()
    assert response.status_code == 200
    record = json.loads(response.body)["data"]["agents"][0]
    assert record["agent_id"] == worker.agent_id
    assert record["name"] == "worker"
    assert record["provider_id"] == "model"
    assert "Worker task" in str(record["messages"])


@pytest.mark.asyncio
async def test_duplicate_dispatch_keeps_one_queued_wakeup(environment):
    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    worker.finish(SubAgentState.COMPLETED, result="Result")
    env.runtime.publish_result(worker)
    await SubAgentExecutor._dispatch_subagent_results(env.wrapper)
    await SubAgentExecutor._dispatch_subagent_results(env.wrapper)
    await SubAgentExecutor._dispatch_subagent_results(env.wrapper)
    assert env.queue.qsize() == 1
    assert env.runtime.wakeup_queued


@pytest.mark.asyncio
@pytest.mark.parametrize("current_cid", ["another-conversation", None])
async def test_switched_conversation_does_not_enqueue_old_results(
    environment, current_cid
):
    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    worker.finish(SubAgentState.COMPLETED, result="Result")
    env.runtime.publish_result(worker)
    env.context.conversation_manager.get_curr_conversation_id.return_value = current_cid
    await SubAgentExecutor._dispatch_subagent_results(env.wrapper)
    assert env.queue.empty()
    assert not env.runtime.wakeup_queued
    assert (worker.agent_id, worker.turn_id) in env.runtime._pending_results


@pytest.mark.asyncio
@pytest.mark.parametrize("request_cid", ["original", "another-conversation"])
async def test_switch_after_enqueue_rejects_wakeup_and_clears_original_flag(
    environment, request_cid
):
    from astrbot.core.pipeline.context_utils import call_event_hook
    from astrbot.core.star.star_handler import EventType

    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    worker.finish(SubAgentState.COMPLETED, result="Result")
    env.runtime.publish_result(worker)
    await SubAgentExecutor._dispatch_subagent_results(env.wrapper)
    event = env.queue.get_nowait()
    assert env.runtime.wakeup_queued
    env.context.conversation_manager.get_curr_conversation_id.return_value = (
        "another-conversation"
    )
    req = ProviderRequest(conversation=SimpleNamespace(cid=request_cid))
    assert await call_event_hook(event, EventType.OnLLMRequestEvent, req)
    assert event.is_stopped()
    assert not env.runtime.wakeup_queued
    assert req.func_tool is None
    assert (worker.agent_id, worker.turn_id) in env.runtime._pending_results


@pytest.mark.asyncio
async def test_manual_stop_blocks_an_already_queued_wakeup(environment):
    from astrbot.core.utils.active_event_registry import active_event_registry

    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    worker.finish(SubAgentState.COMPLETED, result="Result")
    env.runtime.publish_result(worker)
    await SubAgentExecutor._dispatch_subagent_results(env.wrapper)
    event = env.queue.get_nowait()
    active_event_registry.register(env.event)
    try:
        active_event_registry.request_agent_stop_all(env.event.unified_msg_origin)
    finally:
        active_event_registry.unregister(env.event)
    await env.plugin.prepare_request(
        event, ProviderRequest(conversation=env.conversation)
    )
    assert event.is_stopped()
    assert not env.runtime.wakeup_queued


@pytest.mark.asyncio
@pytest.mark.parametrize("current_cid", ["original", "another-conversation", None])
async def test_restart_only_wakes_the_current_conversation(environment, current_cid):
    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    worker.start()
    worker.finish(SubAgentState.COMPLETED, result="Result")
    env.runtime.publish_result(worker)
    await env.runtime.checkpoint()
    env.context.conversation_manager.get_curr_conversation_id.return_value = current_cid
    store = SubAgentStore(env.db)
    store.settings = env.config
    try:
        await store.recover(env.context)
        restored = store.runtimes[env.runtime.storage_scope]
        if restored.wakeup_task is not None:
            await asyncio.wait_for(restored.wakeup_task, 1)
        assert (worker.agent_id, worker.turn_id) in restored._pending_results
        if current_cid == "original":
            event = env.queue.get_nowait()
            assert event.get_extra("_subagent_wakeup") == env.runtime.storage_scope
        else:
            assert env.queue.empty()
            assert not restored.wakeup_queued
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_same_conversation_another_sender_cannot_find_worker(environment):
    env = environment
    worker = env.runtime.create_instance(
        agent=Agent(name="worker"), parent_context=env.wrapper, task="Task"
    )
    from copy import copy

    event = copy(env.event)
    event.message_obj = copy(event.message_obj)
    event.message_obj.sender = copy(event.message_obj.sender)
    event.message_obj.sender.user_id = "bob"
    parent = SubAgentContext(
        context=env.context, event=event, conversation_id="original"
    )
    await env.plugin.orchestrator.store.bind(parent)
    with pytest.raises(ValueError, match="Unknown subagent"):
        await GetAgentResultTool().call(ContextWrapper(context=parent), worker.agent_id)


@pytest.mark.asyncio
async def test_main_tool_loop_spawns_then_wakes_through_plugin_hooks(environment):
    from astrbot.core.agent.message import dump_messages_with_checkpoints
    from astrbot.core.agent.runners.tool_loop_agent_runner import ToolLoopAgentRunner
    from astrbot.core.astr_agent_hooks import MainAgentHooks
    from astrbot.core.astr_agent_tool_exec import FunctionToolExecutor
    from astrbot.core.pipeline.context_utils import call_event_hook
    from astrbot.core.star.star_handler import EventType

    env = environment
    release = asyncio.Event()

    async def worker_run(**kwargs):
        await release.wait()
        return LLMResponse(role="assistant", completion_text="Verified worker result")

    env.context.tool_loop_agent = worker_run
    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "main", "modalities": ["tool_use"]}
    provider.get_model.return_value = "main-test"
    provider.text_chat = AsyncMock(
        side_effect=[
            LLMResponse(
                role="assistant",
                tools_call_name=["spawn_agent"],
                tools_call_ids=["spawn"],
                tools_call_args=[{"task": "Verify the implementation"}],
            ),
            LLMResponse(role="assistant", completion_text="Delegated"),
            LLMResponse(
                role="assistant", completion_text="Worker verified the implementation"
            ),
        ]
    )
    req = ProviderRequest(prompt="Original task", conversation=env.conversation)
    assert not await call_event_hook(env.event, EventType.OnLLMRequestEvent, req)
    main = ToolLoopAgentRunner()
    wrapper = ContextWrapper(
        context=AstrAgentContext(context=env.context, event=env.event)
    )
    async with session_lock_manager.acquire_lock(env.event.unified_msg_origin):
        await main.reset(
            provider=provider,
            request=req,
            run_context=wrapper,
            tool_executor=FunctionToolExecutor(),
            agent_hooks=MainAgentHooks(),
        )
        async for _ in main.step_until_done(5):
            pass
        assert isinstance(wrapper.context, SubAgentContext)
        assert len(env.runtime._instances) == 1
        assert main.get_final_llm_resp().completion_text == "Delegated"
        env.conversation.history = json.dumps(
            dump_messages_with_checkpoints(wrapper.messages)
        )
    worker = next(iter(env.runtime._instances.values()))
    release.set()
    await asyncio.wait_for(worker.execution_task, 2)
    wakeup = await asyncio.wait_for(env.queue.get(), 2)
    assert wakeup.get_extra("_subagent_wakeup") == env.runtime.storage_scope
    req = ProviderRequest(
        prompt=wakeup.message_str,
        contexts=json.loads(env.conversation.history),
        conversation=env.conversation,
    )
    assert not await call_event_hook(wakeup, EventType.OnLLMRequestEvent, req)
    resumed = ContextWrapper(
        context=AstrAgentContext(context=env.context, event=wakeup)
    )
    async with session_lock_manager.acquire_lock(wakeup.unified_msg_origin):
        await main.reset(
            provider=provider,
            request=req,
            run_context=resumed,
            tool_executor=FunctionToolExecutor(),
            agent_hooks=MainAgentHooks(),
        )
        async for _ in main.step_until_done(5):
            pass
        env.conversation.history = json.dumps(
            dump_messages_with_checkpoints(resumed.messages)
        )
    await SubAgentExecutor._dispatch_subagent_results(resumed)
    assert "Verified worker result" in str(
        provider.text_chat.call_args_list[-1].kwargs["contexts"]
    )
    assert (worker.agent_id, 1) in env.runtime._durable_received
    assert env.queue.empty()


@pytest.mark.asyncio
async def test_queued_timeout_counts_waiting_time_and_releases_no_provider(environment):
    env = environment
    env.config.update(max_concurrent_agents=1, task_timeout=1)
    env.context.tool_loop_agent = AsyncMock()
    async with env.runtime.scheduler.slot(env.event.unified_msg_origin, 1):
        reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Queued"))
        worker = env.runtime._instances[reply["agent_id"]]
        await asyncio.wait_for(worker.execution_task, 2)
    assert worker.state == SubAgentState.TIMED_OUT
    env.context.tool_loop_agent.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["cancel", "timeout", "provider-error"])
async def test_worker_failure_leaves_shell_sessions_to_existing_lifecycle(
    environment, monkeypatch, outcome
):
    import os
    import shlex
    import sys

    from astrbot.core.computer.booters.local import LocalShellComponent

    env = environment
    shell = LocalShellComponent()
    monkeypatch.setattr(
        "astrbot.core.computer.computer_client.local_booter",
        SimpleNamespace(shell=shell),
    )
    command = (
        "& '" + sys.executable.replace("'", "''") + "' -c 'import time; time.sleep(30)'"
        if os.name == "nt"
        else shlex.join([sys.executable, "-c", "import time; time.sleep(30)"])
    )
    started = asyncio.Event()
    created_sessions = []

    async def run(**kwargs):
        session = await shell.exec_managed(
            command,
            owner_id=env.event.unified_msg_origin,
            creator_id=env.event.get_sender_id(),
            creator_is_admin=False,
            sandboxed=False,
            permission_check=lambda: True,
            yield_time_ms=0,
        )
        created_sessions.append(session["session_id"])
        started.set()
        if outcome == "provider-error":
            return LLMResponse(role="err", completion_text="Provider unavailable")
        await asyncio.Event().wait()

    env.context.tool_loop_agent = run
    if outcome == "timeout":
        env.config["task_timeout"] = 1
    try:
        sibling = await shell.exec_managed(
            command,
            owner_id=env.event.unified_msg_origin,
            creator_id=env.event.get_sender_id(),
            creator_is_admin=False,
            sandboxed=False,
            permission_check=lambda: True,
            yield_time_ms=0,
        )
        reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Run tool"))
        worker = env.runtime._instances[reply["agent_id"]]
        await asyncio.wait_for(started.wait(), 3)
        if outcome == "cancel":
            await CancelAgentTool().call(env.wrapper, worker.agent_id)
        await asyncio.wait_for(
            asyncio.gather(worker.execution_task, return_exceptions=True), 10
        )
        assert (
            worker.state
            == {
                "cancel": SubAgentState.CANCELLED,
                "timeout": SubAgentState.TIMED_OUT,
                "provider-error": SubAgentState.FAILED,
            }[outcome]
        )
        assert set(shell._sessions) == {sibling["session_id"], *created_sessions}
        assert len(shell._sessions) == 2
        assert all(
            session.process.returncode is None for session in shell._sessions.values()
        )
    finally:
        await shell.shutdown_sessions()


@pytest.mark.asyncio
async def test_cancel_mid_tool_saves_only_complete_steps_and_resumes(environment):
    env = environment
    started = asyncio.Event()

    class BlockingTool(FunctionTool):
        async def call(self, context, **kwargs):
            started.set()
            await asyncio.Event().wait()

    tool = BlockingTool(name="blocking", description="Blocking", parameters={})
    env.wrapper.context.delegable_tools.add_tool(tool)
    provider = MagicMock(spec=Provider)
    provider.provider_config = {"id": "model", "modalities": ["tool_use"]}
    provider.get_model.return_value = "test-model"
    provider.text_chat = AsyncMock(
        side_effect=[
            LLMResponse(
                role="assistant",
                tools_call_name=["blocking"],
                tools_call_ids=["in-flight"],
                tools_call_args=[{}],
            ),
            LLMResponse(role="assistant", completion_text="Resumed"),
        ]
    )
    env.context.provider_manager.get_provider_by_id = AsyncMock(return_value=provider)
    reply = json.loads(await SpawnAgentTool([]).call(env.wrapper, task="Initial task"))
    worker = env.runtime._instances[reply["agent_id"]]
    await asyncio.wait_for(started.wait(), 2)
    await env.runtime.checkpoint()
    row = await env.db.get_preference(
        "subagent_runtime",
        env.runtime.storage_scope[0],
        json.dumps(env.runtime.storage_scope[1:]),
    )
    assert "in-flight" not in json.dumps(row.value["workers"][0]["messages"])
    await CancelAgentTool().call(env.wrapper, worker.agent_id)
    await asyncio.gather(worker.execution_task, return_exceptions=True)
    assert "in-flight" not in str(worker.run_context.messages)
    await SendAgentMessageTool().call(
        env.wrapper, worker.agent_id, "Continue without replaying the tool"
    )
    await asyncio.wait_for(worker.execution_task, 2)
    assert worker.state == SubAgentState.COMPLETED
    assert worker.turn_id == 2
    assert "in-flight" not in str(
        provider.text_chat.call_args_list[-1].kwargs["contexts"]
    )


@pytest.mark.asyncio
async def test_template_initialization_preserves_loader_tool_activation(environment):
    env = environment
    env.plugin.spawn_tool.active = False
    env.config["agents"] = [
        {"name": "expert", "system_prompt": "Expert prompt", "tools": []}
    ]
    env.context.persona_manager.get_persona_v3_by_id.return_value = None
    await env.plugin.initialize()
    assert env.manager.get_func("spawn_agent") is env.plugin.spawn_tool
    assert not env.plugin.spawn_tool.active
    assert "expert" in env.plugin.spawn_tool.description
    req = ProviderRequest(conversation=env.conversation)
    await env.plugin.prepare_request(env.event, req)
    assert req.func_tool.get_tool("spawn_agent") is None
