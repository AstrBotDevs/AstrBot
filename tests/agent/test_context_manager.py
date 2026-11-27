"""Comprehensive tests for ContextManager."""

import math
import sys
from pathlib import Path
from typing import Literal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add parent directory to path to avoid circular import issues
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from astrbot.core.agent.context.config import ContextConfig
from astrbot.core.agent.context.manager import ContextManager
from astrbot.core.agent.context.token_counter import EstimateTokenCounter
from astrbot.core.agent.message import (
    AudioURLPart,
    ImageURLPart,
    Message,
    TextPart,
    ThinkPart,
    ToolCall,
)
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from astrbot.core.provider.sources.request_retry import retry_provider_request


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


class FailingProvider(MockProvider):
    """Provider whose summary request always fails."""

    async def text_chat(self, **kwargs):
        self.last_text_chat_kwargs = kwargs
        raise RuntimeError("summary model unavailable")


class QuotaExhaustedError(Exception):
    status_code = 429


class RateLimitedProvider(MockProvider):
    """Provider that goes through the real retry helper and always gets a 429."""

    def __init__(self):
        super().__init__()
        self.attempts = 0

    async def text_chat(self, **kwargs):
        async def request():
            self.attempts += 1
            raise QuotaExhaustedError("quota exhausted")

        return await retry_provider_request(
            "summary",
            request,
            max_attempts=kwargs.get("request_max_retries"),
        )


class CharTokenCounter:
    """Counts one token per character of text content."""

    def count_tokens(self, messages, trusted_token_usage: int = 0) -> int:
        return sum(len(m.content) for m in messages if isinstance(m.content, str))


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
            return_value=LLMResponse(
                role="assistant", completion_text="  ", usage=TokenUsage(output=3)
            )
        )
        sink = AsyncMock()
        compressor = LLMSummaryCompressor(
            provider=provider, keep_recent_ratio=0.15, request_event_emitter=sink
        )  # type: ignore[arg-type]
        messages = self.create_messages(6)

        with patch("astrbot.core.agent.context.compressor.logger") as mock_logger:
            result = await compressor(messages)

        assert result == messages
        mock_logger.warning.assert_called_once_with(
            "LLM context compression returned an empty summary."
        )

        recorded = sink.await_args.args[0]
        assert recorded.type == "message.appended"
        assert recorded.data["purpose"] == "compaction"
        assert recorded.data["status"] == "completed"
        assert recorded.data["message"]["_no_save"] is True
        assert recorded.data["usage"]["output_tokens"] == 3

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
    async def test_trusted_usage_triggers_compression_before_provider_call(self):
        config = ContextConfig(max_context_tokens=100, truncate_turns=1)
        manager = ContextManager(config)
        messages = [self.create_message("user", "short")]
        compressed = [self.create_message("user", "compressed")]
        mock_compressor = AsyncMock(return_value=compressed)
        mock_compressor.should_compress = MagicMock(side_effect=[True, False])
        manager.compressor = mock_compressor

        result = await manager.process(messages, trusted_token_usage=83)

        first_check = mock_compressor.should_compress.call_args_list[0]
        assert first_check.args == (messages, 83, 100)
        mock_compressor.assert_awaited_once_with(messages)
        assert result == compressed

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

    def _rounds_with_tool_chain(self, latest_request: str) -> list[Message]:
        """System prompt, a long first round, a round with a tool chain, and
        the latest request. One token per character with ``CharTokenCounter``."""
        return [
            self.create_message("system", "s" * 10),
            self.create_message("user", "a" * 300),
            self.create_message("assistant", "b" * 300),
            self.create_message("user", "c" * 50),
            Message(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        function=ToolCall.FunctionBody(name="lookup", arguments="{}"),
                    )
                ],
            ),
            Message(role="tool", content="d" * 100, tool_call_id="call_1"),
            self.create_message("assistant", "e" * 50),
            self.create_message("user", latest_request),
        ]

    @pytest.mark.asyncio
    async def test_failed_summary_drops_oldest_rounds_until_within_limit(self):
        """When the summary fails, whole rounds are dropped until the context fits."""
        provider = FailingProvider()
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=provider,  # type: ignore[arg-type]
            custom_token_counter=CharTokenCounter(),
        )
        manager = ContextManager(config)
        messages = self._rounds_with_tool_chain("f" * 20)

        result = await manager.process(messages)

        assert provider.last_text_chat_kwargs["request_max_retries"] == 1
        # Dropping the first round (600 tokens) is enough to get under 820, so
        # the round with the tool chain stays intact.
        assert result == [messages[0], *messages[3:]]

    @pytest.mark.asyncio
    async def test_fallback_keeps_latest_round_when_it_alone_exceeds_limit(
        self, caplog
    ):
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
            custom_token_counter=CharTokenCounter(),
        )
        manager = ContextManager(config)
        messages = self._rounds_with_tool_chain("f" * 900)

        result = await manager.process(messages)

        assert result == [messages[0], messages[-1]]
        assert "only the latest round left" in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("summary", [False, True])
    async def test_token_fallback_keeps_internal_notice_with_oversized_request(
        self, summary
    ):
        """The last internal notice cannot replace the active request in fallback."""
        from astrbot.core.agent.message import dump_messages, load_messages

        original = self._rounds_with_tool_chain("f" * 900)
        messages = load_messages(
            dump_messages(original)
            + [
                {"role": "assistant", "content": "Working"},
                {
                    "role": "user",
                    "content": "Internal notice",
                    "_turn_continuation": True,
                },
            ]
        )
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=FailingProvider() if summary else None,
            custom_token_counter=CharTokenCounter(),
        )

        result = await ContextManager(config).process(messages)

        assert result == [messages[0], *messages[-3:]]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("summary", [False, True])
    @pytest.mark.parametrize("custom_counter", [False, True])
    @pytest.mark.parametrize("oversized_latest", [False, True])
    async def test_fallback_preserves_mixed_rounds_and_custom_token_counts(
        self, summary, custom_counter, oversized_latest
    ):
        """Keep whole tool rounds and honor non-additive custom token counters."""

        class RequestOverheadCounter(EstimateTokenCounter):
            def count_tokens(self, messages, trusted_token_usage=0):
                return super().count_tokens(messages, trusted_token_usage) + 1000

        counter = RequestOverheadCounter() if custom_counter else EstimateTokenCounter()
        original = self._rounds_with_tool_chain(
            "f" * (5000 if oversized_latest else 20)
        )
        messages = [
            original[0],
            Message(
                role="user",
                content=[
                    TextPart(text="old context 中文 😀" * 1000),
                    ImageURLPart(
                        image_url=ImageURLPart.ImageURL(
                            url="https://example.com/image.png"
                        )
                    ),
                    AudioURLPart(
                        audio_url=AudioURLPart.AudioURL(
                            url="https://example.com/audio.wav"
                        )
                    ),
                ],
            ),
            Message(role="assistant", content=[ThinkPart(think="old reasoning" * 100)]),
            *original[1:],
        ]
        before = [message.model_dump() for message in messages]
        expected = (
            [messages[0], messages[-1]]
            if oversized_latest
            else [original[0], *original[3:]]
        )
        config = ContextConfig(
            max_context_tokens=(
                100
                if oversized_latest
                else math.ceil(counter.count_tokens(expected) / 0.82)
            ),
            llm_compress_provider=FailingProvider() if summary else None,  # type: ignore[arg-type]
            custom_token_counter=counter if custom_counter else None,
        )

        result = await ContextManager(config).process(messages)

        assert result == expected
        assert [message.model_dump() for message in messages] == before

    @pytest.mark.asyncio
    async def test_llm_summary_is_requested_once(self):
        """A failed summary falls back to truncation instead of being retried."""
        from astrbot.core.agent.context.compressor import LLMSummaryCompressor

        provider = RateLimitedProvider()
        compressor = LLMSummaryCompressor(provider=provider, keep_recent_ratio=0.15)  # type: ignore[arg-type]
        messages = self._rounds_with_tool_chain("f" * 20)

        result = await compressor(messages)

        assert result is messages
        assert provider.attempts == 1

    @pytest.mark.asyncio
    async def test_custom_compressor_receives_matching_history_and_token_count(self):
        """Custom compression checks must see the current retained messages."""
        from astrbot.core.agent.context.compressor import TruncateByTurnsCompressor

        counter = EstimateTokenCounter()

        class InspectingCompressor(TruncateByTurnsCompressor):
            async def __call__(self, messages):
                return messages

            def should_compress(self, messages, current_tokens, max_tokens):
                assert current_tokens == counter.count_tokens(messages)
                return super().should_compress(messages, current_tokens, max_tokens)

        messages = self._rounds_with_tool_chain("latest request")
        before = [message.model_dump() for message in messages]
        manager = ContextManager(
            ContextConfig(
                max_context_tokens=100, custom_compressor=InspectingCompressor()
            )
        )

        result = await manager.process(messages)

        assert result == [messages[0], messages[-1]]
        assert [message.model_dump() for message in messages] == before

    # ==================== Trusted Usage Calibration & No-Op Fallback Tests ====================

    def _underestimated_multi_round_history(self) -> list[Message]:
        """Build a multi-round history whose heuristic estimate is below threshold.

        With ``EstimateTokenCounter``, total heuristic tokens are ~730 (< 820
        for ``max_context_tokens=1000``), reproducing the real-world regime
        where ``trusted_token_usage`` exceeds the compression threshold while
        uncalibrated heuristic recounts fall below it.

        Returns:
            Message list containing a system message, five older rounds
            (including one tool-call round), and a latest active user round.
        """
        return [
            self.create_message("system", "s" * 100),  # 30
            # Round 0: 120 tokens
            self.create_message("user", "a" * 200),
            self.create_message("assistant", "b" * 200),
            # Round 1: 120 tokens
            self.create_message("user", "c" * 200),
            self.create_message("assistant", "d" * 200),
            # Round 2 (tool chain): 30 + tool_call(~25) + 30 + 30 ≈ 115 tokens
            self.create_message("user", "e" * 100),
            Message(
                role="assistant",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        function=ToolCall.FunctionBody(name="lookup", arguments="{}"),
                    )
                ],
            ),
            Message(role="tool", content="f" * 100, tool_call_id="call_1"),
            self.create_message("assistant", "g" * 100),
            # Round 3: 120 tokens
            self.create_message("user", "h" * 200),
            self.create_message("assistant", "i" * 200),
            # Round 4: 120 tokens
            self.create_message("user", "j" * 200),
            self.create_message("assistant", "k" * 200),
            # Round 5 (latest active request): 105 tokens
            self.create_message("user", "z" * 350),
        ]

    @pytest.mark.asyncio
    async def test_failed_llm_summary_with_trusted_usage_underestimate_falls_back_to_truncation(
        self, caplog
    ):
        """Failed LLM compression must still truncate oldest rounds when
        ``trusted_token_usage`` exceeds the limit even if the heuristic does not.
        """
        provider = FailingProvider()
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=provider,  # type: ignore[arg-type]
        )
        manager = ContextManager(config)
        messages = self._underestimated_multi_round_history()
        est_before = manager.token_counter.count_tokens(messages)
        trusted_usage = 989  # 98.9% > 82%, mirroring ~1.037M / 1.048M

        assert est_before < 820  # uncalibrated heuristic sits below 82% threshold

        with caplog.at_level("INFO"):
            result = await manager.process(messages, trusted_token_usage=trusted_usage)

        # Dropping only Round 0 leaves calibrated tokens > 820; dropping Round 0
        # and Round 1 brings calibrated tokens <= 820 while keeping the tool chain.
        expected = [messages[0], *messages[5:]]
        est_after_one_drop = manager.token_counter.count_tokens(
            [messages[0], *messages[3:]]
        )
        est_after_two_drops = manager.token_counter.count_tokens(expected)
        assert math.ceil(est_after_one_drop * trusted_usage / est_before) > 820
        assert math.ceil(est_after_two_drops * trusted_usage / est_before) <= 820

        assert result == expected
        assert "Compression made no changes" in caplog.text
        assert "Compress completed" not in caplog.text
        assert "Dropped 2 oldest round(s)." in caplog.text

    @pytest.mark.asyncio
    @pytest.mark.parametrize("failure_mode", ["empty_summary", "err_role"])
    async def test_noop_llm_summary_responses_with_trusted_usage_fall_back_to_truncation(
        self, failure_mode
    ):
        """Empty or error-role summary responses must also trigger fallback truncation."""
        provider = MockProvider()
        if failure_mode == "empty_summary":
            provider.text_chat = AsyncMock(
                return_value=LLMResponse(role="assistant", completion_text="   ")
            )
        else:
            provider.text_chat = AsyncMock(
                return_value=LLMResponse(
                    role="err", completion_text="503 Service Unavailable"
                )
            )
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=provider,  # type: ignore[arg-type]
        )
        manager = ContextManager(config)
        messages = self._underestimated_multi_round_history()

        result = await manager.process(messages, trusted_token_usage=989)

        assert result == [messages[0], *messages[5:]]

    @pytest.mark.asyncio
    async def test_successful_llm_summary_with_trusted_usage_reflects_real_reduction(
        self, caplog
    ):
        """Successful compression scales down cleanly without unnecessary truncation."""
        provider = MockProvider()
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=provider,  # type: ignore[arg-type]
            llm_compress_keep_recent_ratio=0.15,
        )
        manager = ContextManager(config)
        messages = self._underestimated_multi_round_history()

        with caplog.at_level("INFO"):
            result = await manager.process(messages, trusted_token_usage=989)

        assert result[0] is messages[0]
        assert result[-1] is messages[-1]
        assert any(
            isinstance(m.content, str) and "Summary of conversation" in m.content
            for m in result
        )
        assert "Compress completed" in caplog.text
        assert "dropping the oldest rounds" not in caplog.text

    @pytest.mark.asyncio
    async def test_successful_llm_summary_still_above_calibrated_limit_truncates(self):
        """Even when summarization succeeds, fallback truncation runs if the
        calibrated post-summary token count still exceeds the threshold.
        """
        provider = MockProvider()
        # Produce a verbose summary (~510 heuristic tokens) so raw post-summary
        # estimate (~650) sits below 820 while calibrated count (~880) exceeds 820.
        provider.text_chat = AsyncMock(
            return_value=LLMResponse(role="assistant", completion_text="w" * 1700)
        )
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=provider,  # type: ignore[arg-type]
            llm_compress_keep_recent_ratio=0.0,
        )
        manager = ContextManager(config)
        messages = self._underestimated_multi_round_history()

        result = await manager.process(messages, trusted_token_usage=989)

        # Fallback drops the oversized summary round and keeps [system, latest].
        assert result == [messages[0], messages[-1]]

    @pytest.mark.asyncio
    async def test_truncate_by_turns_compressor_with_trusted_usage_continues_to_calibrated_limit(
        self,
    ):
        """TruncateByTurnsCompressor dropping 1 round must keep truncating until
        calibrated tokens fall below the compression threshold.
        """
        config = ContextConfig(max_context_tokens=1000, truncate_turns=1)
        manager = ContextManager(config)
        messages = [
            self.create_message("system", "s" * 100),  # 30
            *[
                msg
                for _ in range(10)
                for msg in (
                    self.create_message("user", "u" * 110),  # 33
                    self.create_message("assistant", "a" * 110),  # 33
                )
            ],
        ]
        # est_before = 30 + 10 * 66 = 690 (< 820), trusted_usage = 980 (> 820).
        # TruncateByTurnsCompressor drops 1 turn -> 9 rounds left (est=624, cal=887 > 820).
        # Fallback drops 1 more round -> 8 rounds left (est=558, cal=793 <= 820).
        est_before = manager.token_counter.count_tokens(messages)
        assert est_before == 690

        result = await manager.process(messages, trusted_token_usage=980)

        assert result == [messages[0], *messages[5:]]

    @pytest.mark.asyncio
    async def test_noop_copy_compressor_and_custom_counter_calibrate_in_non_incremental_loop(
        self,
    ):
        """Non-incremental fallback path must detect copy no-ops and calibrate every recount."""
        from astrbot.core.agent.context.compressor import TruncateByTurnsCompressor

        class SubclassCounter(EstimateTokenCounter):
            pass

        class CopyNoOpCompressor(TruncateByTurnsCompressor):
            async def __call__(self, messages):
                return [msg.model_copy(deep=True) for msg in messages]

        messages = self._underestimated_multi_round_history()
        incremental_manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
            )
        )
        non_incremental_manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                custom_token_counter=SubclassCounter(),
                custom_compressor=CopyNoOpCompressor(),
            )
        )

        incremental_result = await incremental_manager.process(
            messages, trusted_token_usage=989
        )
        non_incremental_result = await non_incremental_manager.process(
            messages, trusted_token_usage=989
        )

        assert non_incremental_result == incremental_result
        assert non_incremental_result == [messages[0], *messages[5:]]

    @pytest.mark.asyncio
    async def test_noop_compression_with_zero_estimate_and_trusted_usage(self, caplog):
        """When heuristic estimate is 0 but trusted usage exceeds the limit,
        failed compression still falls back to dropping oldest rounds down to
        the latest round.
        """
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
        )
        manager = ContextManager(config)
        messages = [
            self.create_message("system", "sys"),
            self.create_message("user", "hi"),
            self.create_message("assistant", "ok"),
            self.create_message("user", "yo"),
            self.create_message("assistant", "ok"),
            self.create_message("user", "go"),
        ]
        assert manager.token_counter.count_tokens(messages) == 0

        with caplog.at_level("WARNING"):
            result = await manager.process(messages, trusted_token_usage=950)

        assert result == [messages[0], messages[-1]]
        assert "only the latest round left" in caplog.text

    @pytest.mark.asyncio
    async def test_trusted_usage_edge_cases_empty_single_round_and_zero_limit(
        self, caplog
    ):
        """Verify empty history, single-round history, and max_context_tokens=0."""
        # 1. Empty messages with trusted_token_usage > 0
        manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
            )
        )
        assert await manager.process([], trusted_token_usage=950) == []

        # 2. Single-round conversation (only latest active request) stays intact
        single_round = [
            self.create_message("system", "s" * 100),
            self.create_message("user", "u" * 200),
        ]
        with caplog.at_level("WARNING"):
            result = await manager.process(single_round, trusted_token_usage=950)
        assert result == single_round
        assert "only the latest round left" in caplog.text

        # 3. max_context_tokens == 0 skips compression even with high trusted usage
        provider = FailingProvider()
        unlimited_manager = ContextManager(
            ContextConfig(
                max_context_tokens=0,
                llm_compress_provider=provider,  # type: ignore[arg-type]
            )
        )
        multi_round = self._underestimated_multi_round_history()
        assert (
            await unlimited_manager.process(multi_round, trusted_token_usage=999_999)
            == multi_round
        )
        assert provider.last_text_chat_kwargs is None

    @pytest.mark.asyncio
    async def test_calibration_boundary_precision_avoids_float_truncation_skip(self):
        """At 1 token above threshold (821 / 1000), exact integer calibration
        must not lose precision and falsely skip fallback truncation.
        """
        config = ContextConfig(
            max_context_tokens=1000,
            llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
        )
        manager = ContextManager(config)
        # Prime heuristic total (29 tokens) where float `29 * (821 / 29)` can drift.
        messages = [
            self.create_message("user", "a" * 34),  # 10 tokens
            self.create_message("assistant", "b" * 34),  # 10 tokens
            self.create_message("user", "c" * 30),  # 9 tokens
        ]
        assert manager.token_counter.count_tokens(messages) == 29

        result = await manager.process(messages, trusted_token_usage=821)

        assert result == [messages[-1]]

    @pytest.mark.asyncio
    async def test_inplace_mutating_custom_compressor_is_not_misclassified_as_noop(
        self, caplog
    ):
        """A custom compressor that mutates the list in place must be recognized
        as having compressed the context rather than treated as a no-op.
        """
        from astrbot.core.agent.context.compressor import TruncateByTurnsCompressor

        class InPlaceCompressor(TruncateByTurnsCompressor):
            async def __call__(self, messages):
                del messages[1:9]
                return messages

        manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                custom_compressor=InPlaceCompressor(),
            )
        )
        messages = self._underestimated_multi_round_history()
        expected = [messages[0], *messages[9:]]

        with caplog.at_level("INFO"):
            result = await manager.process(messages, trusted_token_usage=989)

        assert result == expected
        assert "Compress completed" in caplog.text
        assert "Compression made no changes" not in caplog.text
        assert "dropping the oldest rounds" not in caplog.text

    @pytest.mark.asyncio
    async def test_zero_pre_estimate_positive_post_estimate_still_triggers_fallback(
        self,
    ):
        """When pre-compression estimate is 0 and trusted usage exceeds limit,
        a positive post-compression estimate below threshold must not bypass
        fallback truncation.
        """
        from astrbot.core.agent.context.compressor import TruncateByTurnsCompressor

        class GrowingContentCompressor(TruncateByTurnsCompressor):
            async def __call__(self, messages):
                return [
                    messages[0],
                    self.create_message("user", "a" * 20),
                    messages[2],
                    messages[3],
                    messages[4],
                    messages[5],
                ]

            @staticmethod
            def create_message(role: str, content: str) -> Message:
                return Message(role=role, content=content)

        manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                custom_compressor=GrowingContentCompressor(),
            )
        )
        messages = [
            self.create_message("system", "sys"),
            self.create_message("user", "hi"),
            self.create_message("assistant", "ok"),
            self.create_message("user", "yo"),
            self.create_message("assistant", "ok"),
            self.create_message("user", "go"),
        ]
        assert manager.token_counter.count_tokens(messages) == 0

        result = await manager.process(messages, trusted_token_usage=950)

        assert result == [messages[0], messages[-1]]

    @pytest.mark.asyncio
    async def test_fixed_overhead_tokens_are_not_scaled_away_during_fallback(self):
        """Fixed request overhead (such as tool schemas) must remain accounted
        for while dropping rounds so fallback does not stop prematurely.
        """
        manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
            )
        )
        messages = [
            self.create_message("user", "a" * 100),  # 30
            self.create_message("assistant", "b" * 100),  # 30 (round 0: 60)
            self.create_message("user", "c" * 100),  # 30
            self.create_message("assistant", "d" * 100),  # 30 (round 1: 60)
            self.create_message("user", "e" * 100),  # 30
            self.create_message("assistant", "f" * 100),  # 30 (round 2: 60)
            self.create_message("user", "g" * 100),  # 30 (round 3: 30)
        ]
        # est_before = 210, fixed_overhead = 500 -> est_total_before = 710.
        # With trusted_token_usage = 950:
        # - Without fixed overhead, dropping 1 round (210 -> 150) scales to
        #   ceil(150 * 950 / 210) = 679 <= 820 and stops prematurely.
        # - With fixed_overhead_tokens = 500:
        #   1 drop (150 + 500 = 650): ceil(650 * 950 / 710) = 870 > 820
        #   2 drops (90 + 500 = 590): ceil(590 * 950 / 710) = 790 <= 820
        assert manager.token_counter.count_tokens(messages) == 210

        result = await manager.process(
            messages,
            trusted_token_usage=950,
            fixed_overhead_tokens=500,
        )

        assert result == messages[4:]

    @pytest.mark.asyncio
    async def test_fixed_overhead_when_trusted_usage_within_est_plus_fixed(self):
        """When trusted_token_usage sits between est_before and est_before + fixed,
        the excess stays fixed instead of shrinking with dropped rounds.
        """
        manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
            )
        )
        messages = [
            self.create_message("user", "a" * 200),  # 60
            self.create_message("assistant", "b" * 200),  # 60 (round 0: 120)
            self.create_message("user", "c" * 200),  # 60
            self.create_message("assistant", "d" * 200),  # 60 (round 1: 120)
            self.create_message("user", "e" * 200),  # 60
            self.create_message("assistant", "f" * 200),  # 60 (round 2: 120)
            self.create_message("user", "g" * 200),  # 60 (round 3: 60)
        ]
        # est_before = 420, fixed = 550, trusted_usage = 950 (<= 420 + 550 = 970).
        # Effective fixed excess = 950 - 420 = 530.
        # 1 drop (300 + 530 = 830 > 820); 2 drops (180 + 530 = 710 <= 820).
        assert manager.token_counter.count_tokens(messages) == 420

        result = await manager.process(
            messages,
            trusted_token_usage=950,
            fixed_overhead_tokens=550,
        )

        assert result == messages[4:]

    @pytest.mark.asyncio
    async def test_enforce_max_turns_recalibrates_stale_trusted_usage(self):
        """History trimmed by enforce_max_turns must recalibrate trusted_token_usage
        so valid recent rounds are not dropped by stale pre-trim usage.
        """
        provider = FailingProvider()
        manager = ContextManager(
            ContextConfig(
                enforce_max_turns=2,
                truncate_turns=1,
                max_context_tokens=1000,
                llm_compress_provider=provider,  # type: ignore[arg-type]
            )
        )
        messages = [
            self.create_message("system", "s" * 100),  # 30
            *[
                msg
                for idx in range(6)
                for msg in (
                    self.create_message("user", f"u{idx}" + "x" * 160),  # ~48
                    self.create_message("assistant", f"a{idx}" + "y" * 160),  # ~48
                )
            ],
        ]
        # Original 6 turns ~ 610 heuristic tokens; enforce_max_turns=2 retains
        # system + 2 turns (~224 tokens). Calibrating trusted_token_usage=950
        # yields ~350 <= 820, so compression is skipped and both turns survive.
        result = await manager.process(messages, trusted_token_usage=950)

        assert result == [messages[0], *messages[-4:]]
        assert provider.last_text_chat_kwargs is None

    @pytest.mark.asyncio
    async def test_inplace_message_mutation_same_estimate_is_not_noop(self, caplog):
        """A custom compressor mutating a Message in place with the same
        heuristic token estimate must not be misclassified as a no-op.
        """
        from astrbot.core.agent.context.compressor import TruncateByTurnsCompressor

        class InPlaceContentMutator(TruncateByTurnsCompressor):
            async def __call__(self, messages):
                messages[1].content = "z" * len(str(messages[1].content))
                return messages

        manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                custom_compressor=InPlaceContentMutator(),
            )
        )
        messages = [
            self.create_message("system", "s" * 100),
            self.create_message("user", "a" * 300),
            self.create_message("assistant", "b" * 300),
            self.create_message("user", "c" * 300),
        ]

        with caplog.at_level("INFO"):
            await manager.process(messages, trusted_token_usage=950)

        assert "Compress completed" in caplog.text
        assert "Compression made no changes" not in caplog.text

    @pytest.mark.asyncio
    async def test_zero_recount_after_drop_does_not_stop_fallback_early(self, caplog):
        """When a positive pre-compression estimate drops to 0 while multiple
        older rounds remain, fallback truncation must continue down to the
        latest round rather than stopping early at 0 tokens.
        """
        manager = ContextManager(
            ContextConfig(
                max_context_tokens=1000,
                llm_compress_provider=FailingProvider(),  # type: ignore[arg-type]
            )
        )
        messages = [
            self.create_message("system", "sys"),  # 0
            self.create_message("user", "a" * 34),  # 10
            self.create_message("assistant", "b" * 34),  # 10 (round 0: 20)
            self.create_message("user", "hi"),  # 0
            self.create_message("assistant", "ok"),  # 0 (round 1: 0)
            self.create_message("user", "yo"),  # 0
            self.create_message("assistant", "ok"),  # 0 (round 2: 0)
            self.create_message("user", "go"),  # 0 (round 3: 0)
        ]
        # est_before = 20 (> 0), trusted_token_usage = 950.
        # After dropping round 0, raw_tokens == 0 while rounds 1, 2, 3 remain.
        # Unmeasured gap = 950 - 20 = 930 > 820 -> must keep dropping rounds 1 & 2.
        assert manager.token_counter.count_tokens(messages) == 20

        with caplog.at_level("WARNING"):
            result = await manager.process(messages, trusted_token_usage=950)

        assert result == [messages[0], messages[-1]]
        assert "only the latest round left" in caplog.text

    @pytest.mark.asyncio
    async def test_tool_loop_runner_passes_tool_schema_fixed_overhead_to_context_manager(
        self,
    ):
        """ToolLoopAgentRunner passes estimated tool-schema overhead to
        ContextManager.process when trusted token usage and max context are set.
        """
        from unittest.mock import MagicMock

        from astrbot.core.agent.hooks import BaseAgentRunHooks
        from astrbot.core.agent.run_context import ContextWrapper
        from astrbot.core.agent.runners.tool_loop_agent_runner import (
            ToolLoopAgentRunner,
        )
        from astrbot.core.agent.tool import FunctionTool, ToolSet
        from astrbot.core.provider.entities import ProviderRequest

        class EchoTool(FunctionTool):
            def __init__(self) -> None:
                super().__init__(
                    name="verbose_schema_tool",
                    description="D" * 2000,
                    parameters={
                        "type": "object",
                        "properties": {
                            "payload": {"type": "string", "description": "P" * 1000}
                        },
                    },
                )

            async def call(self, context, **kwargs):
                return "ok"

        provider = MagicMock()
        provider.provider_config = {"id": "p1", "max_context_tokens": 10000}
        provider.meta = MagicMock(return_value=MagicMock(model="test-model"))
        provider.get_model = MagicMock(return_value="test-model")
        provider.text_chat = AsyncMock(
            return_value=LLMResponse(role="assistant", completion_text="done")
        )
        provider.text_chat_stream = MagicMock()

        conversation = MagicMock()
        conversation.token_usage = 9000
        req = ProviderRequest(
            prompt="hello",
            conversation=conversation,
            func_tool=ToolSet([EchoTool()]),
        )
        runner = ToolLoopAgentRunner()
        await runner.reset(
            provider=provider,
            request=req,
            run_context=ContextWrapper(context=None),
            tool_executor=MagicMock(),
            agent_hooks=BaseAgentRunHooks(),
            streaming=False,
        )

        captured_kwargs: dict = {}

        async def spy_process(messages, **kwargs):
            captured_kwargs.update(kwargs)
            return messages

        runner.request_context_manager.process = spy_process  # type: ignore[method-assign]

        async for _ in runner.step_until_done(1):
            pass

        assert captured_kwargs["trusted_token_usage"] == 9000
        assert captured_kwargs["fixed_overhead_tokens"] > 500

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

    @pytest.mark.parametrize("as_models", [False, True])
    def test_split_rounds_keeps_internal_user_messages_in_current_round(
        self, as_models
    ):
        """Internal notices must not split a user's request from its result."""
        from astrbot.core.agent.context.round_utils import split_into_rounds
        from astrbot.core.agent.message import load_messages

        history = [
            {"role": "user", "content": "Request"},
            {"role": "assistant", "content": "Working"},
            {"role": "user", "content": "Internal notice", "_turn_continuation": True},
            {"role": "assistant", "content": "Done"},
            {"role": "user", "content": "Follow-up"},
        ]
        messages = load_messages(history) if as_models else history

        assert split_into_rounds(messages) == [messages[:4], messages[4:]]

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
