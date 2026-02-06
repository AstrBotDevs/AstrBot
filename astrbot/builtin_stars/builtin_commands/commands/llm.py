from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_LLM,
    toggle_chain_runtime_flag,
)


class LLMCommands:
    def __init__(self, context: star.Context):
        self.context = context

    async def llm(self, event: AstrMessageEvent):
        chain_config = event.chain_config
        if not chain_config:
            event.set_result(MessageEventResult().message("No routed chain found."))
            return

        enabled = await toggle_chain_runtime_flag(chain_config.chain_id, FEATURE_LLM)
        status = "enabled" if enabled else "disabled"
        event.set_result(
            MessageEventResult().message(
                f"LLM for chain `{chain_config.chain_id}` is now {status}."
            )
        )
