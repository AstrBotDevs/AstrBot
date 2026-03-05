"""Tests for register_agent decorator runtime behavior."""

import builtins

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.star.register import star_handler


class _DummyHandoffTool:
    def __init__(self, agent):
        self.agent = agent
        self.handler = None


def test_register_agent_does_not_import_astr_agent_context_at_runtime(
    monkeypatch,
):
    """register_agent should not require runtime import of AstrAgentContext."""

    monkeypatch.setattr(star_handler, "HandoffTool", _DummyHandoffTool)

    original_import = builtins.__import__

    def guarded_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        if name == "astrbot.core.astr_agent_context":
            raise RuntimeError("unexpected runtime import of AstrAgentContext")
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    before_count = len(star_handler.llm_tools.func_list)

    async def test_agent(_event, _context):
        return "ok"

    registering_agent = star_handler.register_agent(
        name="test_agent",
        instruction="You are a test helper.",
    )(test_agent)

    try:
        assert isinstance(registering_agent, star_handler.RegisteringAgent)
        assert registering_agent._agent.name == "test_agent"
        assert isinstance(registering_agent._agent.run_hooks, BaseAgentRunHooks)
        assert len(star_handler.llm_tools.func_list) == before_count + 1
    finally:
        if len(star_handler.llm_tools.func_list) > before_count:
            star_handler.llm_tools.func_list.pop()
