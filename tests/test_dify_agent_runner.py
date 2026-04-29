"""Import smoke tests for DifyAgentRunner."""

import pytest

from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner


class TestDifyAgentRunnerImport:
    """Verify DifyAgentRunner can be imported and instantiated."""

    def test_class_importable(self):
        """DifyAgentRunner should be importable."""
        assert DifyAgentRunner is not None

    def test_instantiation(self):
        """DifyAgentRunner should be instantiatable without arguments."""
        runner = DifyAgentRunner()
        assert isinstance(runner, DifyAgentRunner)

    def test_inherits_base_agent_runner(self):
        """DifyAgentRunner should inherit from BaseAgentRunner."""
        from astrbot.core.agent.runners.base import BaseAgentRunner

        assert issubclass(DifyAgentRunner, BaseAgentRunner)

    def test_default_state_is_idle(self):
        """A freshly instantiated runner should have IDLE state."""
        from astrbot.core.agent.runners.base import AgentState

        runner = DifyAgentRunner()
        assert runner._state == AgentState.IDLE

    def test_done_returns_false_when_idle(self):
        """done() should return False when in IDLE state."""
        runner = DifyAgentRunner()
        assert runner.done() is False

    def test_get_final_llm_resp_returns_none_when_uninitialized(self):
        """get_final_llm_resp() should return None before reset()."""
        runner = DifyAgentRunner()
        runner.final_llm_resp = None
        assert runner.get_final_llm_resp() is None
