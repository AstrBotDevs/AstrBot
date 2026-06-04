from typing import Any

from astrbot.core.db.po import UmoAlias

MAX_UMO_NAME_LENGTH = 255


def normalize_umo_name(name: str | None) -> str:
    return (name or "").strip()[:MAX_UMO_NAME_LENGTH]


def get_event_auto_name(event: Any) -> str:
    group_id = event.get_group_id() if hasattr(event, "get_group_id") else ""
    message_obj = getattr(event, "message_obj", None)
    group = getattr(message_obj, "group", None)

    if group_id:
        group_name = normalize_umo_name(getattr(group, "group_name", None))
        return group_name or normalize_umo_name(group_id)

    sender_name = ""
    if hasattr(event, "get_sender_name"):
        sender_name = event.get_sender_name()
    sender_id = event.get_sender_id() if hasattr(event, "get_sender_id") else ""
    return normalize_umo_name(sender_name) or normalize_umo_name(sender_id)


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
