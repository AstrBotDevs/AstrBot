"""Queue nonempty follow-up messages using the original wake-up identity."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

from astrbot.api.message_components import At

if TYPE_CHECKING:
    from astrbot.api.event import AstrMessageEvent
    from astrbot.api.star import Context
    from astrbot.core.utils.session_waiter import SessionController


def enqueue_mentioned_followup(
    context: Context, controller: SessionController, event: AstrMessageEvent
) -> None:
    """Queue a shallow event copy before stopping the current waiter event."""
    if not event.message_str or not event.message_str.strip():
        return
    event.message_obj.message.insert(
        0, At(qq=event.get_self_id(), name=event.get_self_id())
    )
    context.get_event_queue().put_nowait(copy.copy(event))
    event.stop_event()
    controller.stop()
