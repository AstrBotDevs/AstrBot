"""Import smoke tests for DashscopeAgentRunner."""

import pytest

from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)


class TestDashscopeAgentRunnerImport:
    """Verify DashscopeAgentRunner can be imported and instantiated."""

    def test_class_importable(self):
        """DashscopeAgentRunner should be importable."""
        assert DashscopeAgentRunner is not None

    def test_instantiation(self):
        """DashscopeAgentRunner should be instantiatable without arguments."""
        runner = DashscopeAgentRunner()
        assert isinstance(runner, DashscopeAgentRunner)

    def test_inherits_base_agent_runner(self):
        """DashscopeAgentRunner should inherit from BaseAgentRunner."""
        from astrbot.core.agent.runners.base import BaseAgentRunner

        assert issubclass(DashscopeAgentRunner, BaseAgentRunner)

    def test_default_state_is_idle(self):
        """A freshly instantiated runner should have IDLE state."""
        from astrbot.core.agent.runners.base import AgentState

        runner = DashscopeAgentRunner()
        assert runner._state == AgentState.IDLE

    def test_done_returns_false_when_idle(self):
        """done() should return False when in IDLE state."""
        runner = DashscopeAgentRunner()
        assert runner.done() is False

    def test_get_final_llm_resp_returns_none_when_uninitialized(self):
        """get_final_llm_resp() should return None before reset()."""
        runner = DashscopeAgentRunner()
        runner.final_llm_resp = None
        assert runner.get_final_llm_resp() is None

    def test_has_rag_options_returns_false_with_empty_config(self):
        """has_rag_options() should return False when no RAG options are set."""
        runner = DashscopeAgentRunner()
        runner.rag_options = {}
        assert runner.has_rag_options() is False
