THREAD_SESSION_MARKER = "__thread__"


def encode_thread_session_id(channel_id: str, thread_ts: str) -> str:
    if not channel_id or not thread_ts:
        return channel_id
    return f"{channel_id}{THREAD_SESSION_MARKER}{thread_ts}"


def decode_slack_session_id(session_id: str) -> tuple[str, str | None]:
    if not session_id:
        return "", None

    if THREAD_SESSION_MARKER in session_id:
        channel_id, thread_ts = session_id.split(THREAD_SESSION_MARKER, 1)
        if channel_id and thread_ts:
            return channel_id, thread_ts

    # Backward compatibility for historical IDs like "group_<channel_id>".
    if "_" in session_id:
        return session_id.rsplit("_", 1)[-1], None

    return session_id, None
