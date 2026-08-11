"""Stable, source-independent OneBot v11 contracts.

The generated NapCat models deliberately do not appear in this module.  These
small DTOs are the compatibility boundary between an adapter and plugins.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from astrbot.core.utils.error_redaction import redact_sensitive_text

type JsonValue = (
    None
    | bool
    | int
    | float
    | str
    | list["JsonValue"]
    | tuple["JsonValue", ...]
    | Mapping[str, "JsonValue"]
)

ONEBOT_SDK_VERSION = "1.0"


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, list | tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _copy_json(value: Any) -> Any:
    """Copy JSON-shaped wire data without relying on mutable model internals."""
    if isinstance(value, Mapping):
        return {str(key): _copy_json(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_copy_json(item) for item in value]
    return value


def _id(value: Any) -> str | None:
    if value is None:
        return None
    text = str(getattr(value, "value", value)).strip()
    return text or None


def _time(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except TypeError, ValueError, OverflowError:
        return None


@dataclass(frozen=True, slots=True)
class OneBotSegment:
    type: str
    data: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "type", str(self.type))
        object.__setattr__(self, "data", _freeze(dict(self.data)))

    @classmethod
    def from_value(cls, value: Any) -> OneBotSegment:
        if isinstance(value, Mapping):
            segment_type = str(value.get("type", "unknown"))
            data = value.get("data", {})
            return cls(segment_type, data if isinstance(data, Mapping) else {})
        return cls("unknown", {"value": value})


@dataclass(frozen=True, slots=True)
class OneBotSender:
    user_id: str
    nickname: str | None = None
    card: str | None = None
    role: str | None = None
    sex: str | None = None
    age: int | None = None
    extra: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _id(self.user_id) or "")
        object.__setattr__(self, "extra", _freeze(dict(self.extra)))

    @classmethod
    def from_value(cls, value: Any) -> OneBotSender | None:
        if not isinstance(value, Mapping):
            return None
        known = {"user_id", "nickname", "card", "role", "sex", "age"}
        return cls(
            user_id=_id(value.get("user_id")) or "",
            nickname=_id(value.get("nickname")),
            card=_id(value.get("card")),
            role=_id(value.get("role")),
            sex=_id(value.get("sex")),
            age=value.get("age") if isinstance(value.get("age"), int) else None,
            extra={k: v for k, v in value.items() if k not in known},
        )


@dataclass(frozen=True, slots=True)
class OneBotEvent:
    protocol: Literal["onebot.v11"] = "onebot.v11"
    schema_version: int = 1
    post_type: str = "unknown"
    self_id: str = ""
    time: int | None = None
    message_type: str | None = None
    notice_type: str | None = None
    request_type: str | None = None
    sub_type: str | None = None
    payload: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.protocol != "onebot.v11":
            raise ValueError("OneBot event protocol must be onebot.v11")
        if self.schema_version < 1:
            raise ValueError("OneBot event schema_version must be positive")
        object.__setattr__(self, "self_id", _id(self.self_id) or "")
        object.__setattr__(self, "time", _time(self.time))
        for name in ("message_type", "notice_type", "request_type", "sub_type"):
            object.__setattr__(self, name, _id(getattr(self, name)))
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> OneBotEvent:
        data = _copy_json(payload)
        post_type = str(data.get("post_type", "unknown"))
        if post_type in {"message", "message_sent"}:
            return OneBotMessageEvent._from_payload(data)
        if post_type == "notice":
            return OneBotNoticeEvent._from_payload(data)
        if post_type == "request":
            return OneBotRequestEvent._from_payload(data)
        if post_type == "meta_event":
            return OneBotMetaEvent._from_payload(data)
        return cls(
            post_type=post_type,
            self_id=_id(data.get("self_id")) or "",
            time=_time(data.get("time")),
            message_type=_id(data.get("message_type")),
            notice_type=_id(data.get("notice_type")),
            request_type=_id(data.get("request_type")),
            sub_type=_id(data.get("sub_type")),
            payload=data,
        )


@dataclass(frozen=True, slots=True)
class OneBotMessageEvent(OneBotEvent):
    message_id: str | None = None
    real_id: str | None = None
    message_seq: str | None = None
    user_id: str | None = None
    group_id: str | None = None
    sender: OneBotSender | None = None
    segments: tuple[OneBotSegment, ...] = ()
    message_format: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("message_id", "real_id", "message_seq", "user_id", "group_id"):
            object.__setattr__(self, name, _id(getattr(self, name)))
        object.__setattr__(
            self,
            "segments",
            tuple(
                segment
                if isinstance(segment, OneBotSegment)
                else OneBotSegment.from_value(segment)
                for segment in self.segments
            ),
        )

    @classmethod
    def _from_payload(cls, data: dict[str, Any]) -> OneBotMessageEvent:
        raw_segments = data.get("message")
        if isinstance(raw_segments, str):
            segments = (OneBotSegment("text", {"text": raw_segments}),)
        elif isinstance(raw_segments, (list, tuple)):
            segments = tuple(OneBotSegment.from_value(item) for item in raw_segments)
        else:
            segments = ()
        sender_mapping = data.get("sender")
        sender_user_id = (
            _id(sender_mapping.get("user_id"))
            if isinstance(sender_mapping, Mapping)
            else None
        )
        return cls(
            post_type=str(data.get("post_type", "message")),
            self_id=_id(data.get("self_id")) or "",
            time=_time(data.get("time")),
            message_type=_id(data.get("message_type")),
            sub_type=_id(data.get("sub_type")),
            payload=data,
            message_id=_id(data.get("message_id")),
            real_id=_id(data.get("real_id")),
            message_seq=_id(data.get("message_seq")),
            user_id=_id(data.get("user_id")) or sender_user_id,
            group_id=_id(data.get("group_id")),
            sender=OneBotSender.from_value(data.get("sender")),
            segments=segments,
            message_format=_id(data.get("message_format")),
        )


@dataclass(frozen=True, slots=True)
class OneBotNoticeEvent(OneBotEvent):
    notice_type: str | None = None
    notice_ids: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        super().__post_init__()
        object.__setattr__(self, "notice_ids", _freeze(dict(self.notice_ids)))

    @classmethod
    def _from_payload(cls, data: dict[str, Any]) -> OneBotNoticeEvent:
        ids = {
            key: _id(data[key]) or ""
            for key in ("user_id", "group_id", "operator_id", "message_id", "target_id")
            if key in data and _id(data[key]) is not None
        }
        return cls(
            post_type="notice",
            self_id=_id(data.get("self_id")) or "",
            time=_time(data.get("time")),
            notice_type=_id(data.get("notice_type")),
            sub_type=_id(data.get("sub_type")),
            payload=data,
            notice_ids=ids,
        )


@dataclass(frozen=True, slots=True)
class OneBotRequestEvent(OneBotEvent):
    request_type: str | None = None
    flag: str | None = None
    user_id: str | None = None
    group_id: str | None = None
    comment: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()
        for name in ("flag", "user_id", "group_id", "comment"):
            object.__setattr__(self, name, _id(getattr(self, name)))

    @classmethod
    def _from_payload(cls, data: dict[str, Any]) -> OneBotRequestEvent:
        return cls(
            post_type="request",
            self_id=_id(data.get("self_id")) or "",
            time=_time(data.get("time")),
            request_type=_id(data.get("request_type")),
            sub_type=_id(data.get("sub_type")),
            payload=data,
            flag=_id(data.get("flag")),
            user_id=_id(data.get("user_id")),
            group_id=_id(data.get("group_id")),
            comment=_id(data.get("comment")),
        )


@dataclass(frozen=True, slots=True)
class OneBotMetaEvent(OneBotEvent):
    meta_event_type: str | None = None

    def __post_init__(self) -> None:
        super().__post_init__()

    @classmethod
    def _from_payload(cls, data: dict[str, Any]) -> OneBotMetaEvent:
        return cls(
            post_type="meta_event",
            self_id=_id(data.get("self_id")) or "",
            time=_time(data.get("time")),
            sub_type=_id(data.get("sub_type")),
            payload=data,
            meta_event_type=_id(data.get("meta_event_type")),
        )


@dataclass(frozen=True, slots=True)
class OneBotActionResult:
    action: str
    data: JsonValue = None
    retcode: int | None = None
    status: str | None = None
    payload: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "action", str(self.action))
        object.__setattr__(self, "data", _freeze(self.data))
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class OneBotMessageReceipt:
    message_id: str | None
    res_id: str | None = None
    forward_id: str | None = None
    payload: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "message_id", _id(self.message_id))
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class OneBotFileResult:
    file_id: str | None = None
    url: str | None = None
    file: str | None = None
    payload: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_id", _id(self.file_id))
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class OneBotGroupInfo:
    """Stable group-directory result independent of NapCat response shapes."""

    group_id: str
    group_name: str | None = None
    member_count: int | None = None
    max_member_count: int | None = None
    payload: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_id", _id(self.group_id) or "")
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> OneBotGroupInfo:
        return cls(
            group_id=_id(value.get("group_id")) or "",
            group_name=_id(value.get("group_name")),
            member_count=_time(value.get("member_count")),
            max_member_count=_time(value.get("max_member_count")),
            payload=_copy_json(value),
        )


@dataclass(frozen=True, slots=True)
class OneBotMemberInfo:
    """Stable member/profile result independent of NapCat response shapes."""

    user_id: str
    group_id: str | None = None
    nickname: str | None = None
    card: str | None = None
    role: str | None = None
    payload: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "user_id", _id(self.user_id) or "")
        object.__setattr__(self, "group_id", _id(self.group_id))
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))

    @classmethod
    def from_payload(cls, value: Mapping[str, Any]) -> OneBotMemberInfo:
        return cls(
            user_id=_id(value.get("user_id")) or "",
            group_id=_id(value.get("group_id")),
            nickname=_id(value.get("nickname")),
            card=_id(value.get("card")),
            role=_id(value.get("role")),
            payload=_copy_json(value),
        )


@dataclass(frozen=True, slots=True)
class OneBotHistoryPage:
    """A read-only page of historical message payloads."""

    items: tuple[Mapping[str, JsonValue], ...]
    next_message_seq: str | None = None
    payload: Mapping[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "items",
            tuple(_freeze(dict(item)) for item in self.items),
        )
        object.__setattr__(self, "next_message_seq", _id(self.next_message_seq))
        object.__setattr__(self, "payload", _freeze(dict(self.payload)))


@dataclass(frozen=True, slots=True)
class PlatformActionDescriptor:
    name: str
    wire_action: str
    input_model: OneBotActionInput = field(default_factory=lambda: OneBotActionInput())
    return_model: object = OneBotActionResult
    read_only: bool = False
    destructive: bool = False
    retryable: bool = False
    requires_event: bool = False
    extension: bool = False


@dataclass(frozen=True, slots=True)
class PlatformCapabilityDescriptor:
    name: str
    version: str
    protocol: str
    actions: tuple[PlatformActionDescriptor, ...]
    extensions: tuple[str, ...] = ()

    def action(self, name: str) -> PlatformActionDescriptor | None:
        return next((item for item in self.actions if item.name == name), None)


class OneBotError(Exception):
    def __init__(
        self,
        message: str,
        *,
        action: str | None = None,
        code: str | int | None = None,
        retryable: bool = False,
    ) -> None:
        safe_message = redact_sensitive_text(str(message))
        super().__init__(safe_message)
        self.action = action
        self.code = code
        self.retryable = retryable
        self.message = safe_message


class OneBotCapabilityUnavailable(OneBotError):
    pass


class OneBotActionUnavailable(OneBotError):
    pass


class OneBotActionValidationError(OneBotError):
    pass


class OneBotActionRejected(OneBotError):
    pass


class OneBotTransportError(OneBotError):
    pass


class OneBotActionTimeout(OneBotTransportError):
    pass


@dataclass(frozen=True, slots=True)
class OneBotActionInput:
    """Small, dependency-free input model used by registered actions.

    ``kind`` is intentionally a narrow wire-independent vocabulary.  The
    adapter remains responsible for translating the validated values to the
    concrete NapCat request shape.
    """

    fields: tuple[tuple[str, str], ...] = ()
    required: tuple[str, ...] = ()
    exactly_one: tuple[str, ...] = ()
    at_least_one: tuple[str, ...] = ()

    def validate(self, params: Mapping[str, Any]) -> dict[str, Any]:
        known = {name for name, _kind in self.fields}
        unknown = sorted(set(params) - known)
        if unknown:
            raise OneBotActionValidationError(f"Unknown action parameter: {unknown[0]}")
        values = dict(params)
        for name in self.required:
            if name not in values or values[name] is None:
                raise OneBotActionValidationError(f"Missing action parameter: {name}")
        if self.exactly_one:
            supplied = [
                name for name in self.exactly_one if values.get(name) is not None
            ]
            if len(supplied) != 1:
                joined = ", ".join(self.exactly_one)
                raise OneBotActionValidationError(
                    f"Exactly one of {joined} is required"
                )
        if self.at_least_one and not any(
            values.get(name) is not None for name in self.at_least_one
        ):
            joined = ", ".join(self.at_least_one)
            raise OneBotActionValidationError(f"At least one of {joined} is required")
        kinds = dict(self.fields)
        for name, value in values.items():
            if value is None:
                continue
            kind = kinds[name]
            if kind == "id":
                if isinstance(value, bool) or not isinstance(value, (str, int)):
                    raise OneBotActionValidationError(
                        f"Action parameter {name} must be a string or integer"
                    )
                normalized = _id(value)
                if normalized is None:
                    raise OneBotActionValidationError(
                        f"Action parameter {name} must not be empty"
                    )
                values[name] = normalized
            elif kind == "id_list":
                if not isinstance(value, Sequence) or isinstance(value, str | bytes):
                    raise OneBotActionValidationError(
                        f"Action parameter {name} must be a list of IDs"
                    )
                normalized_ids = [_id(item) for item in value]
                if not normalized_ids or any(item is None for item in normalized_ids):
                    raise OneBotActionValidationError(
                        f"Action parameter {name} must contain non-empty IDs"
                    )
                values[name] = normalized_ids
            elif kind == "text":
                if not isinstance(value, str) or not value.strip():
                    raise OneBotActionValidationError(
                        f"Action parameter {name} must be non-empty text"
                    )
            elif kind == "bool" and not isinstance(value, bool):
                raise OneBotActionValidationError(
                    f"Action parameter {name} must be boolean"
                )
            elif kind == "integer" and (
                isinstance(value, bool) or not isinstance(value, int)
            ):
                raise OneBotActionValidationError(
                    f"Action parameter {name} must be an integer"
                )
            elif kind == "number" and (
                isinstance(value, bool) or not isinstance(value, (int, float))
            ):
                raise OneBotActionValidationError(
                    f"Action parameter {name} must be numeric"
                )
            elif kind == "message" and value is None:
                raise OneBotActionValidationError(
                    f"Action parameter {name} must be provided"
                )
        return values


def _input(
    *required: tuple[str, str],
    optional: tuple[tuple[str, str], ...] = (),
    exactly_one: tuple[str, ...] = (),
    at_least_one: tuple[str, ...] = (),
) -> OneBotActionInput:
    fields = tuple(required) + optional
    return OneBotActionInput(
        fields=fields,
        required=tuple(name for name, _kind in required),
        exactly_one=exactly_one,
        at_least_one=at_least_one,
    )


_ANY_MESSAGE = ("message", "message")
_TARGET = (("user_id", "id"), ("group_id", "id"))


_ACTION_INPUTS: dict[str, OneBotActionInput] = {
    "send": _input(
        _ANY_MESSAGE,
        optional=(*_TARGET, ("auto_escape", "bool"), ("timeout_ms", "number")),
        exactly_one=("user_id", "group_id"),
    ),
    "send_private": _input(
        _ANY_MESSAGE,
        ("user_id", "id"),
        optional=(("auto_escape", "bool"), ("timeout_ms", "number")),
    ),
    "send_group": _input(
        _ANY_MESSAGE,
        ("group_id", "id"),
        optional=(("auto_escape", "bool"), ("timeout_ms", "number")),
    ),
    "send_forward": _input(
        ("messages", "message"),
        optional=(
            *_TARGET,
            ("source", "text"),
            ("summary", "text"),
            ("prompt", "text"),
            ("news", "message"),
            ("timeout_ms", "number"),
        ),
        exactly_one=("user_id", "group_id"),
    ),
    "delete": _input(("message_id", "id")),
    "get_message": _input(("message_id", "id")),
    "get_forward_message": _input(("forward_id", "id")),
    "get_login_info": _input(),
    "get_status": _input(),
    "get_version_info": _input(),
    "get_group_info": _input(("group_id", "id")),
    "get_group_member_info": _input(
        ("group_id", "id"), ("user_id", "id"), optional=(("no_cache", "bool"),)
    ),
    "get_group_member_list": _input(
        ("group_id", "id"), optional=(("no_cache", "bool"),)
    ),
    "get_stranger_info": _input(("user_id", "id"), optional=(("no_cache", "bool"),)),
    "get_image": _input(
        optional=(("file", "text"), ("file_id", "text")),
        exactly_one=("file", "file_id"),
    ),
    "get_file": _input(
        optional=(("file", "text"), ("file_id", "text")),
        exactly_one=("file", "file_id"),
    ),
    "get_group_file_url": _input(("group_id", "id"), ("file_id", "text")),
    "get_private_file_url": _input(("file_id", "text")),
    "set_group_admin": _input(
        ("group_id", "id"), ("user_id", "id"), optional=(("enable", "bool"),)
    ),
    "set_group_ban": _input(
        ("group_id", "id"),
        ("user_id", "id"),
        optional=(("duration", "number"),),
    ),
    "set_group_card": _input(
        ("group_id", "id"), ("user_id", "id"), optional=(("card", "text"),)
    ),
    "kick_group_member": _input(
        ("group_id", "id"),
        ("user_id", "id"),
        optional=(("reject_add_request", "bool"),),
    ),
    "kick_group_members": _input(
        ("group_id", "id"),
        ("user_ids", "id_list"),
        optional=(("reject_add_request", "bool"),),
    ),
    "leave_group": _input(("group_id", "id"), optional=(("is_dismiss", "bool"),)),
    "set_group_whole_ban": _input(("group_id", "id"), optional=(("enable", "bool"),)),
    "set_essence_message": _input(("message_id", "id")),
    "delete_essence_message": _input(
        optional=(
            ("message_id", "id"),
            ("msg_seq", "id"),
            ("msg_random", "id"),
            ("group_id", "id"),
        ),
        at_least_one=("message_id", "msg_seq", "msg_random"),
    ),
    "set_friend_add_request": _input(
        ("flag", "text"),
        optional=(("approve", "bool"), ("remark", "text")),
    ),
    "set_group_add_request": _input(
        ("flag", "text"),
        ("sub_type", "text"),
        optional=(("approve", "bool"), ("reason", "text")),
    ),
    "get_group_msg_history": _input(
        ("group_id", "id"),
        optional=(("count", "integer"), ("message_seq", "id")),
    ),
    "get_friend_msg_history": _input(
        ("user_id", "id"),
        optional=(("count", "integer"), ("message_seq", "id")),
    ),
    "send_like": _input(("user_id", "id"), optional=(("times", "number"),)),
    "friend_poke": _input(("user_id", "id"), optional=(("target_id", "id"),)),
    "group_poke": _input(
        ("group_id", "id"),
        ("user_id", "id"),
        optional=(("target_id", "id"),),
    ),
    "send_group_notice": _input(
        ("group_id", "id"),
        ("content", "text"),
        optional=(
            ("pinned", "number"),
            ("type_", "number"),
            ("confirm_required", "number"),
            ("is_show_edit_card", "number"),
            ("tip_window_type", "number"),
            ("image", "text"),
        ),
    ),
    "set_input_status": _input(("user_id", "id"), optional=(("event_type", "number"),)),
    "get_online_file_messages": _input(("user_id", "id")),
    "create_flash_task": _input(
        ("files", "message"),
        optional=(("name", "text"), ("thumb_path", "text")),
    ),
    "get_flash_file_list": _input(("fileset_id", "text")),
    "get_flash_file_url": _input(
        ("fileset_id", "text"),
        optional=(("file_name", "text"), ("file_index", "number")),
    ),
    "receive_online_file": _input(
        ("user_id", "id"), ("msg_id", "text"), ("element_id", "text")
    ),
    "refuse_online_file": _input(
        ("user_id", "id"), ("msg_id", "text"), ("element_id", "text")
    ),
    "cancel_online_file": _input(("user_id", "id"), ("msg_id", "text")),
    "send_online_file": _input(
        ("user_id", "id"),
        ("file_path", "text"),
        optional=(("file_name", "text"),),
    ),
    "send_online_folder": _input(
        ("user_id", "id"),
        ("folder_path", "text"),
        optional=(("folder_name", "text"),),
    ),
    "send_flash_message": _input(
        ("fileset_id", "text"),
        optional=(*_TARGET,),
        exactly_one=("user_id", "group_id"),
    ),
    "fetch_custom_face": _input(optional=(("count", "integer"),)),
    "get_ai_characters": _input(
        ("group_id", "id"), optional=(("chat_type", "number"),)
    ),
    "send_group_ai_record": _input(
        ("group_id", "id"),
        ("character", "text"),
        ("text", "text"),
        optional=(
            ("chat_type", "number"),
            ("timeout_seconds", "number"),
        ),
    ),
}

_ACTION_RETURN_MODELS: dict[str, object] = {
    "send": OneBotMessageReceipt,
    "send_private": OneBotMessageReceipt,
    "send_group": OneBotMessageReceipt,
    "send_forward": OneBotMessageReceipt,
    "get_group_info": OneBotGroupInfo,
    "get_group_member_info": OneBotMemberInfo,
    "get_group_member_list": tuple[OneBotMemberInfo, ...],
    "get_stranger_info": OneBotMemberInfo,
    "get_image": OneBotFileResult,
    "get_file": OneBotFileResult,
    "get_group_file_url": OneBotFileResult,
    "get_private_file_url": OneBotFileResult,
    "get_group_msg_history": OneBotHistoryPage,
    "get_friend_msg_history": OneBotHistoryPage,
}


ONEBOT_V11_ACTIONS: tuple[PlatformActionDescriptor, ...] = tuple(
    PlatformActionDescriptor(
        name=name,
        wire_action=wire,
        input_model=_ACTION_INPUTS[name],
        return_model=_ACTION_RETURN_MODELS.get(name, OneBotActionResult),
        read_only=read_only,
        destructive=destructive,
        retryable=read_only,
    )
    for name, wire, read_only, destructive in (
        ("send", "send_msg", False, False),
        ("send_private", "send_private_msg", False, False),
        ("send_group", "send_group_msg", False, False),
        ("send_forward", "send_forward_msg", False, False),
        ("delete", "delete_msg", False, False),
        ("get_message", "get_msg", True, False),
        ("get_forward_message", "get_forward_msg", True, False),
        ("get_login_info", "get_login_info", True, False),
        ("get_status", "get_status", True, False),
        ("get_version_info", "get_version_info", True, False),
        ("get_group_info", "get_group_info", True, False),
        ("get_group_member_info", "get_group_member_info", True, False),
        ("get_group_member_list", "get_group_member_list", True, False),
        ("get_stranger_info", "get_stranger_info", True, False),
        ("get_image", "get_image", True, False),
        ("get_file", "get_file", True, False),
        ("get_group_file_url", "get_group_file_url", True, False),
        ("get_private_file_url", "get_private_file_url", True, False),
        ("set_group_admin", "set_group_admin", False, True),
        ("set_group_ban", "set_group_ban", False, True),
        ("set_group_card", "set_group_card", False, True),
        ("kick_group_member", "set_group_kick", False, True),
        ("kick_group_members", "set_group_kick_members", False, True),
        ("leave_group", "set_group_leave", False, True),
        ("set_group_whole_ban", "set_group_whole_ban", False, True),
        ("set_essence_message", "set_essence_msg", False, True),
        ("delete_essence_message", "delete_essence_msg", False, True),
        ("set_friend_add_request", "set_friend_add_request", False, True),
        ("set_group_add_request", "set_group_add_request", False, True),
        ("get_group_msg_history", "get_group_msg_history", True, False),
        ("get_friend_msg_history", "get_friend_msg_history", True, False),
    )
)

NAPCAT_QQ_ACTIONS: tuple[PlatformActionDescriptor, ...] = tuple(
    PlatformActionDescriptor(
        name=name,
        wire_action=wire,
        input_model=_ACTION_INPUTS[name],
        return_model=_ACTION_RETURN_MODELS.get(name, OneBotActionResult),
        read_only=name.startswith(("get_", "fetch_")),
        destructive=destructive,
        retryable=name.startswith(("get_", "fetch_")),
        extension=True,
    )
    for name, wire, destructive in (
        ("send_like", "send_like", False),
        ("friend_poke", "friend_poke", False),
        ("group_poke", "group_poke", False),
        ("send_group_notice", "_send_group_notice", False),
        ("set_input_status", "set_input_status", False),
        ("get_online_file_messages", "get_online_file_messages", False),
        ("create_flash_task", "create_flash_task", False),
        ("get_flash_file_list", "get_flash_file_list", False),
        ("get_flash_file_url", "get_flash_file_url", False),
        ("receive_online_file", "receive_online_file", False),
        ("refuse_online_file", "refuse_online_file", False),
        ("cancel_online_file", "cancel_online_file", False),
        ("send_online_file", "send_online_file", False),
        ("send_online_folder", "send_online_folder", False),
        ("send_flash_message", "send_flash_msg", False),
        ("fetch_custom_face", "fetch_custom_face", False),
        ("get_ai_characters", "get_ai_characters", False),
        ("send_group_ai_record", "send_group_ai_record", False),
    )
)

ONEBOT_CAPABILITIES = (
    PlatformCapabilityDescriptor("onebot.v11", "1.0", "onebot.v11", ONEBOT_V11_ACTIONS),
    PlatformCapabilityDescriptor(
        "napcat.qq", "1.0", "onebot.v11", NAPCAT_QQ_ACTIONS, extensions=("napcat", "qq")
    ),
)


def get_capability_descriptor(name: str) -> PlatformCapabilityDescriptor | None:
    return next((item for item in ONEBOT_CAPABILITIES if item.name == name), None)


__all__ = [
    "JsonValue",
    "OneBotEvent",
    "OneBotMessageEvent",
    "OneBotNoticeEvent",
    "OneBotRequestEvent",
    "OneBotMetaEvent",
    "OneBotSegment",
    "OneBotSender",
    "OneBotActionResult",
    "OneBotMessageReceipt",
    "OneBotFileResult",
    "OneBotGroupInfo",
    "OneBotMemberInfo",
    "OneBotHistoryPage",
    "OneBotActionInput",
    "PlatformCapabilityDescriptor",
    "PlatformActionDescriptor",
    "OneBotError",
    "OneBotCapabilityUnavailable",
    "OneBotActionUnavailable",
    "OneBotActionValidationError",
    "OneBotActionRejected",
    "OneBotTransportError",
    "OneBotActionTimeout",
    "ONEBOT_CAPABILITIES",
    "get_capability_descriptor",
    "ONEBOT_SDK_VERSION",
]
