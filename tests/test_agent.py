"""Agent specifications retain explicit capabilities and independent defaults."""

from dataclasses import replace

import pytest

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.agent.tool import FunctionTool


def test_agent_name_is_required():
    with pytest.raises(TypeError, match="name"):
        Agent()


def test_minimal_agent_has_no_implicit_tools_or_dialogues():
    first, second = Agent(name="first"), Agent(name="second")
    assert (first.instructions, first.tools, first.run_hooks, first.begin_dialogs) == (
        None,
        None,
        None,
        None,
    )
    first.tools = ["explicit"]
    assert second.tools is None


def test_agent_keeps_explicit_hook_tools_and_initial_dialogues():
    tool = FunctionTool(name="probe", description="Probe")
    hooks = BaseAgentRunHooks()
    dialogues = [{"role": "user", "content": "start"}]
    agent = Agent(
        name="configured",
        instructions="Follow instructions",
        tools=["named", tool],
        run_hooks=hooks,
        begin_dialogs=dialogues,
    )
    assert agent.tools == ["named", tool] and agent.tools[1] is tool
    assert agent.run_hooks is hooks
    assert agent.begin_dialogs == dialogues
    changed = replace(agent, name="renamed", instructions="New instructions")
    assert agent.name == "configured" and agent.instructions == "Follow instructions"
    assert changed.name == "renamed" and changed.instructions == "New instructions"
