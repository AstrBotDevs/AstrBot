from astrbot import logger
from astrbot.core.exceptions import ContextCompressionError

from ..message import Message
from .compressor import LLMSummaryCompressor, TruncateByTurnsCompressor
from .config import ContextConfig
from .round_utils import split_into_rounds
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
            trusted_token_usage: Provider-reported usage for the request context.

        Returns:
            The processed message list.

        Raises:
            ContextCompressionError: If the compressor fails.
        """
        try:
            result = messages

            # 1. 基于轮次的截断 (Enforce max turns)
            if self.config.enforce_max_turns != -1:
                result = self.truncator.truncate_by_turns(
                    result,
                    keep_most_recent_turns=self.config.enforce_max_turns,
                    drop_turns=self.config.truncate_turns,
                )

            # 2. 基于 token 的压缩
            if self.config.max_context_tokens > 0:
                total_tokens = self.token_counter.count_tokens(
                    result, trusted_token_usage
                )

                if self.compressor.should_compress(
                    result, total_tokens, self.config.max_context_tokens
                ):
                    result = await self._run_compression(result, total_tokens)

            return result
        except ContextCompressionError:
            raise
        except Exception as e:
            logger.error(f"Error during context processing: {e}", exc_info=True)
            return messages

    async def _run_compression(
        self, messages: list[Message], prev_tokens: int
    ) -> list[Message]:
        """
        Compress/truncate the messages.

        If successful compression leaves the context above the threshold, drop
        whole rounds, oldest first. Always keep the latest round. Compression
        failures propagate so the runner can check the model's hard limit.

        Args:
            messages: The original message list.
            prev_tokens: The token count before compression.

        Returns:
            The compressed/truncated message list.

        Raises:
            ContextCompressionError: If the compressor fails.
        """
        logger.debug("Compress triggered, starting compression...")

        try:
            messages = await self.compressor(messages)
        except Exception as e:
            raise ContextCompressionError(
                f"Context compression failed: {e}",
                messages=messages,
                token_count=prev_tokens,
            ) from e

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
        if not self.compressor.should_compress(
            messages, tokens_after_summary, self.config.max_context_tokens
        ):
            return messages

        logger.info(
            "Context still exceeds max tokens after compression, dropping the oldest rounds..."
        )
        # Drop whole rounds, oldest first, so that tool calls stay with their
        # results, and recount after each one. The latest round is the current
        # request and is always kept.
        first_non_system = next(
            (i for i, msg in enumerate(messages) if msg.role != "system"),
            len(messages),
        )
        system_messages = messages[:first_non_system]
        rounds = [
            [seg for seg in rnd if isinstance(seg, Message)]
            for rnd in split_into_rounds(messages[first_non_system:])
        ]
        tokens = tokens_after_summary
        dropped_rounds = 0
        while len(rounds) > 1 and self.compressor.should_compress(
            messages, tokens, self.config.max_context_tokens
        ):
            rounds.pop(0)
            dropped_rounds += 1
            messages = system_messages + [msg for rnd in rounds for msg in rnd]
            tokens = self.token_counter.count_tokens(messages)
        logger.info(f"Dropped {dropped_rounds} oldest round(s).")

        if self.compressor.should_compress(
            messages, tokens, self.config.max_context_tokens
        ):
            logger.warning(
                "Context still exceeds max tokens with only the latest round left; "
                "sending it as is."
            )
        return messages
