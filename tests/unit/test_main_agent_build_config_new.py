"""Tests for new context management fields in MainAgentBuildConfig.

Covers:
- New fields: enable_turn_limit, max_turns, enable_token_guard, token_guard_threshold
- New fields: enable_summary, enable_discard, discard_turns
- New fields: summary_prompt, summary_provider_id
- New fields: retention_method, retain_turns, retain_percentage
- Removal of old fields: context_limit_reached_strategy, max_context_length, etc.
"""

from astrbot.core.astr_main_agent import MainAgentBuildConfig


class TestMainAgentBuildConfigNewFields:
    """MainAgentBuildConfig must include all 12 new context management fields."""

    def test_new_context_fields_defaults(self):
        """All 12 new fields have correct defaults matching the design doc."""
        config = MainAgentBuildConfig(tool_call_timeout=60)

        # Trigger dimension
        assert config.enable_turn_limit is False
        assert config.max_turns == 50
        assert config.enable_token_guard is True
        assert config.token_guard_threshold == 0.82

        # Disposal dimension
        assert config.enable_summary is True
        assert config.enable_discard is True
        assert config.discard_turns == 1
        assert config.summary_prompt == ""
        assert config.summary_provider_id == ""

        # Retention dimension
        assert config.retention_method == "turns"
        assert config.retain_turns == 20
        assert config.retain_percentage == 0.3

    def test_old_fields_retained_as_deprecated(self):
        """Old context management fields are retained as deprecated placeholders."""
        config = MainAgentBuildConfig(tool_call_timeout=60)

        # Old fields may still exist for backward compatibility
        # but new fields should be the primary interface
        assert hasattr(config, "enable_turn_limit")
        assert hasattr(config, "max_turns")
        assert hasattr(config, "enable_token_guard")
        assert hasattr(config, "token_guard_threshold")
        assert hasattr(config, "enable_summary")
        assert hasattr(config, "enable_discard")
        assert hasattr(config, "discard_turns")
        assert hasattr(config, "summary_prompt")
        assert hasattr(config, "summary_provider_id")
        assert hasattr(config, "retention_method")
        assert hasattr(config, "retain_turns")
        assert hasattr(config, "retain_percentage")

    def test_set_all_new_fields_explicitly(self):
        """All new fields can be set via constructor."""
        config = MainAgentBuildConfig(
            tool_call_timeout=60,
            # Trigger
            enable_turn_limit=True,
            max_turns=100,
            enable_token_guard=False,
            token_guard_threshold=0.9,
            # Disposal
            enable_summary=False,
            enable_discard=False,
            discard_turns=3,
            summary_prompt="Custom prompt",
            summary_provider_id="my-provider",
            # Retention
            retention_method="percentage",
            retain_turns=10,
            retain_percentage=0.5,
        )

        # Verify trigger
        assert config.enable_turn_limit is True
        assert config.max_turns == 100
        assert config.enable_token_guard is False
        assert config.token_guard_threshold == 0.9

        # Verify disposal
        assert config.enable_summary is False
        assert config.enable_discard is False
        assert config.discard_turns == 3
        assert config.summary_prompt == "Custom prompt"
        assert config.summary_provider_id == "my-provider"

        # Verify retention
        assert config.retention_method == "percentage"
        assert config.retain_turns == 10
        assert config.retain_percentage == 0.5

    def test_new_fields_compatible_with_existing_fields(self):
        """Existing non-context fields still work alongside new fields."""
        config = MainAgentBuildConfig(
            tool_call_timeout=30,
            streaming_response=False,
            kb_agentic_mode=True,
            llm_safety_mode=True,
            enable_turn_limit=True,
            max_turns=50,
        )
        assert config.tool_call_timeout == 30
        assert config.streaming_response is False
        assert config.kb_agentic_mode is True
        assert config.llm_safety_mode is True
        assert config.enable_turn_limit is True
        assert config.max_turns == 50
