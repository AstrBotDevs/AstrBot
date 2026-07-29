import asyncio
import math

from astrbot import logger

from ..message import Message
from .compressor import LLMSummaryCompressor
from .config import ContextConfig
from .round_utils import split_into_rounds
from .token_counter import EstimateTokenCounter
from .truncator import ContextTruncator


class ContextManager:
    """Context compression manager — orthogonal trigger/disposal model."""

    def __init__(
        self,
        config: ContextConfig,
    ) -> None:
        self.config = config
        self.token_counter = config.custom_token_counter or EstimateTokenCounter()
        self.truncator = ContextTruncator()

        # Build compressors on demand. Summary compressor only when a provider is
        # available; discard is handled directly via truncator, not a compressor.
        self._summary_compressor = None
        self._unity_compressor = None
        if config.custom_compressor:
            self._unity_compressor = config.custom_compressor
        else:
            if config.summary_provider:
                self._summary_compressor = LLMSummaryCompressor(
                    provider=config.summary_provider,
                    keep_recent_ratio=config.retain_percentage,
                    instruction_text=config.summary_prompt,
                    compression_threshold=config.token_guard_threshold,
                    token_counter=self.token_counter,
                )

    # -- helpers ----------------------------------------------------------

    def _count_turns(self, messages: list[Message]) -> int:
        """Count the number of conversation turns (non-system rounds)."""
        rounds = split_into_rounds(messages)
        # Filter out rounds that are exclusively system messages
        return sum(
            1
            for rnd in rounds
            if any((isinstance(m, Message) and m.role != "system") for m in rnd)
        )

    def _compute_discard_limit(self, total_turns: int) -> int:
        """Maximum number of turns that discard may remove, given retention."""
        method = self.config.retention_method
        if method == "turns":
            return max(0, total_turns - self.config.retain_turns)
        if method == "percentage":
            min_keep = math.ceil(total_turns * self.config.retain_percentage)
            return max(0, total_turns - min_keep)
        # "null" — no lower bound
        return total_turns

    async def _try_summary(self, messages: list[Message]) -> list[Message] | None:
        """Attempt LLM summary compression. Returns compressed messages or None."""
        if not self.config.enable_summary or self._summary_compressor is None:
            return None
        try:
            result = await self._summary_compressor(messages)
            if result is None or result is messages:
                return None  # compressor chose not to compress
            if len(result) >= len(messages):
                return None  # no effective reduction
            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.warning(
                "LLM summary compression failed, falling back.", exc_info=True
            )
            return None

    def _try_discard(
        self, messages: list[Message], total_turns: int
    ) -> list[Message] | None:
        """Discard oldest turns, bounded by retention."""
        if not self.config.enable_discard:
            return None
        max_discardable = self._compute_discard_limit(total_turns)
        if max_discardable <= 0:
            return None  # retention prevents any discard
        requested = min(self.config.discard_turns, max_discardable)
        return self.truncator.truncate_by_dropping_oldest_turns(
            messages,
            drop_turns=requested,
        )

    def _token_guard_exceeded(self, tokens: int, max_context_tokens: int) -> bool:
        """Pure predicate: return True if tokens exceed the configured threshold."""
        if tokens <= 0 or max_context_tokens <= 0:
            return False
        return (tokens / max_context_tokens) > self.config.token_guard_threshold

    def _triggers_fired(
        self,
        total_turns: int,
        current_tokens: int,
        guard_max_tokens: int,
    ) -> bool:
        """Return True if any trigger condition is met.

        Args:
            total_turns: Current conversation turn count.
            current_tokens: Current token count.
            guard_max_tokens: Resolved guard window (0 = token guard disabled).
        """
        if self.config.enable_turn_limit and total_turns > self.config.max_turns:
            return True

        if (
            self.config.enable_token_guard
            and guard_max_tokens
            and self._token_guard_exceeded(current_tokens, guard_max_tokens)
        ):
            return True

        return False

    async def _select_disposal(
        self,
        messages: list[Message],
        total_turns: int,
    ) -> list[Message]:
        """Apply disposal strategy: custom > summary > discard."""
        if self._unity_compressor is not None:
            return await self._unity_compressor(messages)

        compressed = await self._try_summary(messages)
        if compressed is not None:
            return compressed

        discarded = self._try_discard(messages, total_turns=total_turns)
        if discarded is not None:
            return discarded

        logger.warning(
            "Context disposal triggered but both summary and discard "
            "are unavailable or disabled. No compression applied.",
        )
        return messages

    # -- main entry point -------------------------------------------------

    async def process(
        self,
        messages: list[Message],
        trusted_token_usage: int = 0,
        max_context_tokens: int = 0,
    ) -> list[Message]:
        """Process messages through the orthogonal trigger/disposal pipeline.

        Args:
            messages: The original message list.
            trusted_token_usage: External token count hint (e.g. from conversation stats).
            max_context_tokens: The model's context window size (provider-level value).

        Returns:
            The processed message list.
        """
        try:
            result = messages

            current_tokens = self.token_counter.count_tokens(
                result, trusted_token_usage
            )
            total_turns = self._count_turns(result)

            # Resolve token guard: validate config and precompute guard window.
            guard_max_tokens = 0
            if self.config.enable_token_guard:
                if max_context_tokens <= 0:
                    if not getattr(self, "_token_guard_warning_emitted", False):
                        logger.warning(
                            "Token guard is enabled but max_context_tokens is %s. "
                            "Token guarding is effectively disabled. "
                            "Set max_context_tokens in the provider config to enable it.",
                            max_context_tokens,
                        )
                        self._token_guard_warning_emitted = True
                else:
                    guard_max_tokens = max_context_tokens

            if not self._triggers_fired(total_turns, current_tokens, guard_max_tokens):
                return result

            # Disposal entry: custom > summary > discard (fallthrough)
            result = await self._select_disposal(result, total_turns)

            # Double-check halving — only when token guard is active
            tokens_after = self.token_counter.count_tokens(result, trusted_token_usage)
            if guard_max_tokens and self._token_guard_exceeded(
                tokens_after, guard_max_tokens
            ):
                logger.info(
                    "Context still exceeds token guard threshold after disposal, "
                    "applying halving truncation (unconstrained by retention).",
                )
                result = self.truncator.truncate_by_halving(result)

            return result
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.error("Error during context processing.", exc_info=True)
            return messages
