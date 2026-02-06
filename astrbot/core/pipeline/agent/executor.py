from __future__ import annotations

from astrbot.core import logger
from astrbot.core.pipeline.agent.internal import InternalAgentExecutor
from astrbot.core.pipeline.agent.third_party import ThirdPartyAgentExecutor
from astrbot.core.pipeline.agent.types import AgentRunOutcome
from astrbot.core.pipeline.context import PipelineContext
from astrbot.core.pipeline.engine.chain_runtime_flags import (
    FEATURE_LLM,
    is_chain_runtime_feature_enabled,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent


class AgentExecutor:
    """Native agent executor for the new pipeline."""

    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config

        self.bot_wake_prefixs: list[str] = self.config["wake_prefix"]
        self.prov_wake_prefix: str = self.config["provider_settings"]["wake_prefix"]
        for bwp in self.bot_wake_prefixs:
            if self.prov_wake_prefix.startswith(bwp):
                logger.info(
                    f"识别 LLM 聊天额外唤醒前缀 {self.prov_wake_prefix} 以机器人唤醒前缀 {bwp} 开头，已自动去除。",
                )
                self.prov_wake_prefix = self.prov_wake_prefix[len(bwp) :]

        agent_runner_type = self.config["provider_settings"]["agent_runner_type"]
        if agent_runner_type == "local":
            self.executor = InternalAgentExecutor()
        else:
            self.executor = ThirdPartyAgentExecutor()
        await self.executor.initialize(ctx)

    async def run(self, event: AstrMessageEvent) -> AgentRunOutcome:
        outcome = AgentRunOutcome()
        chain_id = event.chain_config.chain_id if event.chain_config else None
        if not await is_chain_runtime_feature_enabled(chain_id, FEATURE_LLM):
            logger.debug(
                "Current chain runtime LLM switch is disabled, skip processing."
            )
            return outcome

        return await self.executor.run(event, self.prov_wake_prefix)
