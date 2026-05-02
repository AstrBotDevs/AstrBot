from astrbot.core.utils.datetime_utils import to_utc_isoformat


def build_message_saved_event(
    saved_record,
    refs: dict | None = None,
    *,
    llm_checkpoint_id: str | None = None,
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
    if llm_checkpoint_id is not None:
        payload["data"]["llm_checkpoint_id"] = llm_checkpoint_id
    if chat_mode:
        payload["ct"] = "chat"
    return payload
