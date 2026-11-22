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
        self._uses_builtin_llm_compressor = False

        if config.custom_compressor:
            self.compressor = config.custom_compressor
        elif config.llm_compress_provider:
            self._uses_builtin_llm_compressor = True
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
        self,
        messages: list[Message],
        trusted_token_usage: int = 0,
        *,
        request_id: str = "",
        umo: str = "",
        conversation_id: str = "",
    ) -> list[Message]:
        """Process the messages.

        Args:
            messages: The original message list.
            request_id: Request ID shared with the current agent run.
            umo: Unified message origin of the current event.
            conversation_id: Conversation ID of the current request.

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
                    result = await self._run_compression(
                        result,
                        total_tokens,
                        request_id=request_id,
                        umo=umo,
                        conversation_id=conversation_id,
                    )

            return result
        except ConversationPersistenceError:
            raise
        except Exception as e:
            logger.error(f"Error during context processing: {e}", exc_info=True)
            return messages

    async def _run_compression(
        self,
        messages: list[Message],
        prev_tokens: int,
        *,
        request_id: str = "",
        umo: str = "",
        conversation_id: str = "",
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
            request_id: Request ID shared with the current agent run.
            umo: Unified message origin of the current event.
            conversation_id: Conversation ID of the current request.

        Returns:
            The compressed/truncated message list.
        """
        logger.debug("Compress triggered, starting compression...")

        if self._uses_builtin_llm_compressor:
            messages = await self.compressor(
                messages,
                request_id=request_id,
                umo=umo,
                conversation_id=conversation_id,
            )
        else:
            # Custom compressors retain the original single-argument interface.
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
                tokens -= self.token_counter.count_tokens(dropped_round)
            else:
                messages = system_messages + [
                    msg for rnd in rounds[dropped_rounds:] for msg in rnd
                ]
                tokens = self.token_counter.count_tokens(messages)
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
