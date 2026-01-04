from typing import TYPE_CHECKING

from astrbot import logger

from ..message import Message
from .compressor import LLMSummaryCompressor, TruncateByTurnsCompressor
from .token_counter import TokenCounter
from .truncator import ContextTruncator

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider


class ContextManager:
    """Context compression manager."""

    COMPRESSION_THRESHOLD = 0.82
    """compression trigger threshold"""

    def __init__(
        self,
        max_context_tokens: int = 0,
        truncate_turns: int = 1,
        llm_compress_instruction: str | None = None,
        llm_compress_keep_recent: int = 4,
        llm_compress_provider: "Provider | None" = None,
    ):
        """Initialize the context manager.

        There are two strategies to handle context limit reached:
        1. Truncate by turns: remove older messages by turns.
        2. LLM-based compression: use LLM to summarize old messages.

        Args:
            max_context_tokens: The maximum context tokens. <= 0 means no limit.
            truncate_turns: For turncate strategy. The number of turns to discard when truncating.
            llm_compress_instruction: The instruction text for LLM compression.
            llm_compress_keep_recent: The number of recent messages to keep during LLM compression.
            llm_compress_provider: The LLM provider for compression.
        """
        self.max_context_tokens = max_context_tokens
        self.truncate_turns = truncate_turns

        self.token_counter = TokenCounter()
        self.truncator = ContextTruncator()

        if llm_compress_provider:
            self.compressor = LLMSummaryCompressor(
                provider=llm_compress_provider,
                keep_recent=llm_compress_keep_recent,
                instruction_text=llm_compress_instruction,
            )
        else:
            self.compressor = TruncateByTurnsCompressor(truncate_turns=truncate_turns)

    async def process(self, messages: list[Message]) -> list[Message]:
        """Process the messages.

        Args:
            messages: The original message list.

        Returns:
            The processed message list.
        """
        if self.max_context_tokens <= 0:
            return messages

        # check if the messages need to be compressed
        needs_compression, _ = await self._initial_token_check(messages)

        # compress/truncate the messages if needed
        messages = await self._run_compression(messages, needs_compression)

        return messages

    async def _initial_token_check(
        self, messages: list[Message]
    ) -> tuple[bool, int | None]:
        """
        Check if the messages need to be compressed.

        Args:
            messages: The original message list.

        Returns:
            tuple: (whether to compress, initial token count)
        """
        if not messages:
            return False, None
        if self.max_context_tokens <= 0:
            return False, None

        total_tokens = self.token_counter.count_tokens(messages)

        logger.debug(
            f"ContextManager: total tokens = {total_tokens}, max_context_tokens = {self.max_context_tokens}"
        )
        usage_rate = total_tokens / self.max_context_tokens

        needs_compression = usage_rate > self.COMPRESSION_THRESHOLD
        return needs_compression, total_tokens if needs_compression else None

    async def _run_compression(
        self, messages: list[Message], needs_compression: bool
    ) -> list[Message]:
        """
        Compress/truncate the messages if needed.

        Args:
            messages: The original message list.
            needs_compression: Whether to compress.

        Returns:
            The compressed/truncated message list.
        """
        if not needs_compression:
            return messages
        if self.max_context_tokens <= 0:
            return messages

        messages = await self.compressor.compress(messages)

        # double check
        tokens_after_summary = self.token_counter.count_tokens(messages)
        if tokens_after_summary / self.max_context_tokens > self.COMPRESSION_THRESHOLD:
            # still over 82%, truncate by half
            messages = self._compress_by_halving(messages)

        return messages

    def _compress_by_halving(self, messages: list[Message]) -> list[Message]:
        """
        对半砍策略：删除中间50%的消息

        Args:
            messages: 原始消息列表

        Returns:
            截断后的消息列表
        """
        return self.truncator.truncate_by_halving(messages)
