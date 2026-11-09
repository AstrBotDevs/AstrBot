"""Project protocol-recorded self mentions into model-facing text.

Adapters record where the bot was mentioned in the text they cleaned. The
cleaned text itself must stay untouched for wake checks, commands and plugins,
so the model-facing text is derived later, after prefixes and attachments have
been resolved.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from astrbot.core.message.components import At, AtAll

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

SELF_MENTION_SPANS = "_self_mention_spans"
"""Event extra holding ordered ``(start, end, label)`` mentions of the bot."""

SELF_MENTION_TRIM = "_self_mention_trim"
"""Event extra holding the number of leading characters removed from the text."""

SELF_MENTION_UNKNOWN_POSITION = "_self_mention_position_unknown"
"""Event extra marking a bot mention whose original position is unavailable."""

UNKNOWN_POSITION_NOTICE = (
    "[This message mentions you; the original mention position is unavailable.]"
)


def is_self_mention(component: Any, self_id: str) -> bool:
    """Return whether a component is a real top-level mention of the bot.

    Args:
        component: Message component to inspect.
        self_id: Identifier of the bot on the current platform.

    Returns:
        True only for a directed ``At`` targeting the bot; ``AtAll`` is excluded.
    """
    return (
        isinstance(component, At)
        and not isinstance(component, AtAll)
        and str(component.qq) == str(self_id)
    )


def self_mention_label(component: At) -> str:
    """Return the display label of a self mention.

    Args:
        component: ``At`` component resolving to the bot.

    Returns:
        The mention nickname, or its identifier when no nickname is available.
    """
    name = (component.name or "").strip()
    if name:
        return name
    return str(component.qq or "").strip()


def render_self_mention(label: str) -> str:
    """Return the inline marker shown to the model.

    Args:
        label: Mention nickname or identifier; empty when neither is known.

    Returns:
        A self-describing marker followed by a separator space.
    """
    if label:
        return f"@{label}（you） "
    return "@you "


def project_self_mentions(
    text: str,
    spans: list[tuple[int, int, str]] | None,
    trim: int = 0,
) -> str:
    """Insert self-mention markers at their recorded positions.

    Args:
        text: Current cleaned text.
        spans: Ordered ``(start, end, label)`` ranges recorded while parsing.
        trim: Number of leading characters removed from the recorded text.

    Returns:
        The text with markers inserted, or the text unchanged when no span applies.
    """
    if not spans:
        return text
    projected: list[str] = []
    cursor = 0
    for start, end, label in sorted(spans, key=lambda span: span[0]):
        begin = min(max(start - trim, cursor), len(text))
        finish = min(max(end - trim, begin), len(text))
        projected.append(text[cursor:begin])
        projected.append(render_self_mention(label))
        cursor = finish
    projected.append(text[cursor:])
    projected_text = "".join(projected)
    return projected_text if text else projected_text.strip()


def self_mention_view(
    event: AstrMessageEvent,
    text: str,
    trim: int | None = None,
) -> str:
    """Return the model-facing text for an event-derived message.

    Args:
        event: Event carrying the mention facts recorded during parsing.
        text: Current cleaned text to project mentions into.
        trim: Explicit leading-character offset, or None to use the event value.

    Returns:
        The projected text, or the text unchanged when no mention was recorded.
    """
    spans = event.get_extra(SELF_MENTION_SPANS) or []
    if spans:
        offset = event.get_extra(SELF_MENTION_TRIM, 0) if trim is None else trim
        return project_self_mentions(text, spans, int(offset or 0))
    if event.get_extra(SELF_MENTION_UNKNOWN_POSITION):
        return f"{text}\n{UNKNOWN_POSITION_NOTICE}" if text else UNKNOWN_POSITION_NOTICE
    return text
