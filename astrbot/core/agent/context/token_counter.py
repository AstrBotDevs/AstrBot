import json
from typing import Protocol, runtime_checkable

from ..message import (
    AudioURLPart,
    ImageRefPart,
    ImageURLPart,
    Message,
    TextPart,
    ThinkPart,
)


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
                    elif isinstance(part, ImageRefPart):
                        total += self._estimate_tokens(part.to_text())
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


async def estimate_preview_tokens(previews) -> dict:
    """Estimate visual context from local preview dimensions, never encoded length.

    Args:
        previews: Trusted local model-preview paths, one per image submission.

    Returns:
        Heuristic tokens and per-image dimensions; unknown images are explicit.
        This model-independent tile heuristic is not a provider pricing formula.
        Unknown images contribute no invented tokens; byte/count budgets still apply.
    """
    import asyncio
    from pathlib import Path

    from PIL import Image

    from astrbot.core.utils.media_utils import is_recoverable_image_error

    def inspect():
        images = []
        for preview in previews:
            item = {"status": "unknown", "tokens": None, "width": None, "height": None}
            try:
                # This estimator must never download URLs or decode inline base64.
                if isinstance(preview, (str, Path)) and not str(preview).startswith(
                    ("data:", "http:", "https:", "base64:")
                ):
                    with Image.open(Path(preview)) as image:
                        width, height = image.size
                    if width > 0 and height > 0:
                        item = {
                            "status": "heuristic",
                            "width": width,
                            "height": height,
                            "tokens": 256
                            * (1 + ((width + 511) // 512) * ((height + 511) // 512)),
                        }
            except OSError as exc:
                if not is_recoverable_image_error(exc):
                    raise
            except (ValueError, TypeError):
                pass
            images.append(item)
        unknown = sum(item["status"] == "unknown" for item in images)
        return {
            "tokens": sum(item["tokens"] or 0 for item in images),
            "status": "unknown" if unknown else "heuristic",
            "unknown_images": unknown,
            "images": images,
        }

    # Only metadata is inspected; decompression and provider requests are excluded.
    previews = tuple(previews)
    return await asyncio.to_thread(inspect)
