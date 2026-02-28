from astrbot.core.lang import t
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.session_llm_manager import SessionServiceManager

from ...context import PipelineContext
from ..stage import Stage
from .agent_sub_stages.internal import InternalAgentSubStage
from .agent_sub_stages.third_party import ThirdPartyAgentSubStage


class AgentRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config

        self.bot_wake_prefixs: list[str] = self.config["wake_prefix"]
        self.prov_wake_prefix: str = self.config["provider_settings"]["wake_prefix"]
        for bwp in self.bot_wake_prefixs:
            if self.prov_wake_prefix.startswith(bwp):
                logger.info(
                    t("msg-3267978a", res=self.prov_wake_prefix, bwp=bwp),
                )
                self.prov_wake_prefix = self.prov_wake_prefix[len(bwp) :]

        agent_runner_type = self.config["provider_settings"]["agent_runner_type"]
        if agent_runner_type == "local":
            self.agent_sub_stage = InternalAgentSubStage()
        else:
            self.agent_sub_stage = ThirdPartyAgentSubStage()
        await self.agent_sub_stage.initialize(ctx)

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None, None]:
        if not self.ctx.astrbot_config["provider_settings"]["enable"]:
            logger.debug(
                t("msg-97a4d573")
            )
            return

        if not await SessionServiceManager.should_process_llm_request(event):
            logger.debug(
                t("msg-f1a11d2b", res=event.unified_msg_origin)
            )
            return

        async for resp in self.agent_sub_stage.process(event, self.prov_wake_prefix):
            yield resp
