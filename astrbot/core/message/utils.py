"""Message utilities for deduplication and component handling."""

import hashlib
from typing import Iterable

from astrbot.core.message.components import BaseMessageComponent, File, Image


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
