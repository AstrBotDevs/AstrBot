from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ...context import PipelineContext
from ..stage import Stage
from .agent_sub_stages.internal import InternalAgentSubStage
from .agent_sub_stages.third_party import ThirdPartyAgentSubStage


class AgentRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.internal_agent_sub_stage = InternalAgentSubStage()
        self.third_party_agent_sub_stage = ThirdPartyAgentSubStage()
        await self.internal_agent_sub_stage.initialize(ctx)
        await self.third_party_agent_sub_stage.initialize(ctx)

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None, None]:
        config = self.ctx.astrbot_config
        provider_settings = config["provider_settings"]
        if not provider_settings["enable"]:
            logger.debug(
                "This pipeline does not enable AI capability, skip processing."
            )
            return

        bot_wake_prefixes: list[str] = config["wake_prefix"]
        provider_wake_prefix: str = provider_settings["wake_prefix"]
        for bot_wake_prefix in bot_wake_prefixes:
            if provider_wake_prefix.startswith(bot_wake_prefix):
                logger.info(
                    f"识别 LLM 聊天额外唤醒前缀 {provider_wake_prefix} 以机器人唤醒前缀 {bot_wake_prefix} 开头，已自动去除。",
                )
                provider_wake_prefix = provider_wake_prefix[len(bot_wake_prefix) :]

        agent_sub_stage = (
            self.internal_agent_sub_stage
            if provider_settings["agent_runner_type"] == "local"
            else self.third_party_agent_sub_stage
        )
        async for resp in agent_sub_stage.process(event, provider_wake_prefix):
            yield resp
