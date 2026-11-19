"""Render model-facing mention text from ordered message chains.

Adapters that build Plain/At components at true mention positions mark their
message with ``ordered_mentions``. The agent input boundary then derives the
model body from that chain instead of the cleaned text, so each directed
mention stays with its own clause. Platforms without the marker keep their
existing text-based behavior.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import At, AtAll, Plain

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.provider.entities import ProviderRequest

SELF_MENTION_POSITION_UNKNOWN = "_self_mention_position_unknown"
"""Message attribute marking a wake-only bot At without a locatable tag."""

SELF_MENTION_IDENTITY_CONFIRMED = "_self_mention_identity_confirmed"
"""Message attribute confirming a position-less bot At with a reliable identity."""


def render_mention_body(
    event: AstrMessageEvent,
    prefixes: list[str],
) -> tuple[str, str | None] | None:
    """Render the model-facing body from the event's ordered message chain.

    Args:
        event: Event whose top-level chain carries true mention positions.
        prefixes: Prefix texts confirmed consumed from the cleaned message.

    Returns:
        ``(body, self_label)`` with the label of the first rendered bot
        mention (or None), or None when a confirmed prefix no longer matches
        the chain and the cleaned text must be kept as-is.
    """
    components = getattr(event.message_obj, "message", None) or []
    self_id = str(event.get_self_id() or "")
    skip_self = getattr(event.message_obj, SELF_MENTION_POSITION_UNKNOWN, False)
    identity_confirmed = getattr(
        event.message_obj, SELF_MENTION_IDENTITY_CONFIRMED, False
    )
    parts: list[str] = []
    self_label: str | None = None
    prefixes = [prefix for prefix in prefixes if prefix]
    for component in components:
        if isinstance(component, Plain):
            text = component.text or ""
            while prefixes and text.strip():
                text = text.lstrip()
                if not text.startswith(prefixes[0]):
                    return None
                text = text[len(prefixes.pop(0)) :].lstrip()
            parts.append(text)
        elif isinstance(component, At) and not isinstance(component, AtAll):
            label = str(component.name or "").strip() or str(component.qq or "").strip()
            if not label:
                continue
            is_self = bool(self_id) and str(component.qq) == self_id
            if skip_self and is_self:
                # Wake-only fallback At: the bot was mentioned, but its
                # original position is unavailable, so nothing is rendered.
                # A confirmed identity still yields a self label so the model
                # can be told this message is directed at it.
                if identity_confirmed and self_label is None:
                    self_label = label
                continue
            parts.append(f"@{label}")
            if self_label is None and is_self:
                self_label = label
    if prefixes:
        return None
    return "".join(parts).strip(), self_label


def _self_reminder_text(event: AstrMessageEvent, label: str) -> str:
    self_id = str(event.get_self_id() or "")
    return (
        f"<system_reminder>@{label} refers to you "
        f"(Your ID: {self_id}).</system_reminder>"
    )


def supplement_mention_display(
    event: AstrMessageEvent,
    req: ProviderRequest,
    *,
    prompt_has_text: bool,
) -> None:
    """Render ordered mentions into a default event-derived request.

    Args:
        event: Event whose cleaned text produced the request prompt.
        req: Current request; its prompt and user content are updated in place.
        prompt_has_text: Whether the user actually supplied prompt text before
            attachment handling and placeholder defaults filled it. The cleaned
            message_str cannot decide this because it may still hold an
            already-consumed provider wake prefix.
    """
    if not getattr(event.message_obj, "ordered_mentions", False):
        return
    prefixes = [
        str(event.get_extra("_consumed_wake_prefix") or ""),
        str(event.get_extra("_consumed_provider_prefix") or ""),
    ]
    rendered = render_mention_body(event, prefixes)
    if rendered is None:
        return
    body, self_label = rendered
    # The rendered body only replaces user-supplied text. Pipeline-provided
    # defaults (the file summary prompt, the attachment placeholder) must stay.
    if prompt_has_text or not req.prompt:
        req.prompt = body
    elif body:
        req.extra_user_content_parts.append(TextPart(text=body))
    if self_label is not None:
        req.extra_user_content_parts.append(
            TextPart(text=_self_reminder_text(event, self_label)).mark_as_temp()
        )


def follow_up_text(event: AstrMessageEvent) -> tuple[str, str | None]:
    """Return the in-run follow-up text and its temporary self reminder.

    Args:
        event: Event captured as follow-up input for the active turn.

    Returns:
        ``(text, reminder)``; the text falls back to the media outline when
        the message has no text, and the reminder is only produced for a
        confirmed bot mention. Mention markers alone never turn an otherwise
        empty follow-up into a valid input.
    """
    message_str = event.get_message_str() or ""
    if not getattr(event.message_obj, "ordered_mentions", False):
        return message_str or event.get_message_outline(), None
    message_str = message_str.strip()
    reminder = None
    rendered = render_mention_body(
        event,
        [str(event.get_extra("_consumed_wake_prefix") or "")],
    )
    if rendered is not None:
        body, self_label = rendered
        if self_label:
            reminder = _self_reminder_text(event, self_label)
        # Quoted voice transcripts are only appended to a rendered body:
        # every fallback text (message_str or the outline) either already
        # carries them or never had them, so appending again would
        # duplicate the recognized text.
        if message_str and body:
            quoted = str(event.get_extra("_quoted_voice_transcript") or "")
            return body + quoted, reminder
    return message_str or event.get_message_outline(), reminder
