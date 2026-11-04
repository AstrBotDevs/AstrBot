"""Explicit message components shared by tools and agent runtime implementations."""

from __future__ import annotations

from astrbot.core.agent.input import format_input_content, parse_input_content

SUBAGENT_MESSAGES_SCHEMA = {
    "type": "array",
    "minItems": 1,
    "description": "Ordered plain instructions, image input, and file references. Attachments must be provided explicitly.",
    "items": {
        "type": "object",
        "properties": {
            "type": {"type": "string", "enum": ["plain", "image", "file"]},
            "text": {
                "type": "string",
                "description": "Text for plain, or an optional attachment label.",
            },
            "path": {
                "type": "string",
                "description": "File path in the current workspace, host, or sandbox.",
            },
            "url": {"type": "string", "description": "URL for image or file."},
        },
        "required": ["type"],
        "additionalProperties": False,
    },
}


def format_agent_messages(messages: list[dict]) -> str:
    """Format persisted tool input using the runtime's common content semantics.

    Args:
        messages: Validated plain, image, and file dictionaries in the public store.

    Returns:
        Plain instructions and ordered attachment references.
    """
    return format_input_content(parse_input_content(messages))
