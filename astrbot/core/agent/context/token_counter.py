import json
from collections.abc import Callable
from typing import Protocol, runtime_checkable

from astrbot import logger

from ..message import AudioURLPart, ImageURLPart, Message, TextPart, ThinkPart


@runtime_checkable
class TokenCounter(Protocol):
    """
    Protocol for token counters.
    Provides an interface for counting tokens in message lists.
    """

    def count_tokens(
        self, messages: list[Message], trusted_token_usage: int = 0
    ) -> int:
        """Count the total tokens in the message list.

        Args:
            messages: The message list.
            trusted_token_usage: The total token usage that LLM API returned.
                For some cases, this value is more accurate.
                But some API does not return it, so the value defaults to 0.

        Returns:
            The total token count.
        """
        ...


# 图片/音频 token 开销估算值，参考 OpenAI vision pricing:
# low-res ~85 tokens, high-res ~170 per 512px tile, 通常几百到上千。
# 这里取一个保守中位数，宁可偏高触发压缩也不要偏低导致 API 报错。
IMAGE_TOKEN_ESTIMATE = 765
AUDIO_TOKEN_ESTIMATE = 500


class EstimateTokenCounter:
    """Estimate token counter implementation.
    Provides a simple estimation of token count based on character types.

    Supports multimodal content: images, audio, and thinking parts
    are all counted so that the context compressor can trigger in time.
    """

    def count_tokens(
        self, messages: list[Message], trusted_token_usage: int = 0
    ) -> int:
        if trusted_token_usage > 0:
            return trusted_token_usage

        total = 0
        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                total += self._estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, TextPart):
                        total += self._estimate_tokens(part.text)
                    elif isinstance(part, ThinkPart):
                        total += self._estimate_tokens(part.think)
                    elif isinstance(part, ImageURLPart):
                        total += IMAGE_TOKEN_ESTIMATE
                    elif isinstance(part, AudioURLPart):
                        total += AUDIO_TOKEN_ESTIMATE

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_str = json.dumps(tc if isinstance(tc, dict) else tc.model_dump())
                    total += self._estimate_tokens(tc_str)

        return total

    def _estimate_tokens(self, text: str) -> int:
        chinese_count = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
        other_count = len(text) - chinese_count
        return int(chinese_count * 0.6 + other_count * 0.3)


class TokenizerTokenCounter:
    """Tokenizer-based token counter.

    Uses `tiktoken` when available and falls back to estimate mode if encoding
    is unavailable.
    """

    def __init__(self, model: str | None = None) -> None:
        self._estimate = EstimateTokenCounter()
        self._encode: Callable[[str], int] | None = None
        self._available = False
        self._init_encoder(model)

    @property
    def available(self) -> bool:
        return self._available

    def _init_encoder(self, model: str | None) -> None:
        try:
            import tiktoken  # type: ignore
        except Exception:
            self._available = False
            self._encode = None
            return

        try:
            if model:
                encoding = tiktoken.encoding_for_model(model)
            else:
                encoding = tiktoken.get_encoding("cl100k_base")
        except Exception:
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
            except Exception:
                self._available = False
                self._encode = None
                return

        self._available = True
        self._encode = lambda text: len(encoding.encode(text))

    def count_tokens(
        self, messages: list[Message], trusted_token_usage: int = 0
    ) -> int:
        if trusted_token_usage > 0:
            return trusted_token_usage
        if not self._available:
            return self._estimate.count_tokens(messages)

        total = 0
        for msg in messages:
            content = msg.content
            if isinstance(content, str):
                total += self._encode_len(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, TextPart):
                        total += self._encode_len(part.text)
                    elif isinstance(part, ThinkPart):
                        total += self._encode_len(part.think)
                    elif isinstance(part, ImageURLPart):
                        total += IMAGE_TOKEN_ESTIMATE
                    elif isinstance(part, AudioURLPart):
                        total += AUDIO_TOKEN_ESTIMATE

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_str = json.dumps(
                        tc if isinstance(tc, dict) else tc.model_dump(),
                        ensure_ascii=False,
                        default=str,
                    )
                    total += self._encode_len(tc_str)

        return total

    def _encode_len(self, text: str) -> int:
        if not self._encode:
            return self._estimate._estimate_tokens(text)
        try:
            return self._encode(text)
        except Exception:
            return self._estimate._estimate_tokens(text)


def create_token_counter(
    mode: str | None = None,
    *,
    model: str | None = None,
) -> TokenCounter:
    normalized = str(mode or "estimate").strip().lower()

    if normalized == "estimate":
        return EstimateTokenCounter()

    if normalized in {"tokenizer", "auto"}:
        tokenizer_counter = TokenizerTokenCounter(model=model)
        if tokenizer_counter.available:
            return tokenizer_counter
        if normalized == "tokenizer":
            logger.warning(
                "context_token_counter_mode=tokenizer but `tiktoken` is unavailable; fallback to estimate."
            )
        return EstimateTokenCounter()

    logger.warning(
        "Unknown context_token_counter_mode=%s, fallback to estimate.",
        normalized,
    )
    return EstimateTokenCounter()
