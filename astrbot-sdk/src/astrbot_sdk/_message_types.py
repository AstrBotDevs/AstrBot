from __future__ import annotations

from typing import Any

_GROUP_MESSAGE_TYPES = {"group", "groupmessage", "group_message"}
_PRIVATE_MESSAGE_TYPES = {
    "private",
    "privatemessage",
    "private_message",
    "friend",
    "friendmessage",
    "friend_message",
}
_OTHER_MESSAGE_TYPES = {"other", "othermessage", "other_message"}


def normalize_message_type(
    value: Any,
    *,
    group_id: str | None = None,
    user_id: str | None = None,
    empty_default: str = "",
) -> str:
    """Collapse SDK-visible message types to canonical values."""

    normalized = str(getattr(value, "value", value) or "").strip().lower()
    if normalized in _GROUP_MESSAGE_TYPES:
        return "group"
    if normalized in _PRIVATE_MESSAGE_TYPES:
        return "private"
    if normalized in _OTHER_MESSAGE_TYPES:
        return "other"
    if group_id:
        return "group"
    if user_id:
        return "private"
    if not normalized:
        return empty_default
    return "other"
