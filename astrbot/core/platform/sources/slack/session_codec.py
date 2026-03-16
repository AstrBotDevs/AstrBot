THREAD_SESSION_MARKER = "__thread__"
LEGACY_GROUP_SESSION_PREFIX = "group_"
SLACK_DEFAULT_TEXT_FALLBACKS = {
    "safe_text": "message",
    "image": "[image]",
    "file_template": "[file:{name}]",
    "generic": "[message]",
    "image_upload_failed": "Image upload failed",
    "file_upload_failed": "File upload failed",
}
SLACK_SAFE_TEXT_FALLBACK = SLACK_DEFAULT_TEXT_FALLBACKS["safe_text"]


def build_slack_text_fallbacks(overrides: dict | None = None) -> dict[str, str]:
    text_fallbacks = dict(SLACK_DEFAULT_TEXT_FALLBACKS)
    if not isinstance(overrides, dict):
        return text_fallbacks

    for key in text_fallbacks:
        candidate = overrides.get(key)
        if isinstance(candidate, str) and candidate.strip():
            text_fallbacks[key] = candidate
    return text_fallbacks


def encode_thread_session_id(channel_id: str, thread_ts: str) -> str:
    if not channel_id or not thread_ts:
        return channel_id
    return f"{channel_id}{THREAD_SESSION_MARKER}{thread_ts}"


def _decode_thread_session_id(session_id: str) -> tuple[str, str | None] | None:
    if THREAD_SESSION_MARKER not in session_id:
        return None
    channel_id, thread_ts = session_id.split(THREAD_SESSION_MARKER, 1)
    return channel_id, thread_ts or None


def _decode_legacy_session_id(session_id: str) -> tuple[str, str | None] | None:
    if not session_id.startswith(LEGACY_GROUP_SESSION_PREFIX):
        return None
    return session_id[len(LEGACY_GROUP_SESSION_PREFIX) :], None


def decode_slack_session_id(session_id: str) -> tuple[str, str | None]:
    if not session_id:
        return "", None

    decoded_thread_session = _decode_thread_session_id(session_id)
    if decoded_thread_session is not None:
        return decoded_thread_session

    decoded_legacy_session = _decode_legacy_session_id(session_id)
    if decoded_legacy_session is not None:
        return decoded_legacy_session

    return session_id, None


def _extract_raw_target(raw_message: dict | None) -> tuple[str, str | None]:
    if not isinstance(raw_message, dict):
        return "", None

    raw_channel_id = ""
    raw_thread_ts = None

    raw_channel = raw_message.get("channel")
    if raw_channel is not None and raw_channel != "":
        raw_channel_id = str(raw_channel)

    raw_thread = raw_message.get("thread_ts")
    if raw_thread is not None and raw_thread != "":
        raw_thread_ts = str(raw_thread)

    return raw_channel_id, raw_thread_ts


def _resolve_target_with_precedence(
    *,
    session_id: str,
    raw_message: dict | None = None,
    group_id: str = "",
    fallback_channel_id: str = "",
) -> tuple[str, str | None]:
    """Resolve Slack target with a single precedence chain.

    Precedence for channel: `group_id > raw_message.channel > parsed(session_id) > fallback_channel_id`.
    Precedence for thread: `raw_message.thread_ts > parsed(session_id)`.
    """
    parsed_channel_id, parsed_thread_ts = decode_slack_session_id(session_id)
    raw_channel_id, raw_thread_ts = _extract_raw_target(raw_message)

    channel_id = group_id or raw_channel_id or parsed_channel_id or fallback_channel_id
    return channel_id, raw_thread_ts or parsed_thread_ts


def resolve_target_from_event(
    *,
    session_id: str,
    raw_message: dict,
    group_id: str = "",
) -> tuple[str, str | None]:
    """Resolve target for received Slack events (uses event raw payload)."""
    return _resolve_target_with_precedence(
        session_id=session_id,
        raw_message=raw_message,
        group_id=group_id,
    )


def resolve_target_from_session(
    *,
    session_id: str,
    group_id: str = "",
    fallback_channel_id: str = "",
) -> tuple[str, str | None]:
    """Resolve target when only session metadata is available (no raw event)."""
    return _resolve_target_with_precedence(
        session_id=session_id,
        group_id=group_id,
        fallback_channel_id=fallback_channel_id,
    )


def resolve_slack_message_target(
    session_id: str,
    *,
    raw_message: dict | None = None,
    group_id: str = "",
    sender_id: str = "",
) -> tuple[str, str | None]:
    """Backward-compatible resolver shared by legacy and new Slack call sites."""
    return _resolve_target_with_precedence(
        session_id=session_id,
        raw_message=raw_message,
        group_id=group_id,
        fallback_channel_id=sender_id,
    )
