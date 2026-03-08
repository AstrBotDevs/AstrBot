from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PERSONA_CUSTOM_ERROR_MESSAGE_EXTRA_KEY = "persona_custom_error_message"


def normalize_persona_custom_error_message(value: object) -> str | None:
    """Normalize persona custom error reply text."""
    if not isinstance(value, str):
        return None
    message = value.strip()
    return message or None


def extract_persona_custom_error_message_from_persona(
    persona: Mapping[str, Any] | None,
) -> str | None:
    """Extract normalized custom error reply text from persona mapping."""
    if persona is None:
        return None
    return normalize_persona_custom_error_message(persona.get("custom_error_message"))


def extract_persona_custom_error_message_from_event(event: Any) -> str | None:
    """Extract normalized custom error reply text from event extras."""
    try:
        if event is None or not hasattr(event, "get_extra"):
            return None
        raw_message = event.get_extra(PERSONA_CUSTOM_ERROR_MESSAGE_EXTRA_KEY)
        return normalize_persona_custom_error_message(raw_message)
    except Exception:
        return None


def set_persona_custom_error_message_on_event(
    event: Any, message: object
) -> str | None:
    """Normalize and store persona custom error reply text into event extras."""
    normalized = normalize_persona_custom_error_message(message)
    try:
        if event is not None and hasattr(event, "set_extra"):
            event.set_extra(PERSONA_CUSTOM_ERROR_MESSAGE_EXTRA_KEY, normalized)
    except Exception:
        pass
    return normalized


async def resolve_persona_custom_error_message(
    *,
    event: Any,
    persona_manager: Any,
    provider_settings: dict | None = None,
    conversation_persona_id: str | None = None,
) -> str | None:
    """Resolve normalized custom error reply text for the selected persona."""
    (
        _persona_id,
        persona,
        _force_applied_persona_id,
        _use_webchat_special_default,
    ) = await persona_manager.resolve_selected_persona(
        umo=event.unified_msg_origin,
        conversation_persona_id=conversation_persona_id,
        platform_name=event.get_platform_name(),
        provider_settings=provider_settings,
    )
    return extract_persona_custom_error_message_from_persona(persona)


async def resolve_event_conversation_persona_id(
    event: Any, conversation_manager: Any
) -> str | None:
    """Resolve current conversation persona_id from event and conversation manager."""
    curr_cid = await conversation_manager.get_curr_conversation_id(
        event.unified_msg_origin
    )
    if not curr_cid:
        return None
    conversation = await conversation_manager.get_conversation(
        event.unified_msg_origin, curr_cid
    )
    if not conversation:
        return None
    return conversation.persona_id
