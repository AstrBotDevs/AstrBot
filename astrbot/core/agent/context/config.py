from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

from astrbot.core.utils.config_number import (
    coerce_float_config,
    coerce_int_config,
)

from .compressor import ContextCompressor
from .token_counter import TokenCounter

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider


DEFAULT_FALLBACK_MAX_CONTEXT_TOKENS = 128_000


CompressionThresholdMode = Literal["percentage", "output_reserve", "min", "max"]


class CompressionThresholdResult(TypedDict):
    """Resolved compression threshold shared by runtime and dashboard."""

    mode: CompressionThresholdMode
    percentage: float
    output_tokens: int
    output_threshold: float | None
    effective_threshold: float
    fallback_reason: str | None


def resolve_compression_threshold(
    mode: str,
    percentage: float,
    max_context_tokens: int,
    max_output_tokens: int,
    warn: bool = True,
) -> CompressionThresholdResult:
    """Resolve the effective context compression threshold.

    Args:
        mode: Threshold strategy: percentage, output_reserve, min, or max.
        percentage: User-defined context usage threshold.
        max_context_tokens: Effective model context window.
        max_output_tokens: Effective maximum output budget, or zero when unknown.

    Returns:
        The normalized inputs and effective threshold used by the compressor.
    """
    normalized_mode: CompressionThresholdMode = (
        mode if mode in {"percentage", "output_reserve", "min", "max"} else "percentage"
    )
    normalized_percentage = coerce_float_config(
        percentage,
        default=0.82,
        min_value=0.01,
        max_value=1.0,
        field_name="compression_threshold_percentage",
        warn=warn,
    )
    normalized_context_tokens = coerce_int_config(
        max_context_tokens,
        default=0,
        min_value=0,
        field_name="max_context_tokens",
        warn=warn,
    )
    normalized_output_tokens = coerce_int_config(
        max_output_tokens,
        default=0,
        min_value=0,
        field_name="compression_max_output_tokens",
        warn=warn,
    )
    output_threshold = None
    fallback_reason = None

    if normalized_context_tokens > 0 and normalized_output_tokens > 0:
        output_threshold = max(
            0.0,
            1.0 - normalized_output_tokens / normalized_context_tokens,
        )

    if normalized_mode == "percentage":
        effective_threshold = normalized_percentage
    elif output_threshold is None:
        effective_threshold = normalized_percentage
        fallback_reason = "max_output_tokens_unavailable"
    elif normalized_mode == "output_reserve":
        effective_threshold = output_threshold
    elif normalized_mode == "min":
        effective_threshold = min(normalized_percentage, output_threshold)
    else:
        effective_threshold = max(normalized_percentage, output_threshold)

    return {
        "mode": normalized_mode,
        "percentage": normalized_percentage,
        "output_tokens": normalized_output_tokens,
        "output_threshold": output_threshold,
        "effective_threshold": effective_threshold,
        "fallback_reason": fallback_reason,
    }


@dataclass
class ContextConfig:
    """Context configuration class."""

    max_context_tokens: int = 0
    """Maximum number of context tokens. <= 0 means no limit."""
    compression_threshold: float = 0.82
    """Effective context usage ratio that triggers compression."""
    enforce_max_turns: int = -1  # -1 means no limit
    """Maximum number of conversation turns to keep. -1 means no limit. Executed before compression."""
    truncate_turns: int = 1
    """Number of conversation turns to discard at once when truncation is triggered.
    Two processes will use this value:

    1. Enforce max turns truncation.
    2. Truncation by turns compression strategy.
    """
    llm_compress_instruction: str | None = None
    """Instruction prompt for LLM-based compression."""
    llm_compress_keep_recent_ratio: float = 0.15
    """Percent of current context tokens to keep as exact recent context during LLM-based compression."""
    llm_compress_provider: "Provider | None" = None
    """LLM provider used for compression tasks. If None, truncation strategy is used."""
    custom_token_counter: TokenCounter | None = None
    """Custom token counting method. If None, the default method is used."""
    custom_compressor: ContextCompressor | None = None
    """Custom context compression method. If None, the default method is used."""
