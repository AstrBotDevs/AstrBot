"""Provider-facing sanitization for persisted agent history."""

import re
from copy import deepcopy

IMAGE_HISTORY_PLACEHOLDER = "[image omitted]"
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:[\\/]")


def sanitize_history_for_storage(messages: list[dict]) -> list[dict]:
    """Replace transient image data and local paths in persisted history.

    The input is copied before it is changed so the current agent loop keeps its
    complete, in-memory image data for the rest of the request.

    Args:
        messages: Serialized provider messages.

    Returns:
        A copied message list with base64 image URLs replaced.
    """
    sanitized = deepcopy(messages)
    for message in sanitized:
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            image_url = part.get("image_url")
            if not isinstance(image_url, dict):
                continue
            url = image_url.get("url")
            if (
                isinstance(url, str)
                and (
                    (url.startswith("data:image/") and ";base64," in url)
                    or url.startswith(("file://", "/"))
                    or bool(_WINDOWS_ABSOLUTE_PATH_RE.match(url))
                )
            ):
                image_url["url"] = IMAGE_HISTORY_PLACEHOLDER
    return sanitized
