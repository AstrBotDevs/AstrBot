"""Portable button rendering for WeCom AI Bot template cards."""

import uuid

from astrbot.api.message_components import (
    ActionRow,
    ButtonStyle,
    CallbackAction,
    UrlAction,
)
from astrbot.core.platform.button_interaction import encode_button_callback

_BUTTON_STYLE_MAP = {
    ButtonStyle.DEFAULT: 4,
    ButtonStyle.PRIMARY: 1,
    ButtonStyle.SUCCESS: 3,
    ButtonStyle.DANGER: 2,
}


def build_wecom_button_card(
    rows: list[ActionRow],
    task_id: str | None = None,
) -> dict | None:
    """Build one WeCom button-interaction template card.

    WeCom displays at most six buttons in one interaction card. Portable rows are
    flattened because the native card format does not preserve row boundaries.

    Args:
        rows: Portable action rows to render.
        task_id: Existing WeCom task ID when replacing a clicked card.

    Returns:
        A WeCom template-card object, or ``None`` when no buttons are present.

    Raises:
        ValueError: More than six buttons were supplied for one card.
    """
    buttons = [button for row in rows for button in row.buttons]
    if not buttons:
        return None
    if len(buttons) > 6:
        raise ValueError("WeCom AI Bot supports at most 6 buttons per card.")

    native_buttons = []
    for button in buttons:
        native_button = {
            "text": (button.label or button.id)[:10],
            "style": _BUTTON_STYLE_MAP[button.style],
        }
        if isinstance(button.action, CallbackAction):
            native_button.update(
                {
                    "type": 0,
                    "key": encode_button_callback(button.id, button.action.data),
                }
            )
        elif isinstance(button.action, UrlAction):
            native_button.update({"type": 1, "url": button.action.url})
        native_buttons.append(native_button)

    title = next(
        (
            row.fallback_text.strip()
            for row in rows
            if row.fallback_text and row.fallback_text.strip()
        ),
        "Choose an action",
    )
    return {
        "card_type": "button_interaction",
        "main_title": {"title": title[:26]},
        "button_list": native_buttons,
        "task_id": task_id or f"astrbot_{uuid.uuid4().hex}",
    }
