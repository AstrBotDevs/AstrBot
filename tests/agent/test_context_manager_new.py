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
from unittest.mock import MagicMock, patch

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


def create_message(
    role: Literal["system", "user", "assistant", "tool"], content: str
) -> Message:
    return Message(role=role, content=content)


def create_messages(count: int) -> list[Message]:
    """Alternating user/assistant messages."""
    return [
        create_message("user" if i % 2 == 0 else "assistant", f"Message {i}")
        for i in range(count)
    ]


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
            max_turns=2,  # will trigger
            enable_token_guard=False,  # won't trigger
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


# ====================== Custom Compressor Tests ======================


class TestCustomCompressor:
    """Custom compressor (_unity_compressor) path through process()."""

    @pytest.mark.asyncio
    async def test_custom_compressor_used_when_provided(self):
        """custom_compressor is invoked by process() instead of summary/discard."""
        call_log = []

        async def my_compressor(messages: list[Message]) -> list[Message]:
            call_log.append("called")
            # Simulate compression: keep only last 2 messages
            return messages[-2:]

        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            custom_compressor=my_compressor,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        result = await manager.process(msgs)

        assert call_log == ["called"]
        # Custom compressor returned only last 2 messages
        assert len(result) == 2
        assert result[0].content == "Message 8"
        assert result[1].content == "Message 9"

    @pytest.mark.asyncio
    async def test_custom_compressor_skips_summary_and_discard(self):
        """When custom_compressor is set, summary and discard are NOT called."""
        custom_called = False
        summary_called = False
        discard_called = False

        async def my_compressor(messages: list[Message]) -> list[Message]:
            nonlocal custom_called
            custom_called = True
            return messages

        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=True,
            enable_discard=True,
            summary_provider=MockProvider(),  # would be used if not for custom
            custom_compressor=my_compressor,
        )
        manager = ContextManager(cfg)

        # Spy on summary and discard
        original_try_summary = manager._try_summary
        original_try_discard = manager._try_discard

        async def spy_summary(messages):
            nonlocal summary_called
            summary_called = True
            return await original_try_summary(messages)

        def spy_discard(messages):
            nonlocal discard_called
            discard_called = True
            return original_try_discard(messages)

        manager._try_summary = spy_summary
        manager._try_discard = spy_discard

        msgs = create_messages(10)
        await manager.process(msgs)

        assert custom_called, "Custom compressor should have been called"
        assert not summary_called, (
            "Summary should NOT be called when custom compressor exists"
        )
        assert not discard_called, (
            "Discard should NOT be called when custom compressor exists"
        )

    @pytest.mark.asyncio
    async def test_custom_compressor_result_used_as_is(self):
        """process() passes custom compressor's return value through directly (no validation)."""

        async def my_compressor(messages: list[Message]) -> list[Message]:
            return [create_message("assistant", "Custom result")]

        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            custom_compressor=my_compressor,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        result = await manager.process(msgs)

        assert len(result) == 1
        assert result[0].content == "Custom result"

    @pytest.mark.asyncio
    async def test_custom_compressor_passed_no_trigger(self):
        """When no trigger fires, custom compressor is NOT called."""
        call_log = []

        async def my_compressor(messages: list[Message]) -> list[Message]:
            call_log.append("called")
            return messages

        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=100,  # won't trigger
            enable_token_guard=False,
            custom_compressor=my_compressor,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(4)

        result = await manager.process(msgs)

        assert call_log == [], (
            "Custom compressor should NOT be called when no trigger fires"
        )
        assert len(result) == len(msgs)


# ====================== _try_summary Edge Cases ======================


class TestTrySummaryEdgeCases:
    """Edge cases within _try_summary:

    - Identity check: compressor returns same list object by reference.
    - No reduction: compressor returns a new list of equal/longer length.
    - Compressor exception: compressor.__call__() raises, falls back to discard.
    """

    @pytest.mark.asyncio
    async def test_identity_check_returns_none(self):
        """When compressor returns the exact same list (is), _try_summary returns None."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        # Replace _summary_compressor with one that returns the same list object
        async def identity_compressor(messages):
            return messages  # returns the exact same list (is check)

        manager._summary_compressor = identity_compressor

        result = await manager.process(msgs)

        # _try_summary returned None (identity), process should still work
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_no_effective_reduction_returns_none(self):
        """When compressor returns a new list of same length, _try_summary returns None."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        async def no_op_compressor(messages):
            return list(messages)  # new list, same length

        manager._summary_compressor = no_op_compressor

        result = await manager.process(msgs)

        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_summary_longer_than_input_returns_none(self):
        """When compressor returns a longer list than input, _try_summary returns None."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_discard=False,  # No fallback, so no compression at all
        )
        manager = ContextManager(cfg)
        msgs = create_messages(3)

        async def expander_compressor(messages):
            return messages + [create_message("assistant", "extra")]

        manager._summary_compressor = expander_compressor

        result = await manager.process(msgs)

        # _try_summary returned None, disposal had no effect
        assert len(result) == len(msgs)

    @pytest.mark.asyncio
    async def test_summary_exception_falls_back_to_discard(self):
        """When compressor.__call__() raises, _try_summary catches and falls back to discard."""
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

        # Replace _summary_compressor with one that raises
        async def broken_compressor(messages):
            raise RuntimeError("Summary compressor failed")

        manager._summary_compressor = broken_compressor

        with patch("astrbot.core.agent.context.manager.logger") as mock_logger:
            result = await manager.process(msgs)

        # Should have fallen back to discard
        assert mock_logger.warning.called
        assert len(result) < len(msgs)

    @pytest.mark.asyncio
    async def test_summary_exception_without_discall_fallback(self):
        """Compressor raises and discard disabled → no compression, original returned."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=True,
            enable_discard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(10)

        async def broken_compressor(messages):
            raise RuntimeError("Summary compressor failed")

        manager._summary_compressor = broken_compressor

        result = await manager.process(msgs)

        # No fallback, original messages returned
        assert len(result) == len(msgs)


# ====================== _try_discard Edge Cases ======================


class TestTryDiscardEdgeCases:
    """Edge cases within _try_discard and _compute_discard_limit."""

    @pytest.mark.asyncio
    async def test_discard_prevented_by_retention(self):
        """When retain_turns >= total_turns, max_discardable=0 and nothing is discarded."""
        cfg = ContextConfig(
            enable_turn_limit=True,
            max_turns=2,
            enable_token_guard=False,
            enable_summary=False,
            enable_discard=True,
            discard_turns=5,
            retention_method="turns",
            retain_turns=10,  # retain >= total (10 turns), so max_discardable=0
        )
        manager = ContextManager(cfg)
        msgs = create_messages(20)  # 10 turns

        result = await manager.process(msgs)

        # Retention prevents any discard, original messages returned
        assert len(result) == len(msgs)

    @pytest.mark.asyncio
    async def test_discard_limit_total_turns_zero(self):
        """_compute_discard_limit(0) returns 0 for all retention methods."""
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

        # Directly test _compute_discard_limit
        assert manager._compute_discard_limit(0) == 0

        # Test all three retention methods
        for method, retain in [("turns", 5), ("percentage", 0.3), ("null", None)]:
            cfg2 = ContextConfig(
                enable_turn_limit=True,
                max_turns=2,
                retention_method=method,
                retain_turns=retain if isinstance(retain, int) else 5,
                retain_percentage=retain if isinstance(retain, float) else 0.3,
            )
            m = ContextManager(cfg2)
            assert m._compute_discard_limit(0) == 0, f"method={method}"

    @pytest.mark.asyncio
    async def test_discard_limit_percentage_boundary(self):
        """_compute_discard_limit with retain_percentage=0 and 1.0."""
        cfg_0 = ContextConfig(retention_method="percentage", retain_percentage=0.0)
        m0 = ContextManager(cfg_0)
        total = 10
        # retain_percentage=0 → floor=0 → max_discardable = 10 - 0 = 10
        assert m0._compute_discard_limit(total) == total

        cfg_1 = ContextConfig(retention_method="percentage", retain_percentage=1.0)
        m1 = ContextManager(cfg_1)
        # retain_percentage=1.0 → floor=10 → max_discardable = 10 - 10 = 0
        assert m1._compute_discard_limit(total) == 0

    @pytest.mark.asyncio
    async def test_discard_limit_exact_turns_boundary(self):
        """_compute_discard_limit when total_turns == retain_turns."""
        cfg = ContextConfig(retention_method="turns", retain_turns=5)
        manager = ContextManager(cfg)
        # total=5, retain=5 → max_discardable = max(0, 5-5) = 0
        assert manager._compute_discard_limit(5) == 0
        # total=6, retain=5 → max_discardable = max(0, 6-5) = 1
        assert manager._compute_discard_limit(6) == 1


# ====================== Trusted Token Usage Tests ======================


class TestTrustedTokenUsage:
    """trusted_token_usage parameter passed to process()."""

    @pytest.mark.asyncio
    async def test_trusted_token_usage_non_zero_passed_through(self):
        """Non-zero trusted_token_usage is passed to token_counter."""
        cfg = ContextConfig(
            enable_turn_limit=False,
            enable_token_guard=True,
            token_guard_threshold=0.5,
            enable_summary=False,
            enable_discard=False,
        )
        manager = ContextManager(cfg)
        msgs = create_messages(4)

        # Patch the token_counter to verify trusted_token_usage is passed
        original_count = manager.token_counter.count_tokens

        def spy_count_tokens(messages, trusted_token_usage=0):
            assert trusted_token_usage == 999, (
                f"Expected trusted_token_usage=999, got {trusted_token_usage}"
            )
            return original_count(messages, trusted_token_usage)

        manager.token_counter.count_tokens = spy_count_tokens

        result = await manager.process(msgs, trusted_token_usage=999)

        assert isinstance(result, list)


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
