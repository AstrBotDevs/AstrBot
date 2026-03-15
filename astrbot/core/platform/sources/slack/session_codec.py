THREAD_SESSION_MARKER = "__thread__"
LEGACY_GROUP_SESSION_PREFIX = "group_"
SLACK_SAFE_TEXT_FALLBACK = "message"


def encode_thread_session_id(channel_id: str, thread_ts: str) -> str:
    if not channel_id or not thread_ts:
        return channel_id
    return f"{channel_id}{THREAD_SESSION_MARKER}{thread_ts}"


def decode_slack_session_id(session_id: str) -> tuple[str, str | None]:
    if not session_id:
        return "", None

    if THREAD_SESSION_MARKER in session_id:
        channel_id, thread_ts = session_id.split(THREAD_SESSION_MARKER, 1)
        # Do not fallback to legacy parsing once thread marker is detected.
        # Keep decoded channel_id even if thread_ts is missing.
        return channel_id, thread_ts or None

    # Backward compatibility for historical IDs like "group_<channel_id>".
    if session_id.startswith(LEGACY_GROUP_SESSION_PREFIX):
        return session_id[len(LEGACY_GROUP_SESSION_PREFIX) :], None

    return session_id, None


def resolve_slack_message_target(
    session_id: str,
    *,
    raw_message: dict | None = None,
    group_id: str = "",
    sender_id: str = "",
) -> tuple[str, str | None]:
    parsed_channel_id, parsed_thread_ts = decode_slack_session_id(session_id)

    raw_channel_id = ""
    raw_thread_ts = None
    if isinstance(raw_message, dict):
        raw_channel = raw_message.get("channel")
        if raw_channel is not None and raw_channel != "":
            raw_channel_id = str(raw_channel)
        raw_thread = raw_message.get("thread_ts")
        if raw_thread is not None and raw_thread != "":
            raw_thread_ts = str(raw_thread)

    channel_id = group_id or raw_channel_id or parsed_channel_id or sender_id
    return channel_id, raw_thread_ts or parsed_thread_ts
