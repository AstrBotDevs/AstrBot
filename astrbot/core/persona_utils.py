"""Helpers for persona marker handling."""

PERSONA_NONE_MARKER = "[%None]"


def is_persona_none_marker(persona_id: str | None) -> bool:
    """Return whether the persona id is the explicit no-persona marker."""
    return persona_id == PERSONA_NONE_MARKER


def normalize_persona_id(persona_id: str | None) -> str | None:
    """Normalize the explicit no-persona marker to None."""
    if is_persona_none_marker(persona_id):
        return None
    return persona_id
