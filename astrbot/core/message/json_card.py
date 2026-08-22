from __future__ import annotations

import json
from collections.abc import Iterable

from astrbot.core.message.components import Json

_MAX_CARD_FIELD_LENGTH = 200


def format_json_card_prompt(comp: Json) -> str:
    """Render a JSON card as a compact Shared Card prompt fragment.

    Unknown cards without title, description, or URL still return
    ``[Shared Card]``. Field values are truncated to 200 characters.

    Args:
        comp: An inbound JSON message component.

    Returns:
        A model-readable card summary. Never includes the raw JSON blob.
    """
    card_data = comp.data
    if isinstance(card_data, dict) and isinstance(card_data.get("data"), str):
        try:
            nested_data = json.loads(card_data["data"])
            if isinstance(nested_data, dict):
                card_data = nested_data
        except json.JSONDecodeError:
            pass

    detail = _select_card_detail(card_data)

    fields = []
    for label, value in (
        ("Title", detail.get("title")),
        ("Description", detail.get("desc")),
        ("URL", detail.get("qqdocurl") or detail.get("jumpUrl")),
        ("Tag", detail.get("tag")),
    ):
        if isinstance(value, str) and value.strip():
            normalized = " ".join(value.split())
            fields.append(f"{label}: {_truncate_card_field(normalized)}")
    suffix = f": {'; '.join(fields)}" if fields else ""
    return f"[Shared Card{suffix}]"


def json_card_prompt_from_components(components: Iterable[object] | None) -> str:
    """Join Shared Card summaries from JSON components in a message chain.

    Args:
        components: Message-chain items. Non-iterables and non-JSON items
            are ignored.

    Returns:
        Space-joined card summaries, or an empty string when none exist.
    """
    if components is None or isinstance(components, (str, bytes)):
        return ""
    parts = [
        format_json_card_prompt(comp) for comp in components if isinstance(comp, Json)
    ]
    return " ".join(parts)


def json_card_prompt_from_event(event: object) -> str:
    """Render Shared Card summaries from an event's message chain."""
    messages = getattr(getattr(event, "message_obj", None), "message", None)
    return json_card_prompt_from_components(messages)


def coalesce_prompt_with_json_cards(event: object, prompt: str | None) -> str:
    """Keep a non-blank prompt, otherwise fall back to JSON card summaries."""
    if prompt and str(prompt).strip():
        return prompt
    return json_card_prompt_from_event(event)


def _select_card_detail(card_data: object) -> dict:
    """Pick the first share-card payload from known or generic meta objects."""
    if not isinstance(card_data, dict):
        return {}
    meta = card_data.get("meta")
    if not isinstance(meta, dict):
        return {}

    for key in ("detail_1", "news", "music"):
        candidate = meta.get(key)
        if _is_share_card_detail(candidate):
            return candidate

    view = card_data.get("view")
    if isinstance(view, str) and view.strip():
        candidate = meta.get(view.strip())
        if _is_share_card_detail(candidate):
            return candidate

    for candidate in meta.values():
        if _is_share_card_detail(candidate):
            return candidate
    return {}


def _is_share_card_detail(candidate: object) -> bool:
    if not isinstance(candidate, dict):
        return False
    return any(
        isinstance(candidate.get(key), str) and candidate[key].strip()
        for key in ("title", "desc", "qqdocurl", "jumpUrl", "tag")
    )


def _truncate_card_field(text: str) -> str:
    if len(text) <= _MAX_CARD_FIELD_LENGTH:
        return text
    return text[:_MAX_CARD_FIELD_LENGTH] + "..."
