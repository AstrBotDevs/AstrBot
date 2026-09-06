from astrbot import logger

from ..message import Message
from .compressor import LLMSummaryCompressor, TruncateByTurnsCompressor
from .config import ContextConfig
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
        try:
            result = messages

            # 1. 基于轮次的截断 (Enforce max turns)
            # Skip hard turn truncation when a smart compressor (LLM/custom) is
            # active and the token guard is on; it summarizes instead.
            # If the token guard is off, keep the turn limit as the safety net.
            token_guard_enabled = self.config.max_context_tokens > 0
            skip_hard_turn_limit = token_guard_enabled and (
                self.config.llm_compress_provider is not None
                or self.config.custom_compressor is not None
            )
            if (
                self.config.enforce_max_turns != -1
                and not skip_hard_turn_limit
            ):
                before_len = len(result)
                result = self.truncator.truncate_by_turns(
                    result,
                    keep_most_recent_turns=self.config.enforce_max_turns,
                    drop_turns=self.config.truncate_turns,
                )
                if len(result) != before_len:
                    logger.info(
                        "[context] enforce_max_turns truncation applied: "
                        f"{before_len} -> {len(result)} messages.",
                    )
            elif (
                self.config.enforce_max_turns != -1
                and skip_hard_turn_limit
            ):
                logger.info(
                    "[context] enforce_max_turns skipped (LLM/custom compressor "
                    "will handle context instead of hard turn truncation).",
                )

            # 2. 基于 token 的压缩
            if self.config.max_context_tokens > 0:
                total_tokens = self.token_counter.count_tokens(
                    result, trusted_token_usage
                )

                if self.compressor.should_compress(
                    result, total_tokens, self.config.max_context_tokens
                ):
                    logger.info(
                        "[context] compression triggered: "
                        f"{total_tokens} / {self.config.max_context_tokens} tokens "
                        f"(trusted_token_usage={trusted_token_usage}).",
                    )
                    result = await self._run_compression(result, total_tokens)

            return result
        except Exception as e:
            logger.error(f"Error during context processing: {e}", exc_info=True)
            return messages

    async def _run_compression(
        self, messages: list[Message], prev_tokens: int
    ) -> list[Message]:
        """
        Compress/truncate the messages.

        Args:
            messages: The original message list.
            prev_tokens: The token count before compression.

        Returns:
            The compressed/truncated message list.
        """
        logger.debug("Compress triggered, starting compression...")

        messages = await self.compressor(messages)

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
                "Context still exceeds max tokens after compression, applying "
                "token-budget truncation instead of blind halving..."
            )
            # still need compress, drop oldest until within the token budget
            messages = self.truncator.truncate_to_token_budget(
                messages,
                self.token_counter,
                self.config.max_context_tokens,
            )

        return messages
