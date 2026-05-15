"""Message utilities for deduplication and component handling."""

import hashlib
from collections.abc import Iterable

from astrbot.core.message.components import BaseMessageComponent, File, Image

_MAX_RAW_TEXT_FINGERPRINT_LEN = 256


def build_component_dedup_signature(
    components: Iterable[BaseMessageComponent],
) -> str:
    """Build a deduplication signature from message components.

    This function extracts unique identifiers from Image and File components
    and creates a hash-based signature for deduplication purposes.

    Args:
        components: An iterable of message components to analyze.

    Returns:
        A SHA1 hash (16 hex characters) representing the component signatures,
        or an empty string if no valid components are found.
    """
    parts: list[str] = []
    for component in components:
        if isinstance(component, Image):
            # Image can have url, file, or file_unique
            ref = component.url or component.file or component.file_unique or ""
            if ref:
                parts.append(f"img:{ref}")
        elif isinstance(component, File):
            # File can have url, file (via property), or name
            ref = component.url or component.file or component.name or ""
            if ref:
                parts.append(f"file:{ref}")
        # Future component types can be added here

    if not parts:
        return ""

    payload = "|".join(parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def build_sender_content_dedup_key(content: str, sender_id: str) -> str | None:
    """Build a sender+content hash key for short-window deduplication."""
    if not (content and sender_id):
        return None
    content_hash = hashlib.sha1(content.encode("utf-8")).hexdigest()[:16]
    return f"{sender_id}:{content_hash}"


def build_content_dedup_key(
    *,
    platform_id: str,
    unified_msg_origin: str,
    sender_id: str,
    text: str,
    components: Iterable[BaseMessageComponent],
) -> str:
    """Build a content fingerprint key for event deduplication."""
    msg_text = str(text or "").strip()
    if len(msg_text) <= _MAX_RAW_TEXT_FINGERPRINT_LEN:
        msg_sig = msg_text
    else:
        msg_hash = hashlib.sha1(msg_text.encode("utf-8")).hexdigest()[:16]
        msg_sig = f"h:{len(msg_text)}:{msg_hash}"

    attach_sig = build_component_dedup_signature(components)
    return "|".join(
        [
            "content",
            str(platform_id or ""),
            str(unified_msg_origin or ""),
            str(sender_id or ""),
            msg_sig,
            attach_sig,
        ]
    )


def build_message_id_dedup_key(
    *,
    platform_id: str,
    unified_msg_origin: str,
    message_id: str,
) -> str | None:
    """Build a message_id fingerprint key for event deduplication."""
    normalized_message_id = str(message_id or "")
    if not normalized_message_id:
        return None
    return "|".join(
        [
            "message_id",
            str(platform_id or ""),
            str(unified_msg_origin or ""),
            normalized_message_id,
        ]
    )
