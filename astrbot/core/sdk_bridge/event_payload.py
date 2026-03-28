from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from uuid import UUID

from astrbot_sdk.message.components import component_to_payload_sync

from astrbot.core.message.message_types import sdk_message_type

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


DROP_VALUE = object()


@dataclass(frozen=True, slots=True)
class InboundEventSnapshot:
    text: str
    user_id: str
    group_id: str | None
    platform: str
    platform_id: str
    session_id: str
    self_id: str
    message_type: str
    sender_name: str
    is_admin: bool
    is_wake: bool
    is_at_or_wake_command: bool
    message_outline: str
    messages: tuple[dict[str, Any], ...]
    target: MappingProxyType

    def to_payload(
        self,
        *,
        dispatch_token: str,
        plugin_id: str,
        request_id: str,
        host_extras: dict[str, Any],
        sdk_local_extras: dict[str, Any],
        raw_updates: dict[str, Any] | None = None,
        field_updates: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw = {
            "dispatch_token": dispatch_token,
            "plugin_id": plugin_id,
            "request_id": request_id,
            "platform_id": self.platform_id,
        }
        if raw_updates:
            raw.update(copy.deepcopy(raw_updates))

        merged_extras = dict(host_extras)
        merged_extras.update(sdk_local_extras)
        payload: dict[str, Any] = {
            "text": self.text,
            "user_id": self.user_id,
            "group_id": self.group_id,
            "platform": self.platform,
            "platform_id": self.platform_id,
            "session_id": self.session_id,
            "self_id": self.self_id,
            "message_type": self.message_type,
            "sender_name": self.sender_name,
            "is_admin": self.is_admin,
            "is_wake": self.is_wake,
            "is_at_or_wake_command": self.is_at_or_wake_command,
            "message_outline": self.message_outline,
            "raw": raw,
            "target": {
                "conversation_id": self.target["conversation_id"],
                "platform": self.target["platform"],
                "raw": dict(raw),
            },
            "host_extras": copy.deepcopy(host_extras),
            "sdk_local_extras": copy.deepcopy(sdk_local_extras),
            "extras": merged_extras,
        }
        if self.messages:
            payload["messages"] = copy.deepcopy(list(self.messages))
        if field_updates:
            payload.update(copy.deepcopy(field_updates))
        return payload


def sanitize_sdk_extra_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (list, tuple)):
        items = []
        for item in value:
            normalized = sanitize_sdk_extra_value(item)
            if normalized is not DROP_VALUE:
                items.append(normalized)
        return items
    if isinstance(value, dict):
        normalized_dict: dict[str, Any] = {}
        for key, item in value.items():
            normalized = sanitize_sdk_extra_value(item)
            if normalized is not DROP_VALUE:
                normalized_dict[str(key)] = normalized
        return normalized_dict
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return sanitize_sdk_extra_value(model_dump())
        except Exception:
            return DROP_VALUE
    dict_view = getattr(value, "__dict__", None)
    if isinstance(dict_view, dict) and dict_view:
        return sanitize_sdk_extra_value(dict_view)
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return DROP_VALUE
    return value


def sanitize_sdk_extras(extras: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in extras.items():
        normalized = sanitize_sdk_extra_value(value)
        if normalized is not DROP_VALUE:
            sanitized[str(key)] = normalized
    return sanitized


def normalize_sdk_local_extras(
    payload: Any,
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(payload, dict):
        return {}, []
    normalized: dict[str, Any] = {}
    dropped_keys: list[str] = []
    for key, value in payload.items():
        normalized_value = sanitize_sdk_extra_value(value)
        if normalized_value is DROP_VALUE:
            dropped_keys.append(str(key))
            continue
        normalized[str(key)] = normalized_value
    return normalized, dropped_keys


def extract_sdk_handler_result(sdk_result: dict[str, Any] | None) -> dict[str, bool]:
    if not sdk_result:
        return {"sent_message": False, "stop": False, "call_llm": False}
    return {
        "sent_message": bool(sdk_result.get("sent_message", False)),
        "stop": bool(sdk_result.get("stop", False)),
        "call_llm": bool(sdk_result.get("call_llm", False)),
    }


def build_inbound_event_snapshot(event: AstrMessageEvent) -> InboundEventSnapshot:
    group_id = event.get_group_id() or None
    user_id = event.get_sender_id() or ""
    messages: list[dict[str, Any]] = []
    for component in event.get_messages():
        try:
            messages.append(component_to_payload_sync(component))
        except Exception:
            messages.append(
                {
                    "type": "unknown",
                    "data": {"value": str(component)},
                }
            )
    return InboundEventSnapshot(
        text=event.get_message_str(),
        user_id=user_id,
        group_id=group_id,
        platform=event.get_platform_name(),
        platform_id=event.get_platform_id(),
        session_id=event.unified_msg_origin,
        self_id=event.get_self_id(),
        message_type=sdk_message_type(
            event.get_message_type(),
            group_id=group_id,
            user_id=user_id or None,
        ),
        sender_name=event.get_sender_name(),
        is_admin=event.is_admin(),
        is_wake=bool(event.is_wake),
        is_at_or_wake_command=bool(event.is_at_or_wake_command),
        message_outline=event.get_message_outline(),
        messages=tuple(messages),
        target=MappingProxyType(
            {
                "conversation_id": event.unified_msg_origin,
                "platform": event.get_platform_name(),
            }
        ),
    )
