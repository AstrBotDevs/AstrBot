from astrbot import logger
from astrbot.core.exceptions import ConversationPersistenceError

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
        self.revision = 0

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
                request_event_emitter=config.request_event_emitter,
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
            if self.config.enforce_max_turns != -1:
                result = self.truncator.truncate_by_turns(
                    result,
                    keep_most_recent_turns=self.config.enforce_max_turns,
                    drop_turns=self.config.truncate_turns,
                )

            if result is not messages:
                self.revision += 1

            # 2. 基于 token 的压缩
            if self.config.max_context_tokens > 0:
                total_tokens = self.token_counter.count_tokens(
                    result, trusted_token_usage
                )

                if self.compressor.should_compress(
                    result, total_tokens, self.config.max_context_tokens
                ):
                    # Custom compressors may mutate the existing list in place.
                    self.revision += 1
                    estimated_prev_tokens = (
                        total_tokens if trusted_token_usage == 0 else None
                    )
                    result = await self._run_compression(
                        result,
                        total_tokens,
                        estimated_prev_tokens=estimated_prev_tokens,
                    )

            return result
        except ConversationPersistenceError:
            raise
        except Exception as e:
            logger.error(f"Error during context processing: {e}", exc_info=True)
            return messages

    @staticmethod
    def _is_unchanged_messages(
        before: list[Message],
        after: list[Message],
        est_before: int,
        est_after: int,
    ) -> bool:
        """Return True if compression made no observable change to messages."""
        return bool(after) and est_after == est_before and after == before

    @staticmethod
    def _calibrate_token_count(
        estimated_tokens: int,
        est_before: int,
        prev_tokens: int,
        *,
        has_messages: bool,
    ) -> int:
        """Calibrate a post-compression heuristic token count against ``prev_tokens``.

        When ``prev_tokens`` (for example, API-reported ``trusted_token_usage``)
        exceeds the local pre-compression heuristic ``est_before``, uncalibrated
        recounts can underestimate real usage and skip fallback truncation.
        Scaling by ``prev_tokens / est_before`` keeps checks aligned with real
        usage while preserving proportional reductions from real compression.
        """
        if prev_tokens <= est_before:
            return estimated_tokens
        if estimated_tokens <= 0:
            return prev_tokens if (est_before <= 0 and has_messages) else 0
        if est_before <= 0:
            return estimated_tokens
        # Exact integer ceiling of estimated_tokens * prev_tokens / est_before.
        return (estimated_tokens * prev_tokens + est_before - 1) // est_before

    async def _run_compression(
        self,
        messages: list[Message],
        prev_tokens: int,
        estimated_prev_tokens: int | None = None,
    ) -> list[Message]:
        """
        Compress/truncate the messages.

        If the context still exceeds the limit after compression (for example
        because the summary request failed), whole rounds are dropped, oldest
        first, until it fits. The latest round is always kept, even when it
        alone exceeds the limit.

        Args:
            messages: The original message list.
            prev_tokens: The token count before compression.
            estimated_prev_tokens: Optional uncalibrated token estimate for
                ``messages`` prior to compression.

        Returns:
            The compressed/truncated message list.
        """
        logger.debug("Compress triggered, starting compression...")

        original_messages = list(messages)
        est_before = (
            estimated_prev_tokens
            if estimated_prev_tokens is not None
            else self.token_counter.count_tokens(messages)
        )

        messages = await self.compressor(messages)

        # double check (calibrated against prev_tokens when heuristic underestimates)
        raw_tokens_after_summary = self.token_counter.count_tokens(messages)
        compression_noop = self._is_unchanged_messages(
            original_messages,
            messages,
            est_before,
            raw_tokens_after_summary,
        )
        tokens_after_summary = (
            max(raw_tokens_after_summary, prev_tokens)
            if compression_noop
            else self._calibrate_token_count(
                raw_tokens_after_summary,
                est_before,
                prev_tokens,
                has_messages=bool(messages),
            )
        )

        # calculate compress rate
        compress_rate = (
            (tokens_after_summary / self.config.max_context_tokens) * 100
            if self.config.max_context_tokens > 0
            else 0.0
        )
        if compression_noop:
            logger.warning(
                f"Compression made no changes."
                f" {prev_tokens} -> {tokens_after_summary} tokens,"
                f" context usage: {compress_rate:.2f}%.",
            )
        else:
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
        # results. Always keep the latest round, which is the current request.
        first_non_system = next(
            (i for i, msg in enumerate(messages) if msg.role != "system"),
            len(messages),
        )
        system_messages = messages[:first_non_system]
        rounds = [
            [seg for seg in rnd if isinstance(seg, Message)]
            for rnd in split_into_rounds(messages[first_non_system:])
        ]
        raw_tokens = raw_tokens_after_summary
        tokens = tokens_after_summary
        dropped_rounds = 0
        # Built-in estimates are additive and compression checks only use tokens.
        # Custom implementations need updated messages and a full recount.
        incremental_tokens = type(self.token_counter) is EstimateTokenCounter and type(
            self.compressor
        ) in (TruncateByTurnsCompressor, LLMSummaryCompressor)
        while len(rounds) - dropped_rounds > 1 and self.compressor.should_compress(
            messages, tokens, self.config.max_context_tokens
        ):
            dropped_round = rounds[dropped_rounds]
            dropped_rounds += 1
            if incremental_tokens:
                raw_tokens = max(
                    0, raw_tokens - self.token_counter.count_tokens(dropped_round)
                )
            else:
                messages = system_messages + [
                    msg for rnd in rounds[dropped_rounds:] for msg in rnd
                ]
                raw_tokens = self.token_counter.count_tokens(messages)
            tokens = self._calibrate_token_count(
                raw_tokens,
                est_before,
                prev_tokens,
                has_messages=True,
            )
        if incremental_tokens and dropped_rounds:
            messages = system_messages + [
                msg for rnd in rounds[dropped_rounds:] for msg in rnd
            ]
        logger.info(f"Dropped {dropped_rounds} oldest round(s).")

        if self.compressor.should_compress(
            messages, tokens, self.config.max_context_tokens
        ):
            logger.warning(
                "Context still exceeds max tokens with only the latest round left; "
                "sending it as is."
            )
        return messages
