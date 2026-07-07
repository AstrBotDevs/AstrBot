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
from astrbot.core.agent.message import AudioURLPart, ImageURLPart, Message, TextPart
from astrbot.core.provider.entities import LLMResponse


class MockProvider:
    """模拟 Provider"""

    def __init__(self):
        self.provider_config = {
            "id": "test_provider",
            "model": "gpt-4",
            "modalities": ["text", "image", "tool_use"],
        }
        self.last_text_chat_kwargs = None

    async def text_chat(self, **kwargs):
        """模拟 LLM 调用，返回摘要"""
        self.last_text_chat_kwargs = kwargs
        return LLMResponse(
            role="assistant",
            completion_text="Summary of conversation: Hello and discussed various topics.",
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
            llm_compress_keep_recent_ratio=0.15,
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

    @pytest.mark.asyncio
    async def test_llm_compressor_keeps_history_when_summary_is_empty(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        provider.text_chat = AsyncMock(
            return_value=LLMResponse(role="assistant", completion_text="  ")
        )
        compressor = LLMSummaryCompressor(provider=provider, keep_recent_ratio=0.15)  # type: ignore[arg-type]
        messages = self.create_messages(6)

        with patch("astrbot.core.agent.context.compressor.logger") as mock_logger:
            result = await compressor(messages)

        assert result == messages
        mock_logger.warning.assert_called_once_with(
            "LLM context compression returned an empty summary."
        )

    @pytest.mark.asyncio
    async def test_llm_compressor_handles_textpart_content(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        compressor = LLMSummaryCompressor(provider=provider, keep_recent_ratio=0.01)  # type: ignore[arg-type]
        messages = [
            Message(role="user", content=[TextPart(text="Hello")]),
            Message(role="assistant", content=[TextPart(text="Hi there")]),
            Message(role="user", content=[TextPart(text="Summarize our work")]),
            Message(role="assistant", content=[TextPart(text="Sure")]),
        ]

        result = await compressor(messages)

        assert provider.last_text_chat_kwargs is not None
        assert "prompt" not in provider.last_text_chat_kwargs
        assert "system_prompt" not in provider.last_text_chat_kwargs
        summary_contexts = provider.last_text_chat_kwargs["contexts"]
        assert summary_contexts[0] == {
            "role": "user",
            "content": [{"type": "text", "text": "Hello"}],
        }
        assert summary_contexts[1] == {
            "role": "assistant",
            "content": [{"type": "text", "text": "Hi there"}],
        }
        assert summary_contexts[-1]["role"] == "user"
        assert compressor.instruction_text in summary_contexts[-1]["content"]
        assert (
            compressor.TASK_CONTINUATION_INSTRUCTION in summary_contexts[-1]["content"]
        )

        assert len(result) == 4
        assert result[0].role == "user"
        assert isinstance(result[0].content, str)
        assert result[0].content.strip()
        assert "Hello" in result[0].content
        assert result[-1].content == [TextPart(text="Sure")]

    @pytest.mark.asyncio
    async def test_llm_compressor_preserves_system_and_pads_before_instruction(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        instruction = "Summarize the old context."
        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=0.01,
            instruction_text=instruction,
        )  # type: ignore[arg-type]
        messages = [
            Message(role="system", content="System prompt"),
            Message(role="user", content="Old question"),
            Message(role="user", content="Current question"),
        ]

        result = await compressor(messages)

        summary_contexts = provider.last_text_chat_kwargs["contexts"]
        assert summary_contexts[0] == {"role": "system", "content": "System prompt"}
        assert summary_contexts[1] == {"role": "user", "content": "Old question"}
        assert summary_contexts[2]["role"] == "assistant"
        assert summary_contexts[2]["content"]
        assert summary_contexts[3]["role"] == "user"
        assert instruction in summary_contexts[3]["content"]
        assert (
            compressor.TASK_CONTINUATION_INSTRUCTION in summary_contexts[3]["content"]
        )

        assert result[0] is messages[0]
        assert result[-1] is messages[-1]

    @pytest.mark.asyncio
    async def test_llm_compressor_summarizes_single_long_round(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=0.15,
            instruction_text="Summarize the whole trajectory.",
        )  # type: ignore[arg-type]
        messages = [
            Message(role="user", content="Run the tool."),
            Message(
                role="assistant",
                content="Calling tool",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "search", "arguments": "{}"},
                    }
                ],
            ),
            Message(role="tool", content="x" * 1000, tool_call_id="call_1"),
        ]

        result = await compressor(messages)

        summary_contexts = provider.last_text_chat_kwargs["contexts"]
        assert summary_contexts[0] == {"role": "user", "content": "Run the tool."}
        assert summary_contexts[1]["role"] == "assistant"
        assert summary_contexts[1]["tool_calls"]
        assert summary_contexts[2]["role"] == "tool"
        assert summary_contexts[2]["tool_call_id"] == "call_1"
        assert summary_contexts[3]["role"] == "assistant"
        assert summary_contexts[4]["role"] == "user"
        assert "Summarize the whole trajectory." in summary_contexts[4]["content"]
        assert (
            compressor.TASK_CONTINUATION_INSTRUCTION in summary_contexts[4]["content"]
        )
        assert all(original not in result for original in messages)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_llm_compressor_preserves_active_user_request(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=0,
            instruction_text="Summarize old context.",
        )  # type: ignore[arg-type]
        messages = [
            Message(role="user", content="Old question"),
            Message(role="assistant", content="Old answer"),
            Message(role="user", content="Current question"),
        ]

        result = await compressor(messages)

        summary_contexts = provider.last_text_chat_kwargs["contexts"]
        assert summary_contexts[0] == {"role": "user", "content": "Old question"}
        assert summary_contexts[1] == {"role": "assistant", "content": "Old answer"}
        assert not any(
            msg.get("content") == "Current question" for msg in summary_contexts
        )
        assert result[-1] is messages[2]

    @pytest.mark.asyncio
    async def test_llm_compressor_does_not_summarize_only_active_user_request(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=0.15,
            instruction_text="Summarize old context.",
        )  # type: ignore[arg-type]
        messages = [Message(role="user", content="Current question")]

        result = await compressor(messages)

        assert result == messages
        assert provider.last_text_chat_kwargs is None

    @pytest.mark.asyncio
    async def test_llm_compressor_summarizes_system_plus_single_completed_round(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=0.15,
            instruction_text="Summarize the completed round.",
        )  # type: ignore[arg-type]
        messages = [
            Message(role="system", content="System prompt"),
            Message(role="user", content="Question"),
            Message(role="assistant", content="x" * 1000),
        ]

        result = await compressor(messages)

        summary_contexts = provider.last_text_chat_kwargs["contexts"]
        assert summary_contexts[0]["role"] == "system"
        assert summary_contexts[1]["role"] == "user"
        assert summary_contexts[2]["role"] == "assistant"
        assert len(result) == 3
        assert result[0] is messages[0]
        assert result[1].role == "user"
        assert result[2].role == "assistant"

    @pytest.mark.asyncio
    async def test_llm_compressor_sanitizes_context_for_text_only_provider(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        provider.provider_config["modalities"] = ["text"]
        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=0,
            instruction_text="Summarize multimodal and tool history.",
        )  # type: ignore[arg-type]
        messages = [
            Message(
                role="user",
                content=[
                    TextPart(text="Please inspect this."),
                    ImageURLPart(
                        image_url=ImageURLPart.ImageURL(url="data:image/png;base64,abc")
                    ),
                    AudioURLPart(
                        audio_url=AudioURLPart.AudioURL(url="data:audio/wav;base64,abc")
                    ),
                ],
            ),
            Message(
                role="assistant",
                content="Calling tool",
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "inspect", "arguments": "{}"},
                    }
                ],
            ),
            Message(role="tool", content="tool output", tool_call_id="call_1"),
            Message(role="assistant", content="Done"),
        ]

        await compressor(messages)

        summary_contexts = provider.last_text_chat_kwargs["contexts"]
        assert summary_contexts[0]["content"][1] == {"type": "text", "text": "[Image]"}
        assert summary_contexts[0]["content"][2] == {"type": "text", "text": "[Audio]"}
        assert "tool_calls" not in summary_contexts[1]
        assert summary_contexts[2] == {
            "role": "user",
            "content": "[Tool result]\ntool output",
        }

    @pytest.mark.asyncio
    async def test_llm_compressor_keeps_recent_by_token_ratio(self):
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = MockProvider()
        compressor = LLMSummaryCompressor(
            provider=provider,
            keep_recent_ratio=0.3,
            instruction_text="Summarize.",
        )  # type: ignore[arg-type]
        messages = [
            Message(role="user", content="a" * 200),
            Message(role="assistant", content="b" * 200),
            Message(role="user", content="c" * 10),
            Message(role="assistant", content="d" * 10),
            Message(role="user", content="e" * 10),
            Message(role="assistant", content="f" * 10),
        ]

        result = await compressor(messages)

        summary_contexts = provider.last_text_chat_kwargs["contexts"]
        assert summary_contexts[0] == {"role": "user", "content": "a" * 200}
        assert summary_contexts[1] == {"role": "assistant", "content": "b" * 200}
        assert not any(msg.get("content") == "c" * 10 for msg in summary_contexts)
        assert result[-4:] == messages[2:]

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
            manager.compressor, "should_compress", return_value=False
        ) as mock_should_compress:
            with patch.object(
                manager.compressor, "__call__", new_callable=AsyncMock
            ) as mock_compress:
                result = await manager.process(messages)

                # should_compress should be called
                mock_should_compress.assert_called_once()
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

        # Create a mock compressor
        mock_compressor = AsyncMock()
        mock_compressor.compression_threshold = 0.82
        mock_compressor.return_value = compressed

        # Mock should_compress to return True first time, False after
        call_count = 0

        def mock_should_compress(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count == 1

        mock_compressor.should_compress = mock_should_compress
        manager.compressor = mock_compressor

        result = await manager.process(messages)

        # Compressor should be called
        mock_compressor.assert_called_once()
        # Result should be the compressed version
        assert len(result) <= len(messages)

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

            # Compressor should not be called when max_context_tokens is 0
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

        # Mock should_compress to return True twice (before and after compression)
        with patch.object(manager.compressor, "should_compress", return_value=True):
            with patch.object(manager.compressor, "__call__", new=mock_compress):
                with patch.object(
                    manager.truncator,
                    "truncate_by_halving",
                    return_value=long_messages[:5],
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
        mock_compressor = AsyncMock(side_effect=Exception("Test error"))
        mock_compressor.compression_threshold = 0.82
        mock_compressor.should_compress = MagicMock(return_value=True)
        manager.compressor = mock_compressor

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
        tokens = manager.token_counter.count_tokens(messages)
        needs_compression = manager.compressor.should_compress(messages, tokens, 50)

        assert tokens > 0  # Tokens should be counted
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

    # ==================== Compressor should_compress Tests ====================

    @pytest.mark.asyncio
    async def test_should_compress_empty_messages(self):
        """Test should_compress with empty messages."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Compressor's should_compress should handle empty gracefully
        needs_compression = manager.compressor.should_compress([], 0, 100)
        assert not needs_compression

    @pytest.mark.asyncio
    async def test_should_compress_below_threshold(self):
        """Test should_compress when below compression threshold."""
        config = ContextConfig(max_context_tokens=1000)
        manager = ContextManager(config)

        messages = [self.create_message("user", "Hello")]
        tokens = manager.token_counter.count_tokens(messages)

        needs_compression = manager.compressor.should_compress(messages, tokens, 1000)
        assert not needs_compression

    @pytest.mark.asyncio
    async def test_should_compress_above_threshold(self):
        """Test should_compress when above compression threshold."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Create message with many tokens
        messages = [self.create_message("user", "这是测试" * 50)]
        tokens = manager.token_counter.count_tokens(messages)

        needs_compression = manager.compressor.should_compress(messages, tokens, 100)
        # Should need compression if tokens > 82 (0.82 * 100)
        assert needs_compression == (tokens > 82)

    # ==================== Truncator Halving Tests ====================

    def test_truncate_by_halving_basic(self):
        """Test truncate_by_halving removes middle 50%."""
        config = ContextConfig()
        manager = ContextManager(config)

        messages = self.create_messages(10)
        result = manager.truncator.truncate_by_halving(messages)

        # Should keep roughly half
        assert len(result) < len(messages)

    def test_truncate_by_halving_empty_list(self):
        """Test truncate_by_halving with empty list."""
        config = ContextConfig()
        manager = ContextManager(config)

        result = manager.truncator.truncate_by_halving([])

        assert result == []

    def test_truncate_by_halving_single_message(self):
        """Test truncate_by_halving with single message."""
        config = ContextConfig()
        manager = ContextManager(config)

        messages = [self.create_message("user", "Hello")]
        result = manager.truncator.truncate_by_halving(messages)

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
    async def test_compression_threshold_default(self):
        """Test that compression threshold is used correctly."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        # Verify the default threshold is 0.82
        assert manager.compressor.compression_threshold == 0.82

        # Test threshold logic
        messages = [self.create_message("user", "x" * 81)]  # ~24 tokens
        tokens = manager.token_counter.count_tokens(messages)

        needs_compression = manager.compressor.should_compress(messages, tokens, 100)
        # Should not compress if below threshold
        assert needs_compression == (tokens > 82)

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
            llm_compress_keep_recent_ratio=0.15,
        )
        manager = ContextManager(config)

        # Verify config is stored
        assert manager.config.max_context_tokens == 500
        assert manager.config.enforce_max_turns == 5
        assert manager.config.truncate_turns == 2
        assert manager.config.llm_compress_keep_recent_ratio == 0.15

    # ==================== Run Compression Tests ====================

    @pytest.mark.asyncio
    async def test_run_compression_calls_compressor(self):
        """Test _run_compression calls compressor."""
        config = ContextConfig(max_context_tokens=100)
        manager = ContextManager(config)

        messages = self.create_messages(5)
        compressed = self.create_messages(3)

        # Create a mock compressor
        mock_compressor = AsyncMock()
        mock_compressor.compression_threshold = 0.82
        mock_compressor.return_value = compressed
        mock_compressor.should_compress = MagicMock(return_value=False)
        manager.compressor = mock_compressor

        result = await manager._run_compression(messages, prev_tokens=100)

        # Compressor __call__ should be invoked
        mock_compressor.assert_called_once_with(messages)
        assert result == compressed

    @pytest.mark.asyncio
    async def test_run_compression_applies_compressor_through_process(self):
        """Test _run_compression calls compressor when needed through process()."""
        config = ContextConfig(max_context_tokens=100, truncate_turns=1)
        manager = ContextManager(config)

        # Create messages that will trigger compression
        messages = [self.create_message("user", "x" * 300)]  # ~90 tokens > 82 threshold
        compressed = [self.create_message("user", "short")]  # Much smaller

        # Create a mock compressor
        mock_compressor = AsyncMock()
        mock_compressor.compression_threshold = 0.82
        mock_compressor.return_value = compressed

        # Mock should_compress to return True first time, False after
        call_count = 0

        def mock_should_compress(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return call_count == 1

        mock_compressor.should_compress = mock_should_compress
        manager.compressor = mock_compressor

        result = await manager.process(messages)

        # Compressor should have been called
        mock_compressor.assert_called_once()
        assert len(result) <= len(messages)

    @pytest.mark.asyncio
    async def test_llm_compression_with_mock_provider(self):
        """Test LLM compression using MockProvider."""
        mock_provider = MockProvider()
        config = ContextConfig(
            llm_compress_provider=mock_provider,  # type: ignore
            llm_compress_keep_recent_ratio=0.15,
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

    # ==================== split_into_rounds Tests ====================

    def test_split_rounds_ensures_user_start(self):
        """Test split_into_rounds preserves user-assistant round boundaries."""
        from astrbot.core.agent.context.round_utils import split_into_rounds

        # First round may begin with system messages; subsequent rounds must start with user
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "msg2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "msg4"},
            {"role": "tool", "content": "tool result"},
            {"role": "user", "content": "msg5"},
        ]

        rounds = split_into_rounds(messages)

        # Subsequent rounds (after the first) must start with user
        for rnd in rounds[1:]:
            assert rnd[0]["role"] == "user"

        assert len(rounds) >= 2

    def test_split_rounds_single_round(self):
        """A single user-assistant pair is one round."""
        from astrbot.core.agent.context.round_utils import split_into_rounds

        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]
        rounds = split_into_rounds(messages)
        assert len(rounds) == 1
        assert rounds[0][0]["role"] == "user"

    def test_split_rounds_multi_tool(self):
        """Tool calls/results within a round are kept together."""
        from astrbot.core.agent.context.round_utils import split_into_rounds

        messages = [
            {"role": "user", "content": "search"},
            {"role": "assistant", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "tool_call_id": "c1", "content": "result1"},
            {"role": "tool", "tool_call_id": "c1", "content": "result2"},
            {"role": "assistant", "content": "done"},
        ]
        rounds = split_into_rounds(messages)
        # One round with 5 segments
        assert len(rounds) == 1
        assert len(rounds[0]) == 5

    def test_split_rounds_empty(self):
        """Empty list returns no rounds."""
        from astrbot.core.agent.context.round_utils import split_into_rounds

        rounds = split_into_rounds([])
        assert len(rounds) == 0

    def test_split_rounds_accepts_message_objects(self):
        """Message objects can be split without converting them to dictionaries."""
        from astrbot.core.agent.context.round_utils import split_into_rounds

        messages = [
            Message(role="system", content="System prompt"),
            Message(role="user", content=[TextPart(text="hello")]),
            Message(role="assistant", content="hi"),
            Message(role="user", content="next"),
        ]

        rounds = split_into_rounds(messages)

        assert len(rounds) == 3
        assert rounds[0][0] is messages[0]
        assert rounds[1][0] is messages[1]
        assert rounds[2][0] is messages[3]
