from dataclasses import dataclass
from typing import TYPE_CHECKING

from .compressor import ContextCompressor
from .token_counter import TokenCounter

if TYPE_CHECKING:
    from astrbot.core.provider.provider import Provider


@dataclass
class ContextConfig:
    """Context configuration class."""

    max_context_tokens: int = 0
    """Maximum number of context tokens. <= 0 means no limit."""
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
    llm_compress_keep_recent: int = 0
    """Number of recent messages to keep during LLM-based compression."""
    llm_compress_provider: "Provider | None" = None
    """LLM provider used for compression tasks. If None, truncation strategy is used."""
    custom_token_counter: TokenCounter | None = None
    """Custom token counting method. If None, the default method is used."""
    custom_compressor: ContextCompressor | None = None
    """Custom context compression method. If None, the default method is used."""
    sanitize_historical_thoughts: bool = True
    """Whether to strip historical reasoning (<think> tags and ThinkPart blocks) from prior turns before calling LLM."""
    sanitize_historical_tools: bool = False
    """Whether to truncate bulky historical tool execution results in prior turns."""
    max_historical_tool_result_chars: int = 500
    """Maximum character length for historical tool results when tool sanitization is enabled."""
    sanitize_historical_images: bool = False
    """Whether to sanitize or prune inline data URIs from historical turns."""
    persist_sanitized_history: bool = False
    """Whether to persist sanitized history to SQLite storage. Defaults to False (only sanitize request view)."""
