from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .compressor import ContextCompressor
from .token_counter import TokenCounter

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider


@dataclass
class ContextConfig:
    """Context configuration class — orthogonal trigger/disposal model.

    Trigger dimension (WHEN) — checked independently:
        enable_turn_limit / max_turns
        enable_token_guard / token_guard_threshold

    Disposal dimension (WHAT) — executed in order when any trigger fires:
        1. summary (if enabled and provider available)
        2. discard (fallback if summary fails or is disabled)

    Retention constraint — lower bound on how many turns discard may remove.
    Double-check halving — unconditional truncation when still over threshold
    after disposal (only when enable_token_guard is True).
    """

    # -- Trigger dimension --
    enable_turn_limit: bool = False
    """Enable turn-based trigger. When True, exceeding max_turns triggers disposal."""
    max_turns: int = 50
    """Maximum conversation turns before disposal is triggered. Must be >= 2."""
    enable_token_guard: bool = True
    """Enable token-count trigger. When True, exceeding token_guard_threshold
    triggers disposal."""
    token_guard_threshold: float = 0.82
    """Token usage ratio (current_tokens / max_tokens) that triggers disposal.
    Range 0.5–0.99."""

    # -- Disposal dimension (compression behavior) --
    enable_summary: bool = True
    """Enable LLM-based summary compression. Takes priority over discard when
    both are enabled."""
    enable_discard: bool = True
    """Enable discard of oldest turns. Used as fallback if summary fails or
    is disabled."""
    discard_turns: int = 1
    """Number of turns to discard at once. Must be >= 1."""
    summary_prompt: str = ""
    """Custom instruction prompt for summary generation. Empty = use built-in."""
    summary_provider: "Provider | None" = None
    """Resolved LLM provider for summary generation. None = no summary available."""

    # -- Retention (lower bound) --
    retention_method: Literal["turns", "percentage", "null"] = "turns"
    """Retention method: 'turns', 'percentage', or 'null'."""
    retain_turns: int = 20
    """Minimum turns to keep when retention_method is 'turns'. Must be >= 1."""
    retain_percentage: float = 0.3
    """Minimum ratio of turns to keep when retention_method is 'percentage'.
    Range 0.1–0.9."""

    # -- Customisation --
    custom_token_counter: TokenCounter | None = None
    """Custom token counting method. If None, the default method is used."""
    custom_compressor: ContextCompressor | None = None
    """Custom context compression method. If None, the default method is used."""
