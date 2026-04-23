import json
from typing import Protocol, runtime_checkable

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

# 每条消息的固定开销（role、content wrapper 等）
PER_MESSAGE_OVERHEAD = 4


class EstimateTokenCounter:
    """Estimate token counter implementation.
    Provides a simple estimation of token count based on character types.

    Supports multimodal content: images, audio, and thinking parts
    are all counted so that the context compressor can trigger in time.

    Optimizations:
    - 使用更精确的 token 估算算法
    - 缓存重复计算结果
    - 支持批量计数
    """

    def __init__(self, cache_size: int = 100) -> None:
        """Initialize the token counter with optional cache.

        Args:
            cache_size: Maximum number of message lists to cache (default: 100).
        """
        self._cache: dict[int, int] = {}
        self._cache_size = cache_size
        self._hit_count = 0
        self._miss_count = 0

    def _get_cache_key(self, messages: list[Message]) -> int:
        """Generate a cache key for messages based on full history structure.

        Uses role, content, and tool_calls for each message to create a
        collision-resistant hash.
        """
        if not messages:
            return 0

        h = 0
        for msg in messages:
            # 处理 content
            if isinstance(msg.content, str):
                content_repr = msg.content
            else:
                content_repr = str(msg.content)

            # 处理 tool_calls
            tool_repr = ()
            if msg.tool_calls:
                tool_repr = tuple(
                    sorted(tc.items()) if isinstance(tc, dict) else (str(tc),)
                    for tc in msg.tool_calls
                )

            h = hash((h, msg.role, content_repr, tool_repr))

        return h

    def count_tokens(
        self, messages: list[Message], trusted_token_usage: int = 0
    ) -> int:
        if trusted_token_usage > 0:
            return trusted_token_usage

        # 尝试从缓存获取
        cache_key = self._get_cache_key(messages)
        if cache_key in self._cache:
            self._hit_count += 1
            return self._cache[cache_key]

        self._miss_count += 1
        total = self._count_tokens_internal(messages)

        # 缓存结果
        if len(self._cache) < self._cache_size:
            self._cache[cache_key] = total
        elif self._cache_size > 0:
            # 简单的缓存淘汰: 清空一半
            keys_to_remove = list(self._cache.keys())[: self._cache_size // 2]
            for key in keys_to_remove:
                del self._cache[key]
            self._cache[cache_key] = total

        return total

    def _count_tokens_internal(self, messages: list[Message]) -> int:
        """Internal token counting implementation."""
        total = 0
        for msg in messages:
            message_tokens = 0

            content = msg.content
            if isinstance(content, str):
                message_tokens += self._estimate_tokens(content)
            elif isinstance(content, list):
                for part in content:
                    if isinstance(part, TextPart):
                        message_tokens += self._estimate_tokens(part.text)
                    elif isinstance(part, ThinkPart):
                        message_tokens += self._estimate_tokens(part.think)
                    elif isinstance(part, ImageURLPart):
                        message_tokens += IMAGE_TOKEN_ESTIMATE
                    elif isinstance(part, AudioURLPart):
                        message_tokens += AUDIO_TOKEN_ESTIMATE

            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_str = json.dumps(tc if isinstance(tc, dict) else tc.model_dump())
                    message_tokens += self._estimate_tokens(tc_str)

            # 添加每条消息的固定开销
            total += message_tokens + PER_MESSAGE_OVERHEAD

        return total

    def _estimate_tokens(self, text: str) -> int:
        """Estimate tokens using improved algorithm.

        Optimizations:
        - 更精确的中英文混合文本估算
        - 考虑特殊字符和数字
        - 使用更准确的比率
        """
        if not text:
            return 0

        chinese_count = 0
        english_count = 0
        digit_count = 0
        special_count = 0

        for c in text:
            if "\u4e00" <= c <= "\u9fff":
                chinese_count += 1
            elif c.isdigit():
                digit_count += 1
            elif c.isalpha():
                english_count += 1
            else:
                special_count += 1

        # 使用更精确的估算比率
        chinese_tokens = int(chinese_count * 0.55)
        english_tokens = int(english_count * 0.25)
        digit_tokens = int(digit_count * 0.4)
        special_tokens = int(special_count * 0.2)

        return chinese_tokens + english_tokens + digit_tokens + special_tokens

    def get_cache_stats(self) -> dict:
        """Get cache hit/miss statistics.

        Returns:
            Dictionary with cache stats.
        """
        total = self._hit_count + self._miss_count
        hit_rate = (self._hit_count / total * 100) if total > 0 else 0
        return {
            "hits": self._hit_count,
            "misses": self._miss_count,
            "hit_rate": f"{hit_rate:.1f}%",
            "cache_size": len(self._cache),
        }

    def clear_cache(self) -> None:
        """Clear the token count cache."""
        self._cache.clear()
        self._hit_count = 0
        self._miss_count = 0
