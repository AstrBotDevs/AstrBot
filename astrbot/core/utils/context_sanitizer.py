from typing import Any


def strip_tool_use_from_context(
    messages: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not messages:
        return []

    sanitized_messages: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue

        role = message.get("role")
        if role == "tool":
            continue

        sanitized_message = dict(message)
        if role == "assistant" and "tool_calls" in sanitized_message:
            sanitized_message.pop("tool_calls", None)
            sanitized_message.pop("tool_call_id", None)

            content = sanitized_message.get("content")
            if content is None:
                continue
            if isinstance(content, str) and not content.strip():
                continue
            if isinstance(content, list) and not content:
                continue

        sanitized_messages.append(sanitized_message)

    return sanitized_messages
