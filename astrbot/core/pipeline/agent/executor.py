from __future__ import annotations

from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.pipeline.agent.internal import InternalAgentExecutor
from astrbot.core.pipeline.agent.third_party import ThirdPartyAgentExecutor
from astrbot.core.pipeline.context import PipelineContext
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

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None, None]:
        if not self.ctx.astrbot_config["provider_settings"]["enable"]:
            logger.debug(
                "This pipeline does not enable AI capability, skip processing."
            )
            return

        async for resp in self.executor.process(event, self.prov_wake_prefix):
            yield resp
