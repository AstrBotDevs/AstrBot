"""Text-to-speech command."""

from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_TTS,
    toggle_chain_runtime_flag,
)

from ._node_binding import get_chain_nodes


class TTSCommand:
    """Toggle text-to-speech for the current routed chain."""

    def __init__(self, context: star.Context):
        self.context = context

    async def tts(self, event: AstrMessageEvent):
        chain_config = event.chain_config
        if not chain_config:
            event.set_result(MessageEventResult().message("No routed chain found."))
            return

        nodes = get_chain_nodes(event, "tts")
        if not nodes:
            event.set_result(
                MessageEventResult().message("Current chain has no TTS node.")
            )
            return

        enabled = await toggle_chain_runtime_flag(chain_config.chain_id, FEATURE_TTS)
        status = "enabled" if enabled else "disabled"
        event.set_result(
            MessageEventResult().message(
                f"TTS is now {status} for chain `{chain_config.chain_id}` ({len(nodes)} node(s))."
            )
        )
