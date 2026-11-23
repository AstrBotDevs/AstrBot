from __future__ import annotations

from astrbot.core.utils.quoted_message.extractor import (
    extract_quoted_message_images,
    extract_quoted_message_text,
)
from astrbot.core.utils.quoted_message.forward_extractor import (
    extract_forward_messages,
    format_forward_content_part,
    has_forward_components,
    is_forward_content_injected,
)

__all__ = [
    "extract_forward_messages",
    "extract_quoted_message_images",
    "extract_quoted_message_text",
    "format_forward_content_part",
    "has_forward_components",
    "is_forward_content_injected",
]
