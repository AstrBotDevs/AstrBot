"""Filter plugin view interactions without matching portable buttons."""

from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class UIActionFilter(HandlerFilter):
    """Match a view action within its owning plugin."""

    def __init__(self, action_id: str | None = None):
        self.action_id = action_id

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Match a normalized UI event.

        Args:
            event: Incoming message event.
            cfg: Active session configuration.

        Returns:
            Whether the event is a matching view action.
        """
        interaction = event.get_ui_interaction()
        return interaction is not None and (
            self.action_id is None or self.action_id == interaction.action_id
        )
