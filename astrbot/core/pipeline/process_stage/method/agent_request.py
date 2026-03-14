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
                    f"识别 LLM 聊天额外唤醒前缀 {self.prov_wake_prefix} 以机器人唤醒前缀 {bwp} 开头，已自动去除。",
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
                "This pipeline does not enable AI capability, skip processing."
            )
            return

        if not await SessionServiceManager.should_process_llm_request(event):
            logger.debug(
                f"The session {event.unified_msg_origin} has disabled AI capability, skipping processing."
            )
            return

        # 根据是否为高级人格选择子阶段
        sub_stage = self.agent_sub_stage
        if event.is_advanced_persona and self.mind_sub_stage:
            logger.debug(
                f"会话 {event.unified_msg_origin} 使用高级人格，使用 InternalMindSubStage"
            )
            sub_stage = self.mind_sub_stage

        # 将事件和提供商唤醒前缀传递给代理子阶段处理
        # 异步生成所有响应
        async for resp in sub_stage.process(event, self.prov_wake_prefix):
            # 生成每个响应
            yield resp
