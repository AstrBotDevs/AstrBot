from __future__ import annotations

from astrbot.core.utils.quoted_message.extractor import (
    extract_quoted_message_images,
    extract_quoted_message_text,
)
from astrbot.core.utils.quoted_message.image_resolver import ImageResolver

__all__ = [
    "extract_quoted_message_text",
    "extract_quoted_message_images",
    "ImageResolver",
]
