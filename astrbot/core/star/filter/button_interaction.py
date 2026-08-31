from astrbot.core.config import AstrBotConfig
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from . import HandlerFilter


class ButtonInteractionFilter(HandlerFilter):
    """Match portable button interactions, optionally by action ID."""

    def __init__(self, action_id: str | None = None) -> None:
        self.action_id = action_id

    def filter(self, event: AstrMessageEvent, cfg: AstrBotConfig) -> bool:
        """Return whether an event carries the requested button action.

        Args:
            event: Incoming AstrBot message event.
            cfg: Active AstrBot configuration.

        Returns:
            Whether the event contains a matching button interaction.
        """
        interaction = event.get_button_interaction()
        return interaction is not None and (
            self.action_id is None or interaction.action_id == self.action_id
        )
