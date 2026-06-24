from astrbot import logger

from ..message import Message
from .compressor import LLMSummaryCompressor, TruncateByTurnsCompressor
from .config import ContextConfig
from .round_utils import count_conversation_rounds
from .token_counter import EstimateTokenCounter
from .truncator import ContextTruncator


class ContextManager:
    """Context compression manager."""

    def __init__(
        self,
        config: ContextConfig,
    ) -> None:
        """Initialize the context manager.

        There are two strategies to handle context limit reached:
        1. Truncate by turns: remove older messages by turns.
        2. LLM-based compression: use LLM to summarize old messages.

        Args:
            config: The context configuration.
        """
        self.config = config

        self.token_counter = config.custom_token_counter or EstimateTokenCounter()
        self.truncator = ContextTruncator()

        if config.custom_compressor:
            self.compressor = config.custom_compressor
        elif config.llm_compress_provider:
            self.compressor = LLMSummaryCompressor(
                provider=config.llm_compress_provider,
                keep_recent_ratio=config.llm_compress_keep_recent_ratio,
                instruction_text=config.llm_compress_instruction,
                token_counter=self.token_counter,
            )
        else:
            self.compressor = TruncateByTurnsCompressor(
                truncate_turns=config.truncate_turns
            )

    async def process(
        self, messages: list[Message], trusted_token_usage: int = 0
    ) -> list[Message]:
        """Process the messages.

        Args:
            messages: The original message list.

        Returns:
            The processed message list.
        """
        result, _ = await self.process_with_meta(messages, trusted_token_usage)
        return result

    async def process_with_meta(
        self, messages: list[Message], trusted_token_usage: int = 0
    ) -> tuple[list[Message], bool]:
        try:
            result = messages
            was_hard_truncated = False

            if self.config.enforce_max_turns != -1:
                turn_count = count_conversation_rounds(result)
                if turn_count > self.config.enforce_max_turns:
                    if isinstance(self.compressor, LLMSummaryCompressor):
                        logger.debug(
                            "Turn limit (%s) exceeded (%s turns), "
                            "delegating to LLM summary compressor instead of "
                            "hard truncation.",
                            self.config.enforce_max_turns,
                            turn_count,
                        )
                        compressed = await self.compressor(result)
                        if self.compressor.last_call_failed:
                            logger.warning(
                                "LLM summary compression failed; falling back "
                                "to turn-based truncation to bound context "
                                "size.",
                            )
                            result = self.truncator.truncate_by_turns(
                                result,
                                keep_most_recent_turns=self.config.enforce_max_turns,
                                drop_turns=self.config.truncate_turns,
                            )
                            was_hard_truncated = True
                        else:
                            result = compressed
                    else:
                        result = self.truncator.truncate_by_turns(
                            result,
                            keep_most_recent_turns=self.config.enforce_max_turns,
                            drop_turns=self.config.truncate_turns,
                        )
                        was_hard_truncated = True

            if self.config.max_context_tokens > 0:
                total_tokens = self.token_counter.count_tokens(
                    result, trusted_token_usage
                )

                if self.compressor.should_compress(
                    result, total_tokens, self.config.max_context_tokens
                ):
                    result, compression_was_lossy = await self._run_compression(
                        result, total_tokens
                    )
                    was_hard_truncated = was_hard_truncated or compression_was_lossy

            return result, was_hard_truncated
        except Exception as e:
            logger.error(f"Error during context processing: {e}", exc_info=True)
            return messages, False

    async def _run_compression(
        self, messages: list[Message], prev_tokens: int
    ) -> tuple[list[Message], bool]:
        """
        Compress/truncate the messages.

        Args:
            messages: The original message list.
            prev_tokens: The token count before compression.

        Returns:
            The compressed/truncated message list.
        """
        logger.debug("Compress triggered, starting compression...")

        compressed = await self.compressor(messages)
        was_lossy = (
            not isinstance(self.compressor, LLMSummaryCompressor)
            or self.compressor.last_call_failed
        )
        messages = compressed

        # double check
        tokens_after_summary = self.token_counter.count_tokens(messages)

        # calculate compress rate
        compress_rate = (tokens_after_summary / self.config.max_context_tokens) * 100
        logger.info(
            f"Compress completed."
            f" {prev_tokens} -> {tokens_after_summary} tokens,"
            f" compression rate: {compress_rate:.2f}%.",
        )

        # last check
        if self.compressor.should_compress(
            messages, tokens_after_summary, self.config.max_context_tokens
        ):
            logger.info(
                "Context still exceeds max tokens after compression, applying hard truncation..."
            )
            was_lossy = True
            while self.compressor.should_compress(
                messages, tokens_after_summary, self.config.max_context_tokens
            ):
                truncated = self.truncator.truncate_by_dropping_oldest_turns(
                    messages,
                    drop_turns=self.config.truncate_turns,
                )
                if truncated == messages:
                    truncated = self.truncator.truncate_by_halving(messages)
                if truncated == messages:
                    break
                next_tokens = self.token_counter.count_tokens(truncated)
                if next_tokens >= tokens_after_summary:
                    break
                messages = truncated
                tokens_after_summary = next_tokens

        return messages, was_lossy
