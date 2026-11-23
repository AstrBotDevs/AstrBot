"""Presentation policies for SDK commands exposed by platform adapters."""

from collections.abc import Mapping


def sdk_command_description(item: Mapping[str, object], command_name: str) -> str:
    """Use the declared description or a stable command/group fallback."""
    description = str(item.get("description") or "").strip()
    if description:
        return description
    if item.get("is_group"):
        return f"Command group: {command_name}"
    return f"Command: {command_name}"
