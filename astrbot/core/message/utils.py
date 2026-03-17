"""Message utilities for deduplication and component handling."""

import hashlib
from collections.abc import Iterable
from typing import TYPE_CHECKING

from astrbot.core.message.components import BaseMessageComponent, File, Image

if TYPE_CHECKING:
    from astrbot.core.platform import AstrMessageEvent


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


def build_event_content_dedup_key(event: "AstrMessageEvent") -> str:
    """Build a content fingerprint key for EventBus deduplication."""
    msg_text = str(event.get_message_str() or "").strip()
    if len(msg_text) <= _MAX_RAW_TEXT_FINGERPRINT_LEN:
        msg_sig = msg_text
    else:
        msg_hash = hashlib.sha1(msg_text.encode("utf-8")).hexdigest()[:16]
        msg_sig = f"h:{len(msg_text)}:{msg_hash}"

    attach_sig = build_component_dedup_signature(event.get_messages())
    platform_id = str(event.get_platform_id() or "")
    unified_msg_origin = str(event.unified_msg_origin or "")
    sender_id = str(event.get_sender_id() or "")
    return "|".join(
        [
            "content",
            platform_id,
            unified_msg_origin,
            sender_id,
            msg_sig,
            attach_sig,
        ]
    )


def build_event_message_id_dedup_key(event: "AstrMessageEvent") -> str | None:
    """Build a message_id fingerprint key for EventBus deduplication."""
    message_id = str(getattr(event.message_obj, "message_id", "") or "")
    if not message_id:
        message_id = str(getattr(event.message_obj, "id", "") or "")
    if not message_id:
        return None

    platform_id = str(event.get_platform_id() or "")
    unified_msg_origin = str(event.unified_msg_origin or "")
    return "|".join(
        [
            "message_id",
            platform_id,
            unified_msg_origin,
            message_id,
        ]
    )
