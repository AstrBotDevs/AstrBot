import asyncio
import copy
import json
from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.input import FileInput, ImageInput, PlainInput
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.runtime import AgentPermissions, AgentRole
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_runtime.context import AstrAgentContext
from astrbot.core.astr_agent_runtime.main_agent import subagent
from astrbot.core.astr_agent_runtime.subagents.store import AgentState
from astrbot.core.astr_agent_runtime.tools.subagent import (
    CancelAgentTool,
    ListAgentsTool,
    SendAgentMessageTool,
    SpawnAgentTool,
    WaitAgentTool,
)


@pytest.mark.asyncio
async def test_foreign_runner_exchanges_structured_input_without_native_loop(
    environment,
):
    env = environment
    env.context.tool_loop_agent = AsyncMock(
        side_effect=AssertionError("Native execution must not be used")
    )
    messages = [
        {"type": "plain", "text": "Research"},
        {"type": "image", "url": "https://example.com/a.png"},
    ]
    selected = await env.save_agent(
        "researcher", runtime="memory", config={"model": "external"}
    )
    env.memory.open_session = AsyncMock(wraps=env.memory.open_session)
    reply = json.loads(
        await SpawnAgentTool().call(
            env.wrapper, messages, config_id=selected.config_id, name="researcher"
        )
    )
    assert env.memory.open_session.call_args_list[0].kwargs["options"]["config"] == {
        "model": "external"
    }
    agent_id = reply["agent_id"]
    messages[0]["text"] = "Changed"
    result = await env.service.wait(env.root, [agent_id], 2000, "all")
    agent = env.store.get(agent_id, env.scope)
    assert agent.runtime == "memory"
    assert agent.conversation_id.startswith("remote-")
    assert env.memory.sessions[agent.conversation_id][0][0]["text"] == "Research"
    assert isinstance(env.memory.inputs[0].content[0], PlainInput)
    assert isinstance(env.memory.inputs[0].content[1], ImageInput)
    assert result["agents"][0]["state"] == "completed"
    assert "parent_agent_id" not in result["agents"][0]
    await SendAgentMessageTool().call(
        env.wrapper, agent_id, [{"type": "file", "path": "report.pdf"}]
    )
    await env.service.wait(env.root, [agent_id], 2000, "all")
    assert len(env.memory.sessions[agent.conversation_id]) == 2
    assert env.memory.sessions[agent.conversation_id][1] == [
        {"type": "file", "path": "report.pdf"}
    ]
    assert isinstance(env.memory.inputs[1].content[0], FileInput)
    listing = json.loads(await ListAgentsTool().call(env.wrapper))["agents"]
    assert listing[0]["agent_id"] == agent_id
    assert listing[0]["conversation_id"] == agent.conversation_id
    env.context.tool_loop_agent.assert_not_called()


@pytest.mark.asyncio
async def test_same_agent_inputs_are_serial_and_wait_timeout_does_not_cancel(
    environment,
):
    env = environment
    env.memory.release = asyncio.Event()
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "First"}], runtime="memory"
    )
    conversation_id, _ = await asyncio.wait_for(env.memory.started.get(), 1)
    await env.service.send(
        env.root, agent["agent_id"], [{"type": "plain", "text": "Second"}]
    )
    waiting = json.loads(
        await WaitAgentTool().call(env.wrapper, [agent["agent_id"]], timeout_ms=0)
    )
    assert waiting["timed_out"]
    assert waiting["agents"][0]["state"] == "running"
    assert len(env.memory.sessions[conversation_id]) == 1
    task = env.service._workers[agent["agent_id"]]
    env.memory.release.set()
    await asyncio.wait_for(task, 2)
    assert [batch[0]["text"] for batch in env.memory.sessions[conversation_id]] == [
        "First",
        "Second",
    ]
    assert len(env.store.get(agent["agent_id"], env.scope).turns) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        {"umo": "another:FriendMessage:alice"},
        {"conversation_id": "other"},
    ],
)
async def test_agent_scope_prevents_cross_conversation_access(environment, changed):
    env = environment
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Private"}], runtime="memory"
    )
    other = replace(env.root, subagent_scope=replace(env.scope, **changed))
    assert env.service.list(other) == []
    with pytest.raises(ValueError, match="Unknown subagent"):
        await env.service.send(
            other, agent["agent_id"], [{"type": "plain", "text": "Steal"}]
        )
    with pytest.raises(ValueError, match="Unknown subagent"):
        await env.service.result(other, agent["agent_id"])
    with pytest.raises(ValueError, match="Unknown subagent"):
        await env.service.cancel(other, agent["agent_id"])


@pytest.mark.asyncio
@pytest.mark.parametrize("environment", ["test:GroupMessage:room"], indirect=True)
async def test_group_members_share_agents_but_keep_each_inputs_caller(environment):
    env = environment
    env.event.role = "admin"
    env.root.permissions = AgentPermissions(AgentRole.ADMIN)
    env.root.plugin_tools = ToolSet(
        [FunctionTool(name="plugin_tool", description="Plugin", parameters={})]
    )
    env.root.plugin_skills = []
    env.memory.release = asyncio.Event()
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "First"}], runtime="memory"
    )
    await asyncio.wait_for(env.memory.started.get(), 1)
    wrappers = []
    for sender, role in [("bob", AgentRole.MEMBER), ("carol", AgentRole.ADMIN)]:
        event = copy.copy(env.event)
        event.message_obj = copy.deepcopy(env.event.message_obj)
        event.message_obj.sender.user_id = sender
        event.role = role.value
        wrapper = ContextWrapper(
            context=AstrAgentContext(
                context=env.context,
                event=event,
                permissions=AgentPermissions(role),
                plugin_tools=env.root.plugin_tools,
                plugin_skills=env.root.plugin_skills,
                agent_session=env.root.agent_session,
                _runtime=env.native,
            )
        )
        await subagent.begin_main_agent(
            wrapper, conversation_id=env.conversation.cid, tools=ToolSet()
        )
        assert wrapper.context.subagent_scope == env.scope
        listing = json.loads(await ListAgentsTool().call(wrapper))["agents"]
        assert [item["agent_id"] for item in listing] == [agent["agent_id"]]
        await SendAgentMessageTool().call(
            wrapper, agent["agent_id"], [{"type": "plain", "text": sender}]
        )
        wrappers.append(wrapper)

    # A later read must not replace the caller of already queued input.
    env.service.list(env.root)
    env.memory.release.set()
    await asyncio.wait_for(env.service._workers[agent["agent_id"]], 2)
    assert [
        (input.event.get_sender_id(), input.permissions.role)
        for input in env.memory.inputs
    ] == [
        ("alice", AgentRole.ADMIN),
        ("bob", AgentRole.MEMBER),
        ("carol", AgentRole.ADMIN),
    ]
    assert all(
        input.plugin_tools.names() == ["plugin_tool"] for input in env.memory.inputs
    )
    assert all(input.plugin_skills == [] for input in env.memory.inputs)
    assert (await env.service.result(wrappers[0].context, agent["agent_id"]))[
        "result"
    ] == "carol"
    await CancelAgentTool().call(wrappers[0], agent["agent_id"])
    assert not env.service._task_callers


@pytest.mark.asyncio
@pytest.mark.parametrize("started", [False, True])
async def test_cancel_before_or_during_execution_keeps_conversation_reusable(
    environment, started
):
    env = environment
    env.memory.release = asyncio.Event()
    reply = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Initial"}], runtime="memory"
    )
    if started:
        await asyncio.wait_for(env.memory.started.get(), 1)
        await env.service.send(
            env.root, reply["agent_id"], [{"type": "plain", "text": "Queued"}]
        )
    await CancelAgentTool().call(env.wrapper, reply["agent_id"])
    record = env.store.get(reply["agent_id"], env.scope)
    assert all(turn.state == AgentState.CANCELLED for turn in record.turns)
    env.memory.release.set()
    await env.service.send(
        env.root, reply["agent_id"], [{"type": "plain", "text": "Resume"}]
    )
    result = await env.service.wait(env.root, [reply["agent_id"]], 2000, "all")
    assert result["agents"][0]["result"] == "Resume"
    assert len(record.turns) == (3 if started else 2)


@pytest.mark.asyncio
async def test_queue_time_is_included_in_timeout_and_capacity_is_released(environment):
    env = environment
    env.config.update(max_concurrent_agents=1, task_timeout=1)
    env.memory.release = asyncio.Event()
    first = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Busy"}], runtime="memory"
    )
    await asyncio.wait_for(env.memory.started.get(), 1)
    second = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Waiting"}], runtime="memory"
    )
    result = await env.service.wait(
        env.root, [first["agent_id"], second["agent_id"]], 2500, "all"
    )
    assert not result["timed_out"]
    assert {item["state"] for item in result["agents"]} == {"timed_out"}
    assert env.service._running == {}


@pytest.mark.asyncio
async def test_failure_is_queryable_and_does_not_prevent_later_input(environment):
    env = environment
    env.memory.failure = ValueError("Remote unavailable")
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Task"}], runtime="memory"
    )
    failed = await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert failed["agents"][0]["error"] == "Remote unavailable"
    env.memory.failure = None
    await env.service.send(
        env.root, agent["agent_id"], [{"type": "plain", "text": "Retry"}]
    )
    result = await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert result["agents"][0]["result"] == "Retry"


@pytest.mark.asyncio
async def test_rejects_nested_delegation_and_failed_initial_persistence(environment):
    env = environment
    worker = replace(env.root, is_subagent=True)
    with pytest.raises(ValueError, match="cannot create"):
        await env.service.spawn(worker, [{"type": "plain", "text": "Nested"}])
    env.db.insert_preference_or_update = AsyncMock(side_effect=OSError("Disk full"))
    with pytest.raises(OSError):
        await env.service.spawn(
            env.root, [{"type": "plain", "text": "Task"}], runtime="memory"
        )
    assert not env.store.agents
    assert not env.service._workers


@pytest.mark.asyncio
async def test_runner_cannot_reuse_an_existing_agents_conversation(environment):
    env = environment
    agent = await env.service.spawn(
        env.root, [{"type": "plain", "text": "First"}], runtime="memory"
    )
    env.memory.open_session = AsyncMock(
        return_value=env.memory.handles[agent["conversation_id"]]
    )
    with pytest.raises(ValueError, match="already owned"):
        await env.service.spawn(
            env.root, [{"type": "plain", "text": "Second"}], runtime="memory"
        )
    assert len(env.store.agents) == 1


@pytest.mark.asyncio
async def test_shutdown_during_session_creation_never_starts_work(environment):
    env = environment
    started, release = asyncio.Event(), asyncio.Event()

    original_open = env.memory.open_session

    async def create(umo, **kwargs):
        started.set()
        await release.wait()
        return await original_open(umo, **kwargs)

    env.memory.open_session = create
    opening = asyncio.create_task(
        env.service.spawn(
            env.root, [{"type": "plain", "text": "Task"}], runtime="memory"
        )
    )
    await started.wait()
    await env.service.close()
    release.set()
    with pytest.raises(ValueError, match="shutting down"):
        await opening
    assert not env.store.agents
    assert not env.service._workers
    assert all(handle._closed for handle in env.memory.handles.values())
