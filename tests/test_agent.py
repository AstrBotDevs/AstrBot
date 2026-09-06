"""Import smoke tests for Agent dataclass."""

import pytest

from astrbot.core.agent.agent import Agent


class TestAgentImport:
    """Verify Agent dataclass can be imported and instantiated."""

    def test_class_importable(self):
        """Agent should be importable."""
        assert Agent is not None

    def test_instantiation_with_name_only(self):
        """Agent should be instantiatable with just a name."""
        agent = Agent(name="test_agent")
        assert isinstance(agent, Agent)
        assert agent.name == "test_agent"

    def test_instantiation_with_all_fields(self):
        """Agent should accept all optional fields."""
        agent = Agent(
            name="full_agent",
            instructions="You are a test agent.",
            tools=["tool1", "tool2"],
            # run_hooks and begin_dialogs can be None for this test
        )
        assert agent.name == "full_agent"
        assert agent.instructions == "You are a test agent."
        assert agent.tools == ["tool1", "tool2"]
        assert agent.run_hooks is None
        assert agent.begin_dialogs is None

    def test_is_dataclass(self):
        """Agent should be a dataclass."""
        from dataclasses import dataclass

        # Check it has the dataclass decorator by inspecting __dataclass_fields__
        assert hasattr(Agent, "__dataclass_fields__")

    def test_defaults(self):
        """Agent fields should have correct defaults."""
        agent = Agent(name="defaults_test")
        assert agent.instructions is None
        assert agent.tools is None
        assert agent.run_hooks is None
        assert agent.begin_dialogs is None
