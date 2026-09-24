from astrbot import logger
from astrbot.core.image_request_budget import ImageBudgetExceeded
from astrbot.core.utils.media_utils import is_recoverable_image_error

from ..message import Message
from .compressor import LLMSummaryCompressor, TruncateByTurnsCompressor
from .config import ContextConfig
from .token_counter import EstimateTokenCounter, estimate_preview_tokens
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
                strip_images=config.strip_summary_images,
                image_context=config.image_context,
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

            # 2. 基于 token 的压缩
            if self.config.max_context_tokens > 0:
                count_messages = result
                visual_tokens = 0
                if self.config.image_context is not None:
                    count_messages = await self.config.image_context.project_messages(
                        result
                    )
                    estimates = await estimate_preview_tokens(
                        self.config.image_context.pending_visuals.values()
                    )
                    visual_tokens = estimates["tokens"]
                    # Prior usage describes a different request, not this projection.
                    trusted_token_usage = 0
                total_tokens = (
                    self.token_counter.count_tokens(count_messages, trusted_token_usage)
                    + visual_tokens
                )

                if self.compressor.should_compress(
                    result, total_tokens, self.config.max_context_tokens
                ):
                    result = await self._run_compression(result, total_tokens)

            return result
        except ImageBudgetExceeded:
            raise
        except Exception as e:
            if self.config.image_context is not None and (
                isinstance(e, MemoryError)
                or (isinstance(e, OSError) and not is_recoverable_image_error(e))
            ):
                raise
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
        count_messages = messages
        visual_tokens = 0
        if self.config.image_context is not None:
            count_messages = await self.config.image_context.project_messages(messages)
            estimates = await estimate_preview_tokens(
                self.config.image_context.pending_visuals.values()
            )
            visual_tokens = estimates["tokens"]
        tokens_after_summary = (
            self.token_counter.count_tokens(count_messages) + visual_tokens
        )

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
                "Context still exceeds max tokens after compression, applying halving truncation..."
            )
            # still need compress, truncate by half
            messages = self.truncator.truncate_by_halving(messages)

        return messages
