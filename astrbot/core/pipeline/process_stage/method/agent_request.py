from collections.abc import AsyncGenerator
from contextlib import aclosing

from astrbot.core.config.agent import normalize_agent
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import AstrMessageEvent

from ...context import PipelineContext
from ...stage import Stage
from .agent_sub_stages.internal import InternalAgentSubStage
from .agent_sub_stages.third_party import ThirdPartyAgentSubStage


class AgentRequestSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.config = ctx.astrbot_config

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
        config = self.ctx.plugin_manager.context.get_config(
            umo=event.unified_msg_origin
        )
        if not config["provider_settings"]["enable"]:
            return

        provider_wake_prefix = config["provider_settings"]["wake_prefix"]
        for prefix in config["wake_prefix"]:
            if provider_wake_prefix.startswith(prefix):
                provider_wake_prefix = provider_wake_prefix[len(prefix) :]

        agent_config = config.get("agent", {})
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
            provider_wake_prefix=provider_wake_prefix,
        )
        try:
            stage = (
                self.runtime_sub_stage
                if isinstance(event, AgentWakeupEvent)
                and event.agent_session is not None
                else self.agent_sub_stage
            )
            async with aclosing(
                stage.process(event, provider_wake_prefix)
            ) as responses:
                async for resp in responses:
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
