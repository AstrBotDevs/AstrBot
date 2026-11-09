from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.config.agent import normalize_agent
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
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

        self.bot_wake_prefixs: list[str] = self.config["wake_prefix"]
        self.prov_wake_prefix: str = self.config["provider_settings"]["wake_prefix"]
        for bwp in self.bot_wake_prefixs:
            if self.prov_wake_prefix.startswith(bwp):
                logger.info(
                    f"The additional LLM wake prefix {self.prov_wake_prefix} starts "
                    f"with the bot wake prefix {bwp}; the duplicate prefix was "
                    "removed automatically.",
                )
                self.prov_wake_prefix = self.prov_wake_prefix[len(bwp) :]

        agent_runner = normalize_agent(self.config.get("agent"))
        self.config["agent"] = agent_runner
        agent_runner_type = agent_runner["runtime"]
        self.runtime_sub_stage = InternalAgentSubStage()
        await self.runtime_sub_stage.initialize(ctx)
        if agent_runner_type in ctx.agent_runtimes:
            self.agent_sub_stage = self.runtime_sub_stage
        elif agent_runner_type in ("dify", "coze", "dashscope", "deerflow"):
            self.agent_sub_stage = ThirdPartyAgentSubStage()
            await self.agent_sub_stage.initialize(ctx)
        else:
            raise RuntimeError(f"Agent runtime unavailable: {agent_runner_type}")

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None, None]:
        if not self.ctx.astrbot_config["provider_settings"]["enable"]:
            logger.debug(
                "This pipeline does not enable AI capability, skip processing."
            )
            return

        if not await SessionServiceManager.should_process_llm_request(event):
            logger.debug(
                f"The session {event.unified_msg_origin} has disabled AI capability, skipping processing."
            )
            return

        agent_config = self.config.get("agent", {})
        runtime_name = (
            event.agent_session.runtime
            if isinstance(event, AgentWakeupEvent) and event.agent_session is not None
            else agent_config.get("runtime", "astrbot")
        )
        event.trace.record(
            "agent_start",
            kind="agent",
            status="running",
            runner_type=runtime_name,
            provider_wake_prefix=self.prov_wake_prefix,
        )
        try:
            stage = (
                self.runtime_sub_stage
                if isinstance(event, AgentWakeupEvent)
                and event.agent_session is not None
                else self.agent_sub_stage
            )
            async for resp in stage.process(event, self.prov_wake_prefix):
                yield resp
        except BaseException as exc:
            event.trace.record(
                "agent_end",
                kind="agent",
                status="error",
                error=str(exc),
                runner_type=runtime_name,
            )
            raise
        else:
            event.trace.record(
                "agent_end",
                kind="agent",
                status="success",
                runner_type=runtime_name,
            )
