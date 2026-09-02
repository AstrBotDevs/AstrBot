import re
from typing import Any

from astrbot.core.db.po import UmoAlias

MAX_UMO_NAME_LENGTH = 255
_CONTROL_CHARACTERS_RE = re.compile(r"[\x00-\x1F\x7F-\x9F]")


def normalize_umo_name(name: Any) -> str:
    if name is None:
        return ""
    normalized = _CONTROL_CHARACTERS_RE.sub(" ", str(name)).strip()
    return normalized[:MAX_UMO_NAME_LENGTH]


def parse_umo(umo: Any) -> dict[str, str]:
    umo_str = "" if umo is None else str(umo)
    parts = umo_str.split(":")
    return {
        "platform": parts[0] if len(parts) >= 1 and parts[0] else "unknown",
        "message_type": parts[1] if len(parts) >= 2 and parts[1] else "unknown",
        "session_id": ":".join(parts[2:]) if len(parts) >= 3 else umo_str,
    }


def get_event_auto_name(event: Any, *, fallback_to_id: bool = True) -> str:
    """Resolve an automatic display name from inbound event metadata.

    Args:
        event: Platform event containing group and sender metadata.
        fallback_to_id: Whether to use the group or sender ID when no name exists.

    Returns:
        Normalized group or sender name, an optional ID fallback, or an empty string.
    """
    group_id = event.get_group_id() if hasattr(event, "get_group_id") else ""
    message_obj = getattr(event, "message_obj", None)
    group = getattr(message_obj, "group", None)

    if group_id:
        group_name = normalize_umo_name(getattr(group, "group_name", None))
        if group_name:
            return group_name
        return normalize_umo_name(group_id) if fallback_to_id else ""

    sender_name = ""
    if hasattr(event, "get_sender_name"):
        sender_name = event.get_sender_name()
    sender_id = event.get_sender_id() if hasattr(event, "get_sender_id") else ""
    normalized_sender_name = normalize_umo_name(sender_name)
    if normalized_sender_name:
        return normalized_sender_name
    return normalize_umo_name(sender_id) if fallback_to_id else ""


def get_umo_display_name(
    *,
    umo: str,
    auto_name: str | None = None,
    user_alias: str | None = None,
) -> str:
    return normalize_umo_name(user_alias) or normalize_umo_name(auto_name) or umo


def serialize_umo_alias(alias: UmoAlias | None, umo: str) -> dict[str, str]:
    auto_name = normalize_umo_name(alias.auto_name if alias else "")
    user_alias = normalize_umo_name(alias.user_alias if alias else "")
    return {
        "auto_name": auto_name,
        "user_alias": user_alias,
        "display_name": get_umo_display_name(
            umo=umo,
            auto_name=auto_name,
            user_alias=user_alias,
        ),
        "creator_sender_id": alias.creator_sender_id if alias else "",
    }


def build_umo_alias_map(aliases: list[UmoAlias]) -> dict[str, UmoAlias]:
    return {alias.umo: alias for alias in aliases}
