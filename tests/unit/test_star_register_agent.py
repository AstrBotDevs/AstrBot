"""Tests for register_agent decorator runtime behavior."""

import builtins

import pytest

from astrbot.core.agent.hooks import BaseAgentRunHooks
from astrbot.core.star.register import star_handler


class _DummyHandoffTool:
    """Mock HandoffTool for testing without side effects."""

    def __init__(self, agent):
        self.agent = agent
        self.handler = None


@pytest.fixture
def llm_tools_cleanup():
    """Fixture to restore llm_tools.func_list after each test."""
    original_list = star_handler.llm_tools.func_list.copy()
    yield
    star_handler.llm_tools.func_list[:] = original_list


# Module names that should not be imported at runtime by register_agent
_FORBIDDEN_IMPORT_PATTERNS = (
    "astrbot.core.astr_agent_context",
    "astr_agent_context",
)


def test_register_agent_does_not_import_astr_agent_context_at_runtime(
    monkeypatch,
    llm_tools_cleanup,
):
    """register_agent should not require runtime import of AstrAgentContext."""

    monkeypatch.setattr(star_handler, "HandoffTool", _DummyHandoffTool)

    original_import = builtins.__import__

    def guarded_import(name, globals_=None, locals_=None, fromlist=(), level=0):
        # Check against multiple patterns to be robust to refactors
        for pattern in _FORBIDDEN_IMPORT_PATTERNS:
            if pattern in name:
                raise RuntimeError(
                    f"unexpected runtime import of AstrAgentContext: {name}"
                )
        return original_import(name, globals_, locals_, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    before_count = len(star_handler.llm_tools.func_list)

    async def test_agent(_event, _context):
        return "ok"

    registering_agent = star_handler.register_agent(
        name="test_agent",
        instruction="You are a test helper.",
    )(test_agent)

    assert isinstance(registering_agent, star_handler.RegisteringAgent)
    assert registering_agent._agent.name == "test_agent"
    assert isinstance(registering_agent._agent.run_hooks, BaseAgentRunHooks)
    assert len(star_handler.llm_tools.func_list) == before_count + 1

    # Verify that the decorated coroutine is wired as the handoff handler
    last_tool = star_handler.llm_tools.func_list[-1]
    assert isinstance(last_tool, _DummyHandoffTool)
    assert last_tool.handler is test_agent
