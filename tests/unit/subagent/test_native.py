import asyncio
import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image as PILImage

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_runtime.subagents.store import AgentState
from astrbot.core.message.components import Image
from astrbot.core.provider.entities import LLMResponse


@pytest.mark.asyncio
async def test_native_runtime_owns_computer_initialization_and_shutdown(
    environment, monkeypatch
):
    from astrbot.core.astr_agent_runtime import runtime as native_runtime
    from astrbot.core.astr_agent_runtime.computer import computer_client

    env = environment
    order = []
    setup = MagicMock(side_effect=lambda: order.append("setup"))
    monkeypatch.setitem(
        sys.modules,
        "astrbot.core.astr_agent_runtime.computer.process_sandbox.windows_setup",
        SimpleNamespace(initialize_windows_sandbox=setup),
    )
    monkeypatch.setattr(native_runtime, "sys", SimpleNamespace(platform="win32"))
    env.context.astrbot_config_mgr = SimpleNamespace(
        confs={"default": {"provider_settings": {"computer_use_runtime": "local"}}}
    )
    env.native._sessions[("main", "test")] = SimpleNamespace(
        close=AsyncMock(side_effect=lambda: order.append("session"))
    )
    shutdown = AsyncMock(side_effect=lambda: order.append("computer"))
    monkeypatch.setattr(computer_client, "shutdown_local_booter", shutdown)
    await env.native.initialize()
    await env.native.close()
    assert order == ["setup", "session", "computer"]


@pytest.mark.asyncio
async def test_native_explicit_images_and_files_are_ordered_and_private(
    environment, tmp_path, monkeypatch
):
    env = environment
    PILImage.new("RGB", (4, 4), "blue").save(tmp_path / "chart.png")
    env.event.message_obj.message.append(Image(file="file:///parent-only.png"))
    env.wrapper.messages.append({"role": "user", "content": "Main secret"})
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.tools.message_tools.is_local_runtime",
        lambda _: True,
    )
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.tools.message_tools.workspace_root_for_context",
        AsyncMock(return_value=tmp_path),
    )
    messages = [
        {"type": "plain", "text": "Analyze"},
        {"type": "image", "path": "chart.png"},
        {"type": "plain", "text": "Consult"},
        {"type": "file", "path": "report  final.pdf"},
    ]
    result = await env.service.spawn(env.root, messages)
    agent = env.store.get(result["agent_id"], env.scope)
    messages[0]["text"] = "Changed"
    await env.service.wait(env.root, [agent.agent_id], 2000, "all")
    history = await (
        await env.native.open_session(
            env.scope.umo,
            session_id=agent.conversation_id,
            options={"profile": "subagent"},
        )
    ).history()
    content = next(
        message["content"] for message in history if message["role"] == "user"
    )
    assert [part["type"] for part in content] == ["text", "image_url", "text", "text"]
    assert content[0]["text"] == "Analyze"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[-1]["text"] == "[file] report  final.pdf"
    assert "parent-only" not in str(history)
    assert "Main secret" not in str(history)
    other = await env.service.spawn(
        env.root, [{"type": "plain", "text": "Independent"}]
    )
    await env.service.wait(env.root, [other["agent_id"]], 2000, "all")
    other_record = env.store.get(other["agent_id"], env.scope)
    assert other_record.conversation_id != agent.conversation_id
    assert "Analyze" not in str(
        await (
            await env.native.open_session(
                env.scope.umo,
                session_id=other_record.conversation_id,
                options={"profile": "subagent"},
            )
        ).history()
    )


@pytest.mark.asyncio
async def test_native_running_followup_is_text_and_does_not_create_another_prompt(
    environment,
):
    env = environment
    started, release = asyncio.Event(), asyncio.Event()

    class BlockingTool(FunctionTool):
        async def call(self, context):
            started.set()
            await release.wait()
            return "Finished tool"

    tool = BlockingTool(name="blocking", description="Block", parameters={})
    env.manager.func_list.append(tool)
    env.root.delegable_tools = ToolSet([tool])
    env.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["blocking"],
            tools_call_ids=["one"],
            tools_call_args=[{}],
        ),
        LLMResponse(role="assistant", completion_text="Done"),
    ]
    agent = await env.service.spawn(env.root, [{"type": "plain", "text": "Initial"}])
    await asyncio.wait_for(started.wait(), 2)
    await env.service.send(
        env.root,
        agent["agent_id"],
        [
            {"type": "plain", "text": "Compare"},
            {"type": "image", "path": "followup.png"},
        ],
    )
    record = env.store.get(agent["agent_id"], env.scope)
    assert len(record.turns) == 2
    task = env.service._workers[record.agent_id]
    release.set()
    await asyncio.wait_for(task, 3)
    assert len(record.turns) == 1
    assert record.current.state == AgentState.COMPLETED
    assert env.provider.text_chat.await_count == 2
    history = json.dumps(
        await (
            await env.native.open_session(
                env.scope.umo,
                session_id=record.conversation_id,
                options={"profile": "subagent"},
            )
        ).history()
    )
    assert "[image] followup.png" in history
    assert "Compare" in history


@pytest.mark.asyncio
async def test_native_followup_at_final_response_queues_against_same_history(
    environment,
):
    env = environment
    started, release = asyncio.Event(), asyncio.Event()
    calls = []

    async def respond(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            started.set()
            await release.wait()
        return LLMResponse(role="assistant", completion_text="Done")

    env.provider.text_chat.side_effect = respond
    agent = await env.service.spawn(env.root, [{"type": "plain", "text": "Initial"}])
    await asyncio.wait_for(started.wait(), 2)
    await env.service.send(
        env.root, agent["agent_id"], [{"type": "image", "path": "later.png"}]
    )
    task = env.service._workers[agent["agent_id"]]
    release.set()
    await asyncio.wait_for(task, 3)
    assert len(calls) == 2
    assert "Initial" in str(calls[1]["contexts"])
    assert "[image] later.png" in str(calls[1]["contexts"])
    record = env.store.get(agent["agent_id"], env.scope)
    assert len(record.turns) == 2
    assert all(turn.state == AgentState.COMPLETED for turn in record.turns)


@pytest.mark.asyncio
async def test_native_cancel_keeps_only_complete_steps_and_resumes_without_replaying_tool(
    environment,
):
    env = environment
    started = asyncio.Event()

    class BlockingTool(FunctionTool):
        async def call(self, context):
            started.set()
            await asyncio.Event().wait()

    tool = BlockingTool(name="blocking", description="Block", parameters={})
    env.manager.func_list.append(tool)
    env.root.delegable_tools = ToolSet([tool])
    env.provider.text_chat.side_effect = [
        LLMResponse(
            role="assistant",
            tools_call_name=["blocking"],
            tools_call_ids=["in-flight"],
            tools_call_args=[{}],
        ),
        LLMResponse(role="assistant", completion_text="Resumed"),
    ]
    agent = await env.service.spawn(env.root, [{"type": "plain", "text": "Initial"}])
    await asyncio.wait_for(started.wait(), 2)
    await env.service.cancel(env.root, agent["agent_id"])
    record = env.store.get(agent["agent_id"], env.scope)
    assert "in-flight" not in str(
        await (
            await env.native.open_session(
                env.scope.umo,
                session_id=record.conversation_id,
                options={"profile": "subagent"},
            )
        ).history()
    )
    await env.service.send(
        env.root, record.agent_id, [{"type": "plain", "text": "Continue"}]
    )
    result = await env.service.wait(env.root, [record.agent_id], 2000, "all")
    assert result["agents"][0]["result"] == "Resumed"
    assert "in-flight" not in str(
        env.provider.text_chat.call_args_list[-1].kwargs["contexts"]
    )


@pytest.mark.asyncio
async def test_native_tool_selection_preserves_guards_and_scope_restrictions(
    environment, monkeypatch
):
    from types import SimpleNamespace

    from astrbot.core.provider.func_tool_manager import _PermissionGuardedTool

    env = environment
    tools = [
        FunctionTool(name=name, description=name, parameters={})
        for name in ("allowed", "blocked", "inactive")
    ]
    tools[1].handler_module_path = "plugins.blocked"
    tools[2].active = False
    env.manager.func_list.extend(tools)
    env.event.plugins_name = []
    monkeypatch.setattr(
        "astrbot.core.astr_agent_runtime.delegated_session.star_map",
        {"plugins.blocked": SimpleNamespace(name="blocked", reserved=False)},
    )
    selected = await env.save_agent("expert", tools=None)
    env.root.delegable_tools = ToolSet(tools)
    from astrbot.core.astr_agent_runtime import delegated_session

    create_runner = AsyncMock(wraps=delegated_session.create_native_runner)
    monkeypatch.setattr(delegated_session, "create_native_runner", create_runner)
    agent = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Task"}], config_id=selected.config_id
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    tools = create_runner.call_args.args[2].func_tool
    assert tools.names() == ["allowed"]
    assert isinstance(tools.get_tool("allowed"), _PermissionGuardedTool)


@pytest.mark.asyncio
@pytest.mark.parametrize("selection", [None, ["hidden"]])
async def test_expert_and_parent_tools_cannot_expand_core_plugin_contributions(
    environment, selection, monkeypatch
):
    env = environment
    hidden = FunctionTool(name="hidden", description="Hidden", parameters={})
    env.manager.func_list.append(hidden)
    env.root.delegable_tools = ToolSet([hidden])
    env.root.plugin_tools = ToolSet()
    selected = await env.save_agent("expert", tools=selection)
    from astrbot.core.astr_agent_runtime import delegated_session

    create_runner = AsyncMock(wraps=delegated_session.create_native_runner)
    monkeypatch.setattr(delegated_session, "create_native_runner", create_runner)
    agent = await env.native.spawn_agent(
        env.root, [{"type": "plain", "text": "Task"}], config_id=selected.config_id
    )
    await env.service.wait(env.root, [agent["agent_id"]], 2000, "all")
    assert create_runner.call_args.args[2].func_tool is None
