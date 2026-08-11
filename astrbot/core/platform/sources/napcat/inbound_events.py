"""Validation and dispatch of inbound OneBot v11 events from NapCat."""

from __future__ import annotations

import copy
import json
from collections.abc import Awaitable, Callable, Mapping
from time import monotonic
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, ValidationError

from astrbot import logger

from .codec import sanitize_segment_type
from .generated import ob11_events as ob11_models
from .generated.ob11_events import OB11AllEvent


class NapCatGenericEvent(BaseModel):
    """Forward-compatible representation for unknown non-message events."""

    model_config = ConfigDict(extra="allow")

    post_type: Literal["notice", "request", "meta_event"]
    self_id: int | str = 0
    time: int = 0
    notice_type: str | None = None
    request_type: str | None = None
    meta_event_type: str | None = None
    sub_type: str | None = None


NapCatInboundEvent = OB11AllEvent | NapCatGenericEvent

MESSAGE_EVENT_MODELS: dict[str, type[ob11_models.BaseModel]] = {
    "private": ob11_models.OB11PrivateMessage,
    "group": ob11_models.OB11GroupMessage,
}
NOTICE_EVENT_MODELS: dict[tuple[str, str | None], type[ob11_models.BaseModel]] = {
    ("bot_offline", None): ob11_models.OneBot11BotOffline,
    ("group_upload", None): ob11_models.OneBot11GroupUpload,
    ("group_admin", None): ob11_models.OneBot11GroupAdmin,
    ("group_decrease", None): ob11_models.OneBot11GroupDecrease,
    ("group_increase", None): ob11_models.OneBot11GroupIncrease,
    ("group_ban", None): ob11_models.OneBot11GroupBan,
    ("friend_add", None): ob11_models.OneBot11FriendAdd,
    ("group_recall", None): ob11_models.OneBot11GroupRecall,
    ("friend_recall", None): ob11_models.OneBot11FriendRecall,
    ("group_msg_emoji_like", None): ob11_models.OneBot11GroupMessageReaction,
    ("reaction", None): ob11_models.OneBot11GroupMessageReactionLagrange,
    ("essence", None): ob11_models.OneBot11GroupEssence,
    ("group_card", None): ob11_models.OneBot11GroupCard,
    ("notify", "poke"): ob11_models.OneBot11Poke,
    ("notify", "lucky_king"): ob11_models.OneBot11LuckyKing,
    ("notify", "honor"): ob11_models.OneBot11Honor,
    ("notify", "gray_tip"): ob11_models.OneBot11GroupGrayTip,
    ("notify", "group_name"): ob11_models.OneBot11GroupName,
    ("notify", "title"): ob11_models.OneBot11GroupTitle,
    ("notify", "input_status"): ob11_models.OneBot11InputStatus,
    ("notify", "profile_like"): ob11_models.OneBot11ProfileLike,
    ("online_file_receive", None): ob11_models.OneBot11OnlineFileReceive,
    ("online_file_send", None): ob11_models.OneBot11OnlineFileSend,
}
REQUEST_EVENT_MODELS: dict[str, type[ob11_models.BaseModel]] = {
    "friend": ob11_models.OneBot11FriendRequest,
    "group": ob11_models.OneBot11GroupRequest,
}
META_EVENT_MODELS: dict[str, type[ob11_models.BaseModel]] = {
    "lifecycle": ob11_models.OneBot11Lifecycle,
    "heartbeat": ob11_models.OneBot11Heartbeat,
}
GROUP_SENDER_ROLE_VALUES = frozenset({"owner", "admin", "member"})
FRIEND_SENDER_KEYS = frozenset(
    {"age", "card", "group_id", "nickname", "sex", "user_id"}
)
GROUP_SENDER_KEYS = frozenset(
    {"age", "area", "card", "level", "nickname", "role", "sex", "title", "user_id"}
)
NONSTANDARD_MESSAGE_SEGMENT_FALLBACK_TEXT: dict[str, str] = {
    "flash": "[FlashTransfer]",
}
KNOWN_MESSAGE_SEGMENT_TYPES = frozenset(
    {
        "anonymous",
        "at",
        "contact",
        "dice",
        "face",
        "file",
        "flashtransfer",
        "forward",
        "image",
        "json",
        "location",
        "markdown",
        "mface",
        "miniapp",
        "music",
        "node",
        "onlinefile",
        "poke",
        "record",
        "reply",
        "rps",
        "shake",
        "share",
        "text",
        "video",
        "xml",
    }
)


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_message_segment_for_validation(
    segment: Mapping[str, Any],
) -> tuple[dict[str, Any], str | None]:
    normalized_segment = dict(segment)
    raw_segment_type = _string_or_none(normalized_segment.get("type"))
    segment_type = (
        sanitize_segment_type(raw_segment_type)
        if raw_segment_type is not None
        else None
    )
    if not segment_type:
        return normalized_segment, None
    fallback_text = NONSTANDARD_MESSAGE_SEGMENT_FALLBACK_TEXT.get(segment_type)
    if fallback_text is None:
        if segment_type in KNOWN_MESSAGE_SEGMENT_TYPES:
            return normalized_segment, None
        return (
            {
                "type": "text",
                "data": {"text": f"[Unsupported NapCat segment: {segment_type}]"},
            },
            segment_type,
        )
    raw_data = normalized_segment.get("data")
    data = dict(raw_data) if isinstance(raw_data, Mapping) else {}
    if segment_type == "markdown":
        fallback_text = _string_or_none(data.get("content")) or fallback_text
    elif segment_type == "mface":
        fallback_text = _string_or_none(data.get("summary")) or fallback_text
    elif segment_type == "onlinefile":
        file_name = _string_or_none(data.get("fileName"))
        if file_name:
            fallback_text = f"[OnlineFile:{file_name}]"
    return {"type": "text", "data": {"text": fallback_text}}, segment_type


def _normalize_message_payload(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    normalized_payload = dict(payload)
    normalization_notes: list[str] = []
    message_type = _string_or_none(normalized_payload.get("message_type"))
    sender = normalized_payload.get("sender")
    sender_dict = dict(sender) if isinstance(sender, Mapping) else {}
    sender_user_id = sender_dict.get("user_id", normalized_payload.get("user_id"))
    if sender_user_id is not None and sender_dict.get("user_id") != sender_user_id:
        sender_dict["user_id"] = sender_user_id
        normalization_notes.append("filled sender.user_id from user_id")
    allowed_sender_keys = (
        GROUP_SENDER_KEYS if message_type == "group" else FRIEND_SENDER_KEYS
    )
    sender_extra_keys = sorted(
        key
        for key in sender_dict
        if isinstance(key, str) and key not in allowed_sender_keys
    )
    if sender_extra_keys:
        sender_dict = {
            key: value
            for key, value in sender_dict.items()
            if not isinstance(key, str) or key in allowed_sender_keys
        }
        normalization_notes.append(
            "dropped sender extra fields: " + ", ".join(sender_extra_keys)
        )
    if sender_dict.get("nickname") is None:
        sender_dict["nickname"] = ""
        normalization_notes.append("filled missing sender.nickname")
    if message_type == "group":
        role = _string_or_none(sender_dict.get("role"))
        if role not in GROUP_SENDER_ROLE_VALUES:
            sender_dict["role"] = "member"
            normalization_notes.append("defaulted sender.role to member")
    if sender_dict:
        normalized_payload["sender"] = sender_dict
    raw_segments = normalized_payload.get("message")
    if isinstance(raw_segments, list):
        normalized_segments: list[dict[str, Any] | Any] = []
        normalized_segment_types: list[str] = []
        for segment in raw_segments:
            if not isinstance(segment, Mapping):
                normalized_segments.append(segment)
                continue
            normalized_segment, normalized_segment_type = (
                _normalize_message_segment_for_validation(segment)
            )
            normalized_segments.append(normalized_segment)
            if normalized_segment_type is not None:
                normalized_segment_types.append(normalized_segment_type)
        if normalized_segment_types:
            normalized_payload["message"] = normalized_segments
            normalization_notes.append(
                "normalized nonstandard message segments: "
                + ", ".join(normalized_segment_types)
            )
    return normalized_payload, normalization_notes


def _select_event_model(
    payload: Mapping[str, Any],
) -> type[ob11_models.BaseModel] | None:
    post_type = _string_or_none(payload.get("post_type"))
    if post_type in {"message", "message_sent"}:
        return MESSAGE_EVENT_MODELS.get(
            _string_or_none(payload.get("message_type")) or ""
        )
    if post_type == "notice":
        notice_type = _string_or_none(payload.get("notice_type"))
        if not notice_type:
            return None
        sub_type = _string_or_none(payload.get("sub_type"))
        return NOTICE_EVENT_MODELS.get(
            (notice_type, sub_type)
        ) or NOTICE_EVENT_MODELS.get((notice_type, None))
    if post_type == "request":
        return REQUEST_EVENT_MODELS.get(
            _string_or_none(payload.get("request_type")) or ""
        )
    if post_type == "meta_event":
        return META_EVENT_MODELS.get(
            _string_or_none(payload.get("meta_event_type")) or ""
        )
    return None


def _validate_event(payload: Mapping[str, Any]) -> tuple[NapCatInboundEvent, str]:
    payload_dict = dict(payload)
    model_class = _select_event_model(payload_dict)
    if model_class is None:
        if _string_or_none(payload_dict.get("post_type")) in {
            "notice",
            "request",
            "meta_event",
        }:
            return (
                NapCatGenericEvent.model_validate(payload_dict),
                "NapCatGenericEvent",
            )
        return OB11AllEvent.model_validate(payload_dict, extra="ignore"), "OB11AllEvent"
    typed_event = cast(Any, model_class.model_validate(payload_dict, extra="ignore"))
    return OB11AllEvent(root=typed_event), model_class.__name__


async def dispatch_inbound_event(
    payload: Mapping[str, Any],
    on_event: Callable[[NapCatInboundEvent], Awaitable[None]],
    *,
    started_at: float,
    validation_slow_log_threshold_s: float,
    payload_handle_slow_log_threshold_s: float,
) -> bool:
    """Validate and dispatch an inbound event; return false for API responses."""
    if "post_type" not in payload:
        return False
    validation_started_at = monotonic()
    validation_payload = dict(payload)
    normalization_notes: list[str] = []
    if payload.get("post_type") in {"message", "message_sent"}:
        validation_payload, normalization_notes = _normalize_message_payload(payload)
        if normalization_notes:
            logger.info(
                "[NapCat] Forward WebSocket normalized inbound %s payload before validation: %s",
                payload.get("message_type", "message"),
                "; ".join(normalization_notes),
            )
    event_model = _select_event_model(validation_payload)
    try:
        event, event_model_name = _validate_event(validation_payload)
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {}
        error_location = ".".join(str(part) for part in first_error.get("loc", ()))
        payload_excerpt = json.dumps(validation_payload, ensure_ascii=False)[:1200]
        logger.warning(
            "[NapCat] Forward WebSocket rejected event payload: model=%s post_type=%s message_type=%s notice_type=%s request_type=%s meta_event_type=%s error=%s loc=%s payload=%s",
            event_model.__name__ if event_model is not None else "OB11AllEvent",
            validation_payload.get("post_type"),
            validation_payload.get("message_type"),
            validation_payload.get("notice_type"),
            validation_payload.get("request_type"),
            validation_payload.get("meta_event_type"),
            first_error.get("msg", exc),
            error_location or "<unknown>",
            payload_excerpt,
        )
        return True
    validation_elapsed = monotonic() - validation_started_at
    if validation_elapsed >= validation_slow_log_threshold_s:
        logger.info(
            "[NapCat] Slow payload validation: post_type=%s message_type=%s notice_type=%s request_type=%s elapsed=%.2fs",
            validation_payload.get("post_type"),
            validation_payload.get("message_type"),
            validation_payload.get("notice_type"),
            validation_payload.get("request_type"),
            validation_elapsed,
        )
    logger.debug("[NapCat] Forward WebSocket validated event with %s", event_model_name)
    # Keep the exact wire payload alongside the validated model.  Generated
    # models intentionally ignore unknown fields; the plugin DTO must not.
    try:
        raw_payload = copy.deepcopy(payload)
        object.__setattr__(event, "__astrbot_raw_payload__", raw_payload)
        root = getattr(event, "root", None)
        if root is not None:
            object.__setattr__(
                root, "__astrbot_raw_payload__", copy.deepcopy(raw_payload)
            )
    except Exception:
        # A future generated model may disallow private attributes.  The
        # adapter still receives the validated event and can use model_dump.
        pass
    await on_event(event)
    elapsed = monotonic() - started_at
    if elapsed >= payload_handle_slow_log_threshold_s:
        logger.info(
            "[NapCat] Slow payload handling: post_type=%s message_type=%s notice_type=%s request_type=%s elapsed=%.2fs",
            validation_payload.get("post_type"),
            validation_payload.get("message_type"),
            validation_payload.get("notice_type"),
            validation_payload.get("request_type"),
            elapsed,
        )
    return True
