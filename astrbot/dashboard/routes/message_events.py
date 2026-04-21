from astrbot.core.utils.datetime_utils import to_utc_isoformat


def build_message_saved_event(
    saved_record,
    refs: dict | None = None,
    *,
    chat_mode: bool = False,
) -> dict:
    payload = {
        "type": "message_saved",
        "data": {
            "id": saved_record.id,
            "created_at": to_utc_isoformat(saved_record.created_at),
        },
    }
    if refs:
        payload["data"]["refs"] = refs
    if chat_mode:
        payload["ct"] = "chat"
    return payload
