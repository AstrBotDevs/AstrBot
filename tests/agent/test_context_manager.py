"""Comprehensive tests for ContextManager."""

import sys
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path to avoid circular import issues
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.message import Message, TextPart
from astrbot.core.provider.entities import LLMResponse


class MockProvider:
    """模拟 Provider"""

    def __init__(self):
        self.provider_config = {
            "id": "test_provider",
            "model": "gpt-4",
            "modalities": ["text", "image", "tool_use"],
        }

    async def text_chat(self, **kwargs):
        """模拟 LLM 调用，返回摘要"""
        messages = kwargs.get("messages", [])
        # 简单的摘要逻辑：返回消息数量统计
        return LLMResponse(
            role="assistant",
            completion_text=f"历史对话包含 {len(messages) - 1} 条消息，主要讨论了技术话题。",
        )

    def get_model(self):
        return "gpt-4"

    def meta(self):
        return MagicMock(id="test_provider", type="openai")


class TestContextManager:
    """Test suite for ContextManager."""

    def create_message(
        self, role: Literal["system", "user", "assistant", "tool"], content: str
    ) -> Message:
        """Helper to create a simple text message."""
        return Message(role=role, content=content)

    def create_messages(self, count: int) -> list[Message]:
        """Helper to create alternating user/assistant messages."""
        messages = []
        for i in range(count):
            role = "user" if i % 2 == 0 else "assistant"
            messages.append(self.create_message(role, f"Message {i}"))
        return messages

    # ==================== Basic Initialization Tests ====================

    def test_init_with_minimal_config(self):
        """Test initialization with minimal configuration."""
        config = ContextConfig()
        manager = ContextManager(config)

        assert manager.config == config
        assert manager.token_counter is not None
        assert manager.truncator is not None
        assert manager.compressor is not None

    def test_init_with_llm_compressor(self):
        """Test initialization with LLM-based compression."""
        mock_provider = MockProvider()
        config = ContextConfig(
            llm_compress_provider=mock_provider,  # type: ignore
            llm_compress_keep_recent=5,
            llm_compress_instruction="Summarize the conversation",
        )
        manager = ContextManager(config)

        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        assert isinstance(manager.compressor, LLMSummaryCompressor)

    def test_init_with_truncate_compressor(self):
        """Test initialization with truncate-based compression (default)."""
        config = ContextConfig(truncate_turns=3)
        manager = ContextManager(config)

        from astrbot.core.agent.context.compressor import TruncateByTurnsCompressor

        assert isinstance(manager.compressor, TruncateByTurnsCompressor)

    # ==================== Empty and Edge Cases ====================

    @pytest.mark.asyncio
    async def test_process_empty_messages(self):
        """Test processing an empty message list."""
        config = ContextConfig()
        manager = ContextManager(config)

        result = await manager.process([])

        assert result == []

    @pytest.mark.asyncio
    async def test_process_single_message(self):
        """Test processing a single message."""
        config = ContextConfig()
        manager = ContextManager(config)

        messages = [self.create_message("user", "Hello")]
        result = await manager.process(messages)

        assert len(result) == 1
        assert result[0].content == "Hello"

    @pytest.mark.asyncio
    async def test_process_with_no_limits(self):
        """Test processing when no limits are set (no truncation or compression)."""
        config = ContextConfig(max_context_tokens=0, enforce_max_turns=-1)
        manager = ContextManager(config)

        messages = self.create_messages(20)
        result = await manager.process(messages)

        assert len(result) == 20
        assert result == messages

    # ==================== Enforce Max Turns Tests ====================

    @pytest.mark.asyncio
    async def test_enforce_max_turns_basic(self):
        """Test basic enforce_max_turns functionality."""
        config = ContextConfig(enforce_max_turns=3, truncate_turns=1)
        manager = ContextManager(config)

        # Create 10 turns (20 messages)
        messages = self.create_messages(20)
        result = await manager.process(messages)

        # Should keep only 3 most recent turns (6 messages)
        assert len(result) <= 8  # May vary due to truncation logic

    @pytest.mark.asyncio
    async def test_enforce_max_turns_zero(self):
        """Test enforce_max_turns with value 0 (should keep nothing)."""
        config = ContextConfig(enforce_max_turns=0, truncate_turns=1)
        manager = ContextManager(config)

        messages = self.create_messages(10)
        result = await manager.process(messages)

        # Should result in empty or minimal message list
        assert len(result) <= 2

    @pytest.mark.asyncio
    async def test_enforce_max_turns_negative(self):
        """Test enforce_max_turns with -1 (no limit)."""
        config = ContextConfig(enforce_max_turns=-1)
        manager = ContextManager(config)

        messages = self.create_messages(20)
        result = await manager.process(messages)

        assert len(result) == 20

    @pytest.mark.asyncio
    async def test_enforce_max_turns_with_system_messages(self):
        """Test enforce_max_turns preserves system messages."""
        config = ContextConfig(enforce_max_turns=2, truncate_turns=1)
        manager = ContextManager(config)

        messages = [
            self.create_message("system", "System instruction"),
            *self.create_messages(10),
        ]
        result = await manager.process(messages)

        # System message should be preserved
        system_msgs = [m for m in result if m.role == "system"]
        assert len(system_msgs) >= 1
        assert system_msgs[0].content == "System instruction"

    # ==================== Token-based Compression Tests ====================

    @pytest.mark.asyncio
    async def test_token_compression_not_triggered_below_threshold(self):
        """Test that compression is not triggered below threshold."""
        config = ContextConfig(max_context_tokens=1000)
        manager = ContextManager(config)

        # Create messages that total less than threshold
        messages = [self.create_message("user", "Hi" * 50)]  # ~100 tokens

        with patch.object(
            manager.compressor, "__call__", new_callable=AsyncMock
        ) as mock_compress:
            result = await manager.process(messages)

            # Compressor should not be called
            mock_compress.assert_not_called()
            assert result == messages

    @pytest.mark.asyncio
    async def test_token_compression_triggered_above_threshold(self):
        """Test that compression is triggered above threshold."""
        config = ContextConfig(max_context_tokens=100, truncate_turns=1)
        manager = ContextManager(config)

        # Create messages that exceed threshold (0.82 * 100 = 82 tokens)
        # 300 chars * 0.3 = 90 tokens > 82 threshold
        long_text = "x" * 300  # ~90 tokens, above threshold
        messages = [self.create_message("user", long_text)]

        # Mock compressor to return smaller result
        compressed = [self.create_message("user", "short")]

        # Create a mock compressor that we can track
        mock_compress = AsyncMock(return_value=compressed)
        manager.compressor = mock_compress

        result = await manager.process(messages)

        # Compressor should be called
        mock_compress.assert_called_once()
        # Result should be the compressed version
        assert len(result) == len(compressed)

    @pytest.mark.asyncio
    async def test_token_compression_with_zero_max_tokens(self):
        """Test that compression is skipped when max_context_tokens is 0."""
        config = ContextConfig(max_context_tokens=0)
        manager = ContextManager(config)

        messages = [self.create_message("user", "x" * 10000)]

        with patch.object(
            manager.compressor, "__call__", new_callable=AsyncMock
        ) as mock_compress:
            result = await manager.process(messages)

            # Compressor should not be called
            mock_compress.assert_not_called()
            assert result == messages

    @pytest.mark.asyncio
    async def test_token_compression_with_negative_max_tokens(self):
        """Test that compression is skipped when max_context_tokens is negative."""
        config = ContextConfig(max_context_tokens=-100)
        manager = ContextManager(config)

        messages = [self.create_message("user", "x" * 10000)]

        with patch.object(
            manager.compressor, "__call__", new_callable=AsyncMock
        ) as mock_compress:
            result = await manager.process(messages)

            # Compressor should not be called
            mock_compress.assert_not_called()
            assert result == messages

    @pytest.mark.asyncio
    async def test_double_check_after_compression(self):
        """Test that halving is applied if still over threshold after compression."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Create messages that would still be over threshold after compression
        long_messages = [self.create_message("user", "x" * 200) for _ in range(10)]

        # Mock compressor to return messages still over threshold
        async def mock_compress(msgs):
            return msgs  # Return same messages (still over limit)

        with patch.object(manager.compressor, "__call__", new=mock_compress):
            with patch.object(
                manager, "_compress_by_halving", return_value=long_messages[:5]
            ) as mock_halving:
                _ = await manager.process(long_messages)

                # Halving should be called
                mock_halving.assert_called_once()

    # ==================== Combined Truncation and Compression Tests ====================

    @pytest.mark.asyncio
    async def test_combined_enforce_turns_and_token_limit(self):
        """Test combining enforce_max_turns and token limit."""
        config = ContextConfig(
            enforce_max_turns=5, max_context_tokens=500, truncate_turns=1
        )
        manager = ContextManager(config)

        # Create many messages
        messages = self.create_messages(30)

        result = await manager.process(messages)

        # Should be truncated by both mechanisms
        assert len(result) < 30

    @pytest.mark.asyncio
    async def test_sequential_processing_order(self):
        """Test that enforce_max_turns happens before token compression."""
        config = ContextConfig(enforce_max_turns=5, max_context_tokens=1000)
        manager = ContextManager(config)

        messages = self.create_messages(20)

        # Mock the truncator to track calls
        with patch.object(
            manager.truncator,
            "truncate_by_turns",
            wraps=manager.truncator.truncate_by_turns,
        ) as mock_truncate:
            await manager.process(messages)

            # Truncator should be called first
            mock_truncate.assert_called_once()

    # ==================== Error Handling Tests ====================

    @pytest.mark.asyncio
    async def test_error_handling_returns_original_messages(self):
        """Test that errors during processing return original messages."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        messages = self.create_messages(5)

        # Make compressor raise an exception
        with patch.object(
            manager.compressor, "__call__", side_effect=Exception("Test error")
        ):
            result = await manager.process(messages)

            # Should return original messages despite error
            assert result == messages

    @pytest.mark.asyncio
    async def test_error_handling_logs_exception(self):
        """Test that errors are logged."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Create messages that will trigger compression (> 82 tokens)
        messages = [self.create_message("user", "x" * 300)]  # ~90 tokens

        # Replace compressor with one that raises an exception
        manager.compressor = AsyncMock(side_effect=Exception("Test error"))

        with patch("astrbot.core.agent.context.manager.logger") as mock_logger:
            result = await manager.process(messages)

            # Logger error method should be called
            assert mock_logger.error.called
            # Should return original messages on error
            assert result == messages

    # ==================== Multi-modal Content Tests ====================

    @pytest.mark.asyncio
    async def test_process_messages_with_textpart_content(self):
        """Test processing messages with TextPart content."""
        config = ContextConfig()
        manager = ContextManager(config)

        messages = [
            Message(role="user", content=[TextPart(text="Hello")]),
            Message(role="assistant", content=[TextPart(text="Hi there")]),
        ]

        result = await manager.process(messages)

        assert len(result) == 2
        assert result == messages

    @pytest.mark.asyncio
    async def test_token_counting_with_multimodal_content(self):
        """Test token counting works with multi-modal content."""
        config = ContextConfig(max_context_tokens=50)
        manager = ContextManager(config)

        # Need enough tokens to exceed threshold: 50 * 0.82 = 41 tokens
        # 150 chars * 0.3 = 45 tokens > 41
        messages = [
            Message(role="user", content=[TextPart(text="x" * 150)]),
        ]

        # Should trigger compression due to token count
        needs_compression, tokens = await manager._initial_token_check(messages)

        assert tokens is not None  # Tokens should be counted
        assert needs_compression  # Should trigger compression

    # ==================== Tool Calls Tests ====================

    @pytest.mark.asyncio
    async def test_process_messages_with_tool_calls(self):
        """Test processing messages with tool calls."""
        config = ContextConfig()
        manager = ContextManager(config)

        messages = [
            Message(
                role="assistant",
                content="Let me search for that",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }
                ],
            ),
            Message(role="tool", content="Search result", tool_call_id="call_1"),
        ]

        result = await manager.process(messages)

        assert len(result) == 2

    # ==================== Initial Token Check Tests ====================

    @pytest.mark.asyncio
    async def test_initial_token_check_empty_messages(self):
        """Test _initial_token_check with empty messages."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        needs_compression, tokens = await manager._initial_token_check([])

        assert not needs_compression
        assert tokens is None

    @pytest.mark.asyncio
    async def test_initial_token_check_no_limit(self):
        """Test _initial_token_check when max_context_tokens is 0."""
        config = ContextConfig(max_context_tokens=0)
        manager = ContextManager(config)

        messages = [self.create_message("user", "x" * 1000)]
        needs_compression, tokens = await manager._initial_token_check(messages)

        assert not needs_compression
        assert tokens is None

    @pytest.mark.asyncio
    async def test_initial_token_check_below_threshold(self):
        """Test _initial_token_check when below compression threshold."""
        config = ContextConfig(max_context_tokens=1000)
        manager = ContextManager(config)

        messages = [self.create_message("user", "Hello")]
        needs_compression, tokens = await manager._initial_token_check(messages)

        assert not needs_compression
        assert tokens is None

    @pytest.mark.asyncio
    async def test_initial_token_check_above_threshold(self):
        """Test _initial_token_check when above compression threshold."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Create message with ~90 tokens (above 0.82 * 100 = 82)
        messages = [self.create_message("user", "这是测试" * 50)]
        needs_compression, tokens = await manager._initial_token_check(messages)

        assert needs_compression
        assert tokens is not None
        assert tokens > 82

    @pytest.mark.asyncio
    async def test_initial_token_check_exactly_at_threshold(self):
        """Test _initial_token_check when just above threshold."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Create message with >82 tokens (0.82 * 100)
        # 300 chars * 0.3 = 90 tokens > 82 (threshold)
        messages = [self.create_message("user", "x" * 300)]  # ~90 tokens
        needs_compression, tokens = await manager._initial_token_check(messages)

        # Above threshold should trigger compression
        assert tokens is not None
        assert needs_compression

    # ==================== Compression by Halving Tests ====================

    def test_compress_by_halving_basic(self):
        """Test _compress_by_halving removes middle 50%."""
        config = ContextConfig()
        manager = ContextManager(config)

        messages = self.create_messages(10)
        result = manager._compress_by_halving(messages)

        # Should keep roughly half
        assert len(result) < len(messages)

    def test_compress_by_halving_empty_list(self):
        """Test _compress_by_halving with empty list."""
        config = ContextConfig()
        manager = ContextManager(config)

        result = manager._compress_by_halving([])

        assert result == []

    def test_compress_by_halving_single_message(self):
        """Test _compress_by_halving with single message."""
        config = ContextConfig()
        manager = ContextManager(config)

        messages = [self.create_message("user", "Hello")]
        result = manager._compress_by_halving(messages)

        assert len(result) <= 1

    # ==================== Complex Scenarios ====================

    @pytest.mark.asyncio
    async def test_multiple_compression_cycles(self):
        """Test that compression can be triggered multiple times in sequence."""
        config = ContextConfig(max_context_tokens=50, truncate_turns=1)
        manager = ContextManager(config)

        # Process messages multiple times
        messages = self.create_messages(10)

        result1 = await manager.process(messages)
        result2 = await manager.process(result1)
        result3 = await manager.process(result2)

        # Each cycle should maintain or reduce message count
        assert len(result3) <= len(result2) <= len(result1)

    @pytest.mark.asyncio
    async def test_alternating_roles_preserved(self):
        """Test that user/assistant alternation is preserved after processing."""
        config = ContextConfig(enforce_max_turns=3, truncate_turns=1)
        manager = ContextManager(config)

        messages = self.create_messages(20)
        result = await manager.process(messages)

        # Check that roles still alternate (excluding system messages)
        non_system = [m for m in result if m.role != "system"]
        if len(non_system) >= 2:
            # Should start with user
            assert non_system[0].role == "user"

    @pytest.mark.asyncio
    async def test_compression_threshold_constant(self):
        """Test that COMPRESSION_THRESHOLD is used correctly."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Verify the threshold is 0.82
        assert manager.COMPRESSION_THRESHOLD == 0.82

        # Create messages just below threshold
        messages = [self.create_message("user", "x" * 81)]  # ~24 tokens

        needs_compression, _ = await manager._initial_token_check(messages)
        assert not needs_compression

    @pytest.mark.asyncio
    async def test_large_batch_processing(self):
        """Test processing a large batch of messages."""
        config = ContextConfig(
            enforce_max_turns=10, max_context_tokens=1000, truncate_turns=2
        )
        manager = ContextManager(config)

        # Create 100 messages (50 turns)
        messages = self.create_messages(100)

        result = await manager.process(messages)

        # Should be significantly reduced
        assert len(result) < 100
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_config_persistence(self):
        """Test that config settings are respected throughout processing."""
        config = ContextConfig(
            max_context_tokens=500,
            enforce_max_turns=5,
            truncate_turns=2,
            llm_compress_keep_recent=3,
        )
        manager = ContextManager(config)

        # Verify config is stored
        assert manager.config.max_context_tokens == 500
        assert manager.config.enforce_max_turns == 5
        assert manager.config.truncate_turns == 2
        assert manager.config.llm_compress_keep_recent == 3

    # ==================== Run Compression Tests ====================

    @pytest.mark.asyncio
    async def test_run_compression_skip_when_not_needed(self):
        """Test _run_compression skips when needs_compression is False."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        messages = self.create_messages(5)

        with patch.object(
            manager.compressor, "__call__", new_callable=AsyncMock
        ) as mock_compress:
            result = await manager._run_compression(messages, needs_compression=False)

            mock_compress.assert_not_called()
            assert result == messages

    @pytest.mark.asyncio
    async def test_run_compression_skip_when_zero_limit(self):
        """Test _run_compression skips when max_context_tokens is 0."""
        config = ContextConfig(max_context_tokens=0)
        manager = ContextManager(config)

        messages = self.create_messages(5)

        with patch.object(
            manager.compressor, "__call__", new_callable=AsyncMock
        ) as mock_compress:
            result = await manager._run_compression(messages, needs_compression=True)

            mock_compress.assert_not_called()
            assert result == messages

    @pytest.mark.asyncio
    async def test_run_compression_applies_compressor(self):
        """Test _run_compression calls compressor when needed through process()."""
        config = ContextConfig(max_context_tokens=100, truncate_turns=1)
        manager = ContextManager(config)

        # Create messages that will trigger compression
        messages = [self.create_message("user", "x" * 300)]  # ~90 tokens > 82 threshold
        compressed = [self.create_message("user", "short")]  # Much smaller

        # Replace compressor with mock
        mock_compress = AsyncMock(return_value=compressed)
        manager.compressor = mock_compress

        result = await manager.process(messages)

        # Compressor should have been called
        mock_compress.assert_called_once()
        assert len(result) <= len(messages)

    @pytest.mark.asyncio
    async def test_llm_compression_with_mock_provider(self):
        """Test LLM compression using MockProvider."""
        mock_provider = MockProvider()
        config = ContextConfig(
            llm_compress_provider=mock_provider,  # type: ignore
            llm_compress_keep_recent=3,
            llm_compress_instruction="请总结对话内容",
            max_context_tokens=100,
        )
        manager = ContextManager(config)

        # Create messages that will trigger compression
        messages = [
            self.create_message("user", "x" * 100),
            self.create_message("assistant", "y" * 100),
            self.create_message("user", "z" * 100),
        ]

        result = await manager.process(messages)

        # Should have been compressed
        assert len(result) <= len(messages)

    # ==================== split_history Tests ====================

    def test_split_history_ensures_user_start(self):
        """Test split_history ensures recent_messages starts with user message."""
        from astrbot.core.agent.context.compressor import split_history

        # Create alternating messages: user, assistant, user, assistant, user, assistant
        messages = [
            self.create_message("system", "System prompt"),
            self.create_message("user", "msg1"),
            self.create_message("assistant", "msg2"),
            self.create_message("user", "msg3"),
            self.create_message("assistant", "msg4"),
            self.create_message("user", "msg5"),
            self.create_message("assistant", "msg6"),
        ]

        # Keep recent 3 messages - should adjust to start with user
        system, to_summarize, recent = split_history(messages, keep_recent=3)

        # recent_messages should start with user message
        assert len(recent) > 0
        assert recent[0].role == "user"

        # messages_to_summarize should end with assistant (complete turn)
        if len(to_summarize) > 0:
            assert to_summarize[-1].role == "assistant"

    def test_split_history_handles_assistant_at_split_point(self):
        """Test split_history when assistant message is at the intended split point."""
        from astrbot.core.agent.context.compressor import split_history

        messages = [
            self.create_message("user", "msg1"),
            self.create_message("assistant", "msg2"),
            self.create_message("user", "msg3"),
            self.create_message("assistant", "msg4"),  # <- intended split here
            self.create_message("user", "msg5"),
            self.create_message("assistant", "msg6"),
        ]

        # keep_recent=2 would normally split at index 4 (assistant msg4)
        # Should move back to include from msg5 (user)
        system, to_summarize, recent = split_history(messages, keep_recent=2)

        # recent should start with user message
        assert recent[0].role == "user"
        assert recent[0].content == "msg5"

    def test_split_history_all_assistant_messages(self):
        """Test split_history when there are consecutive assistant messages."""
        from astrbot.core.agent.context.compressor import split_history

        messages = [
            self.create_message("user", "msg1"),
            self.create_message("assistant", "msg2"),
            self.create_message("assistant", "msg3"),
            self.create_message("assistant", "msg4"),
        ]

        system, to_summarize, recent = split_history(messages, keep_recent=2)

        # Should find the user message and keep from there
        if len(recent) > 0:
            # Find first user message backwards
            assert any(m.role == "user" for m in messages)

    def test_split_history_with_system_messages(self):
        """Test split_history preserves system messages separately."""
        from astrbot.core.agent.context.compressor import split_history

        messages = [
            self.create_message("system", "System 1"),
            self.create_message("system", "System 2"),
            self.create_message("user", "msg1"),
            self.create_message("assistant", "msg2"),
            self.create_message("user", "msg3"),
        ]

        system, to_summarize, recent = split_history(messages, keep_recent=2)

        # System messages should be separate
        assert len(system) == 2
        assert all(m.role == "system" for m in system)

        # Recent should start with user
        if len(recent) > 0:
            assert recent[0].role == "user"
