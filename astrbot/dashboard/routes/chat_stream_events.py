from astrbot.core.utils.datetime_utils import to_utc_isoformat


def build_message_saved_event(record, role: str, *, chat_ct: bool = False) -> dict:
    payload = {
        "type": "message_saved",
        "data": {
            "id": record.id,
            "created_at": to_utc_isoformat(record.created_at),
            "role": role,
        },
    }
    if chat_ct:
        payload["ct"] = "chat"
    return payload
