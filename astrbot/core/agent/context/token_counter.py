import copy
import json
import re
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

# An emoji costs about 2 tokens per character under common BPE tokenizers, and
# flag or zero width joiner sequences cost more. The plain text rate of 0.3
# underestimates an emoji heavy context by an order of magnitude.
EMOJI_TOKEN_ESTIMATE = 2.0

# Emoji blocks, the miscellaneous symbols and dingbats block, the variation
# selectors and the zero width joiner that build flag and multi person emoji.
EMOJI_PATTERN = re.compile("[\u200d\u2600-\u27bf\ufe00-\ufe0f\U0001f000-\U0001faff]")


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
        emoji_count = len(EMOJI_PATTERN.findall(text))
        other_count = len(text) - chinese_count - emoji_count
        return int(
            chinese_count * 0.6 + emoji_count * EMOJI_TOKEN_ESTIMATE + other_count * 0.3
        )


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


async def count_projected_tokens(
    messages, image_context, token_counter, *, provider=None
) -> int:
    """Count projected visual inputs using their prepared image dimensions.

    Args:
        messages: Request-only messages returned by ``project_messages``.
        image_context: Turn state containing current inputs not already projected.
        token_counter: Text and non-image token counter.
        provider: Optional model used for this projection instead of the active chat model.

    Returns:
        Estimated total tokens, counting every image position in the request.
    """
    provider = provider or image_context.provider
    modalities = getattr(provider, "provider_config", {}).get("modalities")
    supports_image = (not modalities or "image" in modalities) and getattr(
        provider, "image_request_budget_supported", False
    ) is True
    projected = copy.deepcopy(messages)
    previews = []
    projected_occurrences = set(image_context.projected_visuals)
    for message in projected:
        if not isinstance(message.content, list):
            continue
        kept_parts = []
        for part in message.content:
            if isinstance(part, ImageURLPart):
                if (
                    supports_image
                    and image_context.projected_visuals.get(part.image_url.id)
                    == part.image_url.url
                ):
                    previews.append(part.image_url.url)
            else:
                kept_parts.append(part)
        message.content = kept_parts or ""

    if supports_image:
        previews.extend(
            preview
            for occurrence, preview in image_context.pending_visuals.items()
            if occurrence not in projected_occurrences
            and occurrence not in image_context.revoked_occurrences
        )

    estimates = await estimate_preview_tokens(previews)
    unknown_tokens = estimates["unknown_images"] * IMAGE_TOKEN_ESTIMATE
    return token_counter.count_tokens(projected) + estimates["tokens"] + unknown_tokens
