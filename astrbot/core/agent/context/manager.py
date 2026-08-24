from astrbot import logger

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
                preserve_latest_round=config.llm_compress_preserve_latest_round,
            )
        else:
            self.compressor = TruncateByTurnsCompressor(
                truncate_turns=config.truncate_turns
            )

    async def process(
        self,
        messages: list[Message],
        trusted_token_usage: int = 0,
        force_compress: bool = False,
    ) -> list[Message]:
        """Process the messages.

        Args:
            messages: The original message list.
            trusted_token_usage: Token usage reported by the previous provider call.
            force_compress: Whether to bypass automatic limits and run the configured
                compressor immediately without a truncation fallback.

        Returns:
            The processed message list.
        """
        try:
            result = messages

            # 1. 基于轮次的截断 (Enforce max turns)
            if not force_compress and self.config.enforce_max_turns != -1:
                result = self.truncator.truncate_by_turns(
                    result,
                    keep_most_recent_turns=self.config.enforce_max_turns,
                    drop_turns=self.config.truncate_turns,
                )

            if force_compress:
                total_tokens = self.token_counter.count_tokens(result)
                return await self._run_compression(
                    result,
                    total_tokens,
                    allow_halving_fallback=False,
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
        except Exception as e:
            logger.error("Context processing failed: %s.", type(e).__name__)
            return messages

    async def _run_compression(
        self,
        messages: list[Message],
        prev_tokens: int,
        allow_halving_fallback: bool = True,
    ) -> list[Message]:
        """Compress or truncate the messages.

        If the context still exceeds the limit after compression (for example
        because the summary request failed), whole rounds are dropped, oldest
        first, until it fits. The latest round is always kept, even when it
        alone exceeds the limit.

        Args:
            messages: The original message list.
            prev_tokens: The token count before compression.
            allow_halving_fallback: Whether to drop oldest rounds if the result still
                exceeds the automatic compression threshold.

        Returns:
            The compressed/truncated message list.
        """
        logger.debug("Compress triggered, starting compression...")

        messages = await self.compressor(messages)

        # double check
        tokens_after_summary = self.token_counter.count_tokens(messages)

        logger.info("Compress completed.")

        # last check
        if not allow_halving_fallback or not self.compressor.should_compress(
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
