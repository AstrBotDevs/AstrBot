"""Import smoke tests for CozeAgentRunner."""

import pytest

from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner


class TestCozeAgentRunnerImport:
    """Verify CozeAgentRunner can be imported and instantiated."""

    def test_class_importable(self):
        """CozeAgentRunner should be importable."""
        assert CozeAgentRunner is not None

    def test_instantiation(self):
        """CozeAgentRunner should be instantiatable without arguments."""
        runner = CozeAgentRunner()
        assert isinstance(runner, CozeAgentRunner)

    def test_inherits_base_agent_runner(self):
        """CozeAgentRunner should inherit from BaseAgentRunner."""
        from astrbot.core.agent.runners.base import BaseAgentRunner

        assert issubclass(CozeAgentRunner, BaseAgentRunner)

    def test_default_state_is_idle(self):
        """A freshly instantiated runner should have IDLE state."""
        from astrbot.core.agent.runners.base import AgentState

        runner = CozeAgentRunner()
        assert runner._state == AgentState.IDLE

    def test_done_returns_false_when_idle(self):
        """done() should return False when in IDLE state."""
        runner = CozeAgentRunner()
        assert runner.done() is False

    def test_get_final_llm_resp_returns_none_when_uninitialized(self):
        """get_final_llm_resp() should return None before reset()."""
        runner = CozeAgentRunner()
        runner.final_llm_resp = None
        assert runner.get_final_llm_resp() is None
