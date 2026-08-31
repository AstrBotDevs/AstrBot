from collections.abc import AsyncGenerator

from astrbot import logger
from astrbot.core.config.agent_runner import normalize_agent_runner_for_load
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.session_llm_manager import SessionServiceManager

from ...context import PipelineContext
from ...stage import Stage
from .agent_sub_stages.internal import InternalAgentSubStage
from .agent_sub_stages.third_party import ThirdPartyAgentSubStage


class AgentRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config
        if ctx.preferences is None:
            raise RuntimeError("AgentRequestSubStage requires shared preferences")
        self.session_services = SessionServiceManager(ctx.preferences)

        agent_runner = normalize_agent_runner_for_load(self.config.get("agent_runner"))
        self.config["agent_runner"] = agent_runner
        agent_runner_type = agent_runner["runner_type"]
        if agent_runner_type == "local":
            self.agent_sub_stage = InternalAgentSubStage()
        else:
            self.agent_sub_stage = ThirdPartyAgentSubStage()
        await self.agent_sub_stage.initialize(ctx)

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        if not self.ctx.astrbot_config["provider_settings"]["enable"]:
            logger.debug(
                "This pipeline does not enable AI capability, skip processing."
            )
            return

        if not await self.session_services.should_process_llm_request(event):
            logger.debug(
                f"The session {event.unified_msg_origin} has disabled AI capability, skipping processing."
            )
            return

        async for resp in self.agent_sub_stage.process(event):
            yield resp
