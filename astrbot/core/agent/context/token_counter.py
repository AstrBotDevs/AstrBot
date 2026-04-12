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
