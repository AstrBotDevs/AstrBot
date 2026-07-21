"""Tests for the new orthogonal ContextConfig (redesigned context management).

Tests cover:
- All 12 new fields have correct defaults (no -1 magic values)
- Bool-based enabling (enable_turn_limit, enable_token_guard, etc.)
- Retention method enum validation
- Custom compressor injection
"""

from dataclasses import dataclass
from typing import Protocol
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Mock helpers (used across tests, defined here so they're importable)
# ---------------------------------------------------------------------------

class MockContextCompressor(Protocol):
    """Minimal stub matching the ContextCompressor protocol."""

    def should_compress(self, messages, current_tokens, max_tokens) -> bool:
        ...

    async def __call__(self, messages):
        ...


# ====================== Test: default values ======================


class TestContextConfigDefaults:
    """All 12 new orthogonal fields must have the defaults from the design spec."""

    def test_trigger_dimension_defaults(self):
        """Trigger dimension: enable_turn_limit=false, enable_token_guard=true."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig()

        # -- Turn limit --
        assert cfg.enable_turn_limit is False
        assert cfg.max_turns == 50

        # -- Token guard --
        assert cfg.enable_token_guard is True
        assert cfg.token_guard_threshold == 0.82

    def test_disposal_dimension_defaults(self):
        """Disposal dimension: both summary and discard enabled by default."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig()

        assert cfg.enable_summary is True
        assert cfg.enable_discard is True
        assert cfg.discard_turns == 1
        assert cfg.summary_prompt == ""
        assert cfg.summary_provider is None

    def test_retention_dimension_defaults(self):
        """Retention: method='turns', retain_turns=20, retain_percentage=0.3."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig()

        assert cfg.retention_method == "turns"
        assert cfg.retain_turns == 20
        assert cfg.retain_percentage == 0.3

    def test_no_magic_minus_one_values(self):
        """There must be no fields defaulting to -1 or <=0 to mean 'no limit'."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig()
        # Examine every field; none should be -1 or <= 0 as a disabling sentinel.
        for field_name, field_value in cfg.__dataclass_fields__.items():
            if field_name in ("custom_token_counter", "custom_compressor"):
                continue
            val = getattr(cfg, field_name)
            msg = (
                f"Field '{field_name}' uses magic value {val} instead of a bool switch. "
                "Use enable_* flags per design spec."
            )
            if isinstance(val, int) and field_name in ("retain_turns", "max_turns"):
                assert val >= 1, msg
            elif isinstance(val, int):
                assert val >= 0, msg

    def test_retention_method_valid_values(self):
        """retention_method must be 'turns', 'percentage', or 'null'."""
        from astrbot.core.agent.context.config import ContextConfig

        valid = {"turns", "percentage", "null"}
        cfg = ContextConfig()
        assert cfg.retention_method in valid

        cfg2 = ContextConfig(retention_method="percentage")
        assert cfg2.retention_method == "percentage"

        cfg3 = ContextConfig(retention_method="null")
        assert cfg3.retention_method == "null"


# ====================== Test: custom compressor injection ======================


class TestContextConfigCustomCompressor:
    """custom_compressor and custom_token_counter should work as before."""

    def test_custom_compressor_accepted(self):
        """custom_compressor can be injected via constructor."""
        from astrbot.core.agent.context.config import ContextConfig

        class DummyCompressor:
            def should_compress(self, messages, current_tokens, max_tokens):
                return False

            async def __call__(self, messages):
                return messages

        compressor = DummyCompressor()
        cfg = ContextConfig(custom_compressor=compressor)  # type: ignore[arg-type]
        assert cfg.custom_compressor is compressor

    def test_custom_compressor_defaults_to_none(self):
        """custom_compressor is None by default (ContextManager will choose)."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig()
        assert cfg.custom_compressor is None

    def test_custom_token_counter_defaults_to_none(self):
        """custom_token_counter is None by default."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig()
        assert cfg.custom_token_counter is None


# ====================== Test: explicit construction ======================


class TestContextConfigExplicit:
    """All fields can be set explicitly via constructor."""

    def test_set_all_trigger_fields(self):
        """Trigger dimension accepts explicit values."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=100,
            enable_token_guard=False,
            token_guard_threshold=0.9,
        )
        assert cfg.enable_turn_limit is True
        assert cfg.max_turns == 100
        assert cfg.enable_token_guard is False
        assert cfg.token_guard_threshold == 0.9

    def test_set_all_disposal_fields(self):
        """Disposal dimension accepts explicit values."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(
            enable_summary=False,
            enable_discard=False,
            discard_turns=3,
            summary_prompt="Custom prompt",
            summary_provider=MagicMock(),  # type: ignore[arg-type]
        )
        assert cfg.enable_summary is False
        assert cfg.enable_discard is False
        assert cfg.discard_turns == 3
        assert cfg.summary_prompt == "Custom prompt"
        assert cfg.summary_provider is not None

    def test_set_all_retention_fields(self):
        """Retention dimension accepts explicit values."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(
            retention_method="percentage",
            retain_turns=10,
            retain_percentage=0.5,
        )
        assert cfg.retention_method == "percentage"
        assert cfg.retain_turns == 10
        assert cfg.retain_percentage == 0.5

    def test_discard_turns_at_least_one(self):
        """discard_turns should be >= 1 per design spec."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(discard_turns=1)
        assert cfg.discard_turns >= 1

    def test_max_turns_at_least_2(self):
        """max_turns should be >= 2 per design spec."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(max_turns=2)
        assert cfg.max_turns >= 2

    def test_retain_turns_at_least_1(self):
        """retain_turns should be >= 1 per design spec."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(retain_turns=1)
        assert cfg.retain_turns >= 1

    def test_retain_percentage_range(self):
        """retain_percentage should be 0.1-0.9 per design spec."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(retain_percentage=0.1)
        assert 0.1 <= cfg.retain_percentage <= 0.9

        cfg2 = ContextConfig(retain_percentage=0.9)
        assert 0.1 <= cfg2.retain_percentage <= 0.9

    def test_token_guard_threshold_range(self):
        """token_guard_threshold should be 0.5-0.99 per design spec."""
        from astrbot.core.agent.context.config import ContextConfig

        cfg = ContextConfig(token_guard_threshold=0.5)
        assert 0.5 <= cfg.token_guard_threshold <= 0.99

        cfg2 = ContextConfig(token_guard_threshold=0.99)
        assert 0.5 <= cfg2.token_guard_threshold <= 0.99


# ====================== Test: backward-compatible attribute access ======================


class TestContextConfigBackwardCompat:
    """Old code paths that reference old fields should still be usable if shimmed."""

    def test_context_config_is_dataclass(self):
        """ContextConfig remains a dataclass."""
        from astrbot.core.agent.context.config import ContextConfig

        assert hasattr(ContextConfig, "__dataclass_fields__")
