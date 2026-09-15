"""Validate image bytes independently from text-token estimates."""

from collections.abc import Sequence

from astrbot.core.agent.message import ImageMediaRefPart, ImageURLPart, Message
from astrbot.core.utils.media_utils import (
    IMAGE_COMPRESS_DEFAULT_MAX_ENCODED_BYTES,
    ImagePayloadTooLargeError,
)


def validate_context_image_bytes(
    messages: Sequence[Message | dict],
    max_encoded_bytes: int = IMAGE_COMPRESS_DEFAULT_MAX_ENCODED_BYTES,
) -> int:
    """Validate selected images without loading or rewriting historical bytes.

    Args:
        messages: Selected main or summary request messages.
        max_encoded_bytes: Maximum Base64 bytes for a single image.

    Returns:
        Total known encoded-image bytes, excluding JSON and data URI headers.
        Remote URLs have unknown size until resolved and are not counted.

    Raises:
        ImagePayloadTooLargeError: A selected image exceeds the single-image cap.
        ValueError: The configured cap is invalid.
    """
    if isinstance(max_encoded_bytes, bool) or max_encoded_bytes < 1:
        raise ValueError("Image byte budget must be a positive integer")
    total = 0
    for message in messages:
        parts = (
            message.content if isinstance(message, Message) else message.get("content")
        )
        if not isinstance(parts, list):
            continue
        for part in parts:
            size = 0
            url = None
            if isinstance(part, ImageMediaRefPart):
                size = 4 * ((part.byte_size + 2) // 3)
            elif isinstance(part, ImageURLPart):
                url = part.image_url.url
            elif isinstance(part, dict):
                if part.get("type") == "image_media_ref":
                    size = 4 * ((int(part["byte_size"]) + 2) // 3)
                elif part.get("type") == "image_url":
                    image_url = part.get("image_url")
                    url = (
                        image_url.get("url")
                        if isinstance(image_url, dict)
                        else image_url
                    )
            if isinstance(url, str) and url.startswith("data:image/"):
                comma = url.find(",")
                if comma >= 0 and ";base64" in url[:comma]:
                    # Do not slice the full Base64 suffix merely to count it.
                    size = len(url) - comma - 1
            if size > max_encoded_bytes:
                raise ImagePayloadTooLargeError(
                    f"A selected image uses {size} Base64 bytes, exceeding the "
                    f"{max_encoded_bytes}-byte limit. Historical images were not changed."
                )
            total += size
    return total
