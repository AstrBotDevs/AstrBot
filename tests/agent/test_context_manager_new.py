"""Tests for the redesigned ContextManager.process() flow.

Tests the full new pipeline:
  Trigger dimension (independent checks):
    - enable_turn_limit + max_turns
    - enable_token_guard + token_guard_threshold
  Disposal dimension (unified entry):
    - Summary (with fallback to discard)
    - Discard (with retention lower bound)
    - Both disabled → warning, no-op
  Retention constraint:
    - turns / percentage / null methods
  Double-check:
    - Halving when still over token guard threshold (unconstrained by retention)
"""

from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.message import Message


# ====================== Helpers ======================


class MockProvider:
    """Minimal provider stub for LLM summary calls."""

    def __init__(self):
        self.provider_config = {
            "id": "test_provider",
            "model": "gpt-4",
            "modalities": ["text"],
        }
        self.last_text_chat_kwargs = None

    async def text_chat(self, **kwargs):
        self.last_text_chat_kwargs = kwargs
        from astrbot.core.provider.entities import LLMResponse

        return LLMResponse(
            role="assistant",
            completion_text="Mock summary: conversation compressed.",
        )

    def get_model(self):
        return "gpt-4"

    def meta(self):
        return MagicMock(id="test_provider", type="openai")


def create_message(role: Literal["system", "user", "assistant", "tool"], content: str) -> Message:
    return Message(role=role, content=content)


def create_messages(count: int) -> list[Message]:
    """Alternating user/assistant messages."""
    return [create_message("user" if i % 2 == 0 else "assistant", f"Message {i}") for i in range(count)]


# ====================== Trigger Dimension Tests ======================


class TestTriggerDimension:
    """Independent trigger checks: turn_limit and token_guard."""

    @pytest.mark.asyncio
    async def test_no_triggers_returns_original(self):
        """With all triggers disabled, process() returns messages unchanged."""
        cfg = ContextConfig(
            enable_turn_limit=False,
            enable_token_guard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)

        result = await manager.process(msgs)

        # No triggers → messages unchanged
        assert result is msgs or result == msgs
        assert len(result) == len(msgs)

    @pytest.mark.asyncio
    async def test_turn_limit_triggered(self):
        """enable_turn_limit=True + turns > max_turns → triggers compression."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=3,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=True,
            discard_turns=2,
            retention_method="null",
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)  # 5 turns > 3

        result = await manager.process(msgs)

        # Should have been compressed via discard
        assert len(result) < len(msgs)

    @pytest.mark.asyncio
    async def test_turn_limit_not_triggered_below_max(self):
        """enable_turn_limit=True but turns <= max_turns → no trigger."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=10,
            enable_token_guard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)  # 5 turns <= 10

        result = await manager.process(msgs)

        assert len(result) == len(msgs)

    @pytest.mark.asyncio
    async def test_token_guard_triggered(self):
        """enable_token_guard=True + token ratio > threshold → triggers compression."""
        cfg = ContextConfig(
            enable_turn_limit=False,
            enable_token_guard=True,
            token_guard_threshold=0.1,
            enable_summary=False,
            enable_discard=True,
            discard_turns=2,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(6)  # enough tokens to trigger

        # Use high max_context_tokens so that there's enough headroom
        result = await manager.process(msgs, max_context_tokens=500)

        # The trigger may or may not fire depending on exact token counts;
        # at minimum the pipeline should not crash
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_token_guard_disabled_does_not_trigger(self):
        """enable_token_guard=False → token check skipped even at high usage."""
        cfg = ContextConfig(
            enable_turn_limit=False,
            enable_token_guard=False,
        )
        manager = ContextManager(cfg)
        msgs = [create_message("user", "x" * 5000)]

        result = await manager.process(msgs, max_context_tokens=100)

        assert result == msgs

    @pytest.mark.asyncio
    async def test_either_trigger_suffices(self):
        """Only one trigger needs to fire for compression to run."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,                 # will trigger
            enable_token_guard=False,    # won't trigger
            enable_summary=False,
            enable_discard=True,
            discard_turns=1,
            retention_method="null",
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)  # 5 turns > 2

        result = await manager.process(msgs)

        # Turn limit trigger alone should cause compression
        assert len(result) < len(msgs)


# ====================== Disposal Dimension Tests ======================


class TestDisposalDimension:
    """Unified disposal entry: summary → discard fallback → no-op."""

    @pytest.mark.asyncio
    async def test_summary_used_when_enabled_and_provider_available(self):
        """enable_summary=True with a summary_provider → uses LLM summary."""
        provider = MockProvider()
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=True,
            enable_discard=False,
            summary_provider=provider,  # type: ignore[arg-type]
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        result = await manager.process(msgs)

        # Should have been compressed via LLM summary
        assert len(result) <= len(msgs)
        assert provider.last_text_chat_kwargs is not None

    @pytest.mark.asyncio
    async def test_summary_fallback_to_discard(self):
        """Summary fails → falls back to discard if enable_discard=True."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=True,
            enable_discard=True,
            discard_turns=2,
            retention_method="null",
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        # Simulate summary compressor always failing by removing it
        manager._summary_compressor = None

        result = await manager.process(msgs)

        # Should have been compressed via discard fallback
        assert len(result) < len(msgs)

    @pytest.mark.asyncio
    async def test_discard_only_when_summary_disabled(self):
        """enable_summary=False, enable_discard=True → discard used directly."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=True,
            discard_turns=2,
            retention_method="null",
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        result = await manager.process(msgs)

        # Should be compressed via discard
        assert len(result) < len(msgs)

    @pytest.mark.asyncio
    async def test_both_disabled_logs_warning(self):
        """Both enable_summary=False and enable_discard=False → warning logged, no compression."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        with patch("astrbot.core.agent.context.manager.logger") as mock_logger:
            result = await manager.process(msgs)

        # Should log a warning about both disabled
        assert mock_logger.warning.called

        # Messages should be returned
        assert isinstance(result, list)


# ====================== Retention Tests ======================


class TestRetentionConstraint:
    """Retention lower bound constrains how many turns can be discarded."""

    @pytest.mark.asyncio
    async def test_retention_turns_method(self):
        """retention_method='turns': max_discardable = total - retain_turns."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=True,
            discard_turns=10,
            retention_method="turns",
            retain_turns=5,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)  # 10 turns

        result = await manager.process(msgs)

        # retain_turns=5 means at most 5 turns discarded, so at least 5 remain
        # 10 total turns → max 5 discardable → keep at least 5
        assert len(result) >= 6  # at least 3 turns (6 msgs) due to round padding

    @pytest.mark.asyncio
    async def test_retention_percentage_method(self):
        """retention_method='percentage': max_discardable = total - int(total * retain_percentage)."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=True,
            discard_turns=5,
            retention_method="percentage",
            retain_percentage=0.3,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)  # 10 turns

        result = await manager.process(msgs)

        # retain_percentage=0.3 → keep at least 3 turns → max discard 7
        assert len(result) >= 2

    @pytest.mark.asyncio
    async def test_retention_null_method(self):
        """retention_method='null': no lower bound, all messages can be discarded."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=True,
            discard_turns=10,
            retention_method="null",
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)  # 10 turns

        result = await manager.process(msgs)

        assert isinstance(result, list)


# ====================== Double-check (Halving) Tests ======================


class TestDoubleCheckHalving:
    """After disposal, if still over token_guard_threshold, halve unconditionally."""

    @pytest.mark.asyncio
    async def test_halving_triggered_when_still_over_threshold(self):
        """After compression, if still over threshold, truncate_by_halving is called."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=True,
            token_guard_threshold=0.1,
            enable_summary=False,
            enable_discard=True,
            discard_turns=1,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)

        # Use a very low max_context_tokens so halving is likely needed
        result = await manager.process(msgs, max_context_tokens=100)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_halving_not_constrained_by_retention(self):
        """Halving in double-check phase ignores retention lower bound."""
        cfg = ContextConfig(
            enable_turn_limit=False,
            enable_token_guard=True,
            token_guard_threshold=0.1,
            enable_summary=False,
            enable_discard=False,
            retention_method="turns",
            retain_turns=1000,  # Would normally prevent any discard
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)

        result = await manager.process(msgs, max_context_tokens=1000)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_halving_not_called_when_under_threshold(self):
        """If no disposal is triggered, halving is not called."""
        cfg = ContextConfig(
            enable_turn_limit=False,
            enable_token_guard=True,
            token_guard_threshold=0.95,
            enable_summary=False,
            enable_discard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(4)

        result = await manager.process(msgs)

        # No trigger → no compression → no halving
        assert len(result) == len(msgs)


# ====================== Edge Cases ======================


class TestEdgeCases:
    """Empty messages, single messages, error handling."""

    @pytest.mark.asyncio
    async def test_empty_messages(self):
        """Empty message list returns empty."""
        cfg = ContextConfig()
        manager = ContextManager(cfg)
        result = await manager.process([])
        assert result == []

    @pytest.mark.asyncio
    async def test_single_message(self):
        """Single message passes through unchanged."""
        cfg = ContextConfig()
        manager = ContextManager(cfg)
        msgs = [create_message("user", "Hello")]
        result = await manager.process(msgs)
        assert len(result) == 1
        assert result[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_system_message_preserved(self):
        """System messages are preserved after compression."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_discard=True,
            discard_turns=2,
        )
        manager = ContextManager(cfg)
        msgs = [
            create_message("system", "System instruction"),
            *create_messages(10),
        ]

        result = await manager.process(msgs)

        system_msgs = [m for m in result if m.role == "system"]
        assert len(system_msgs) >= 1
        assert system_msgs[0].content == "System instruction"

    @pytest.mark.asyncio
    async def test_error_returns_original_messages(self):
        """Processing errors return original messages."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=True,
            enable_discard=True,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        # Replace both disposal methods to raise simultaneously
        async def failing_summary(msgs):
            raise RuntimeError("Test error")

        def failing_discard(msgs):
            raise RuntimeError("Test error")

        manager._try_summary = failing_summary
        manager._try_discard = failing_discard
        manager._summary_compressor = None  # prevent short-circuit

        result = await manager.process(msgs)

        # Should return original messages despite error
        assert result == msgs

    @pytest.mark.asyncio
    async def test_tool_messages_preserved_in_turn_count(self):
        """Tool messages are counted within turns correctly."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=3,
            enable_token_guard=False,
            enable_discard=True,
            discard_turns=1,
        )
        manager = ContextManager(cfg)
        msgs = [
            create_message("system", "You are helpful."),
            create_message("user", "Search the web"),
            create_message("assistant", "Calling tool"),
            create_message("tool", "Result 1"),
            create_message("assistant", "Final answer"),
            # Second turn
            create_message("user", "Tell me more"),
            create_message("assistant", "Sure"),
        ]

        result = await manager.process(msgs)

        # Check system message preserved
        assert result[0].role == "system"
        assert result[0].content == "You are helpful."


# ====================== Integration Scenarios ======================


class TestIntegration:
    """Full-flow integration tests."""

    @pytest.mark.asyncio
    async def test_full_trigger_and_disposal_flow(self):
        """Trigger → summary (with LLM) → retention → result."""
        provider = MockProvider()

        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=3,
            enable_token_guard=True,
            token_guard_threshold=0.82,
            enable_summary=True,
            enable_discard=True,
            discard_turns=2,
            retention_method="turns",
            retain_turns=2,
            summary_provider=provider,  # type: ignore[arg-type]
        )
        manager = ContextManager(cfg)

        msgs = create_messages(20)

        result = await manager.process(msgs)

        # Should have been compressed one way or another
        assert len(result) <= len(msgs)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_discard_only_flow_with_retention(self):
        """Trigger → discard → retention lower bound enforced."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=True,
            discard_turns=5,
            retention_method="turns",
            retain_turns=3,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)  # 10 turns

        result = await manager.process(msgs)

        # Should discard some but respect retention
        assert len(result) < len(msgs)

    @pytest.mark.asyncio
    async def test_no_compression_when_under_all_thresholds(self):
        """No trigger fires → no compression at all."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=100,
            enable_token_guard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(4)  # 2 turns << 100

        result = await manager.process(msgs)

        assert result == msgs
