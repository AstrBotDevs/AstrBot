"""Render mention text from group message chains."""

from __future__ import annotations

from typing import TYPE_CHECKING

from astrbot.core.agent.message import TextPart
from astrbot.core.message.components import At, AtAll, Plain
from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.quoted_message.chain_parser import ReplyChainParser

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.provider.entities import ProviderRequest


def render_mention_body(
    event: AstrMessageEvent,
    prefixes: list[str],
) -> tuple[str, str | None] | None:
    """Render the model-facing body from the event's ordered message chain.

    Args:
        event: Event whose top-level chain carries true mention positions.
        prefixes: Prefix texts confirmed consumed from the cleaned message.

    Returns:
        ``(body, self_label)`` with the optional label of the first bot mention,
        or None if the group message has no renderable mention or its
        consumed prefixes do not match.
    """
    if event.get_message_type() != MessageType.GROUP_MESSAGE:
        return None

    components = getattr(event.message_obj, "message", None) or []
    self_id = str(event.get_self_id() or "")
    parts: list[str] = []
    has_mention = False
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
            parts.append(f"@{label}")
            has_mention = True
            if self_label is None and is_self:
                self_label = label
    if prefixes or not has_mention:
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
    reminder = None
    rendered = render_mention_body(
        event,
        [str(event.get_extra("_consumed_wake_prefix") or "")],
    )
    if rendered is not None:
        body, self_label = rendered
        if self_label:
            reminder = _self_reminder_text(event, self_label)
        if message_str.strip() and body:
            message_str = body
    if quoted := ReplyChainParser().format_embedded_replies(event):
        message_str = f"{message_str}\n\n{quoted}" if message_str.strip() else quoted
    return message_str or event.get_message_outline(), reminder
