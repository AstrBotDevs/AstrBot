from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from astrbot_sdk.message_components import component_to_payload_sync

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


class EventConverter:
    """Convert legacy AstrBot events into SDK payloads."""

    _DROP_VALUE = object()

    @classmethod
    def _sanitize_extra_value(cls, value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple)):
            items = []
            for item in value:
                sanitized = cls._sanitize_extra_value(item)
                if sanitized is not cls._DROP_VALUE:
                    items.append(sanitized)
            return items
        if isinstance(value, dict):
            sanitized_dict: dict[str, Any] = {}
            for key, item in value.items():
                sanitized = cls._sanitize_extra_value(item)
                if sanitized is not cls._DROP_VALUE:
                    sanitized_dict[str(key)] = sanitized
            return sanitized_dict
        try:
            json.dumps(value)
        except (TypeError, ValueError):
            return cls._DROP_VALUE
        return value

    @classmethod
    def _sanitize_extras(cls, extras: dict[str, Any]) -> dict[str, Any]:
        sanitized: dict[str, Any] = {}
        for key, value in extras.items():
            normalized = cls._sanitize_extra_value(value)
            if normalized is not cls._DROP_VALUE:
                sanitized[str(key)] = normalized
        return sanitized

    @staticmethod
    def core_to_sdk(
        event: AstrMessageEvent,
        *,
        dispatch_token: str,
        plugin_id: str,
        request_id: str,
    ) -> dict[str, Any]:
        message_type = event.get_message_type()
        raw = {
            "dispatch_token": dispatch_token,
            "plugin_id": plugin_id,
            "request_id": request_id,
            "platform_id": event.get_platform_id(),
        }
        payload: dict[str, Any] = {
            "text": event.get_message_str(),
            "user_id": event.get_sender_id(),
            "group_id": event.get_group_id() or None,
            "platform": event.get_platform_name(),
            "platform_id": event.get_platform_id(),
            "session_id": event.unified_msg_origin,
            "self_id": event.get_self_id(),
            "message_type": getattr(message_type, "value", None),
            "sender_name": event.get_sender_name(),
            "is_admin": event.is_admin(),
            "is_wake": event.is_wake,
            "is_at_or_wake_command": event.is_at_or_wake_command,
            "message_outline": event.get_message_outline(),
            "raw": raw,
            "target": {
                "conversation_id": event.unified_msg_origin,
                "platform": event.get_platform_name(),
                "raw": raw,
            },
        }
        extras = event.get_extra()
        if isinstance(extras, dict) and extras:
            sanitized_extras = EventConverter._sanitize_extras(extras)
            if sanitized_extras:
                payload["extras"] = sanitized_extras
        messages = []
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
        if messages:
            payload["messages"] = messages
        return payload

    @staticmethod
    def extract_handler_result(sdk_result: dict[str, Any] | None) -> dict[str, Any]:
        if not sdk_result:
            return {"sent_message": False, "stop": False, "call_llm": False}
        return {
            "sent_message": bool(sdk_result.get("sent_message", False)),
            "stop": bool(sdk_result.get("stop", False)),
            "call_llm": bool(sdk_result.get("call_llm", False)),
        }
