from astrbot.api import star
from astrbot.api.event import AstrMessageEvent, MessageEventResult
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_LLM,
    toggle_chain_runtime_flag,
)


class LLMCommands:
    def __init__(self, context: star.Context) -> None:
        self.context = context

    async def llm(self, event: AstrMessageEvent):
        chain_config = event.chain_config
        if not chain_config:
            event.set_result(MessageEventResult().message("未找到已路由的 Chain。"))
            return

        enabled = await toggle_chain_runtime_flag(chain_config.chain_id, FEATURE_LLM)
        status = "开启" if enabled else "关闭"
        event.set_result(
            MessageEventResult().message(
                f"Chain `{chain_config.chain_id}` 的 LLM 功能已{status}。"
            )
        )
