"""Regression: skills_like schema mode must hand executable builtin tools to subagents."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.astr_agent_runtime.main_agent.subagent import begin_main_agent
from astrbot.core.astr_agent_runtime.tool_executor import FunctionToolExecutor
from astrbot.core.astr_agent_runtime.tools.computer_tools.shell import (
    LocalExecuteShellTool,
)
from astrbot.core.astr_agent_runtime.tools.web_search_tools import TavilyWebSearchTool


def _persona(tools):
    return {
        "name": "restricted",
        "prompt": "you are a restricted persona",
        "tools": tools,
        "skills": None,
        "begin_dialogs": [],
        "_begin_dialogs_processed": [],
    }


async def _spawn_worker(env, monkeypatch, *, plugin_tools, parent_tools, persona_tools):
    """Bind the parent snapshot, then spawn a worker and return its tool set."""
    wrapper = ContextWrapper(context=env.root)
    await begin_main_agent(
        wrapper,
        conversation_id=env.conversation.cid,
        tools=parent_tools,
    )
    env.root = wrapper.context
    env.root.plugin_tools = plugin_tools
    env.context.persona_manager.get_persona_v3_by_id = MagicMock(
        return_value=_persona(persona_tools)
    )
    selected = await env.save_agent("expert", persona_id="restricted")

    from astrbot.core.astr_agent_runtime import delegated_session

    create_runner = AsyncMock(wraps=delegated_session.create_native_runner)
    monkeypatch.setattr(delegated_session, "create_native_runner", create_runner)
    agent = await env.native.spawn_agent(
        env.root,
        [{"type": "plain", "text": "search something"}],
        config_id=selected.config_id,
    )
    await env.service.wait(env.root, [agent["agent_id"]], 5000, "all")
    return create_runner.call_args.args[2].func_tool, create_runner.call_args.args[4]


@pytest.mark.asyncio
async def test_worker_receives_executable_builtin_in_skills_like(
    environment, monkeypatch
):
    """The parent snapshot holds light copies; the worker must still get the real tool."""
    env = environment
    search = env.manager.get_builtin_tool(TavilyWebSearchTool)
    light = ToolSet([search]).get_light_tool_set()

    worker_tools, worker_context = await _spawn_worker(
        env,
        monkeypatch,
        plugin_tools=ToolSet(),
        parent_tools=light,
        persona_tools=["web_search_tavily"],
    )

    worker_search = worker_tools.get_tool("web_search_tavily")
    assert worker_search is not None
    assert type(worker_search) is TavilyWebSearchTool
    # A light copy has neither a handler nor a `call` override and cannot execute.
    assert not (
        worker_search.handler is None and type(worker_search).call is FunctionTool.call
    )

    # Exercise the real executor too. With no Tavily key configured this returns
    # a tool error rather than touching the network; a light copy raises instead.
    results = [
        result
        async for result in FunctionToolExecutor._execute_local(
            worker_search,
            ContextWrapper(context=worker_context),
            query="offline execution probe",
        )
    ]
    assert "Tavily API key is not configured" in results[0].content[0].text


@pytest.mark.asyncio
async def test_plugin_tool_precedence_is_preserved(environment, monkeypatch):
    """Resolving builtins must not replace plugin tools that share the snapshot."""
    env = environment
    search = env.manager.get_builtin_tool(TavilyWebSearchTool)
    plugin_tool = FunctionTool(name="plugin_tool_a", description="a", parameters={})
    env.manager.func_list.append(plugin_tool)

    worker_tools, _ = await _spawn_worker(
        env,
        monkeypatch,
        plugin_tools=ToolSet([plugin_tool]),
        parent_tools=ToolSet([plugin_tool, search]).get_light_tool_set(),
        persona_tools=None,
    )

    assert sorted(worker_tools.names()) == ["plugin_tool_a", "web_search_tavily"]
    # The plugin tool keeps coming from the authorized plugin contribution.
    assert worker_tools.get_tool("plugin_tool_a") is plugin_tool
    assert type(worker_tools.get_tool("web_search_tavily")) is TavilyWebSearchTool


@pytest.mark.asyncio
async def test_full_mode_local_shell_instance_is_preserved(environment, monkeypatch):
    """A real LocalExecuteShellTool must not be swapped for the generic builtin."""
    env = environment
    local_shell = LocalExecuteShellTool()

    worker_tools, _ = await _spawn_worker(
        env,
        monkeypatch,
        plugin_tools=ToolSet(),
        parent_tools=ToolSet([local_shell]),
        persona_tools=None,
    )

    worker_shell = worker_tools.get_tool("astrbot_execute_shell")
    assert type(worker_shell) is LocalExecuteShellTool


@pytest.mark.asyncio
async def test_same_named_plugin_tool_is_not_replaced(environment, monkeypatch):
    """An authorized tool that shadows a builtin name keeps its own instance."""
    env = environment
    search = env.manager.get_builtin_tool(TavilyWebSearchTool)
    shadow = FunctionTool(
        name="web_search_tavily", description="plugin shadow", parameters={}
    )
    env.manager.func_list.append(shadow)

    worker_tools, _ = await _spawn_worker(
        env,
        monkeypatch,
        plugin_tools=ToolSet([shadow]),
        parent_tools=ToolSet([search]).get_light_tool_set(),
        persona_tools=["web_search_tavily"],
    )

    assert worker_tools.get_tool("web_search_tavily") is shadow
