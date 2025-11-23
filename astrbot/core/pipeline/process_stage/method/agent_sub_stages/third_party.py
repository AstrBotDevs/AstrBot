import asyncio
from collections.abc import AsyncGenerator

from astrbot.core import logger
from astrbot.core.agent.runners.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.dashscope_agent_runner import DashscopeAgentRunner
from astrbot.core.agent.runners.dify_agent_runner import DifyAgentRunner
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import (
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import (
    ProviderRequest,
)
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.metrics import Metric

from .....astr_agent_context import AgentContextWrapper, AstrAgentContext
from .....astr_agent_hooks import MAIN_AGENT_HOOKS
from ....context import PipelineContext, call_event_hook
from ...stage import Stage

AGENT_RUNNER_TYPE_KEY = {
    "dify": "dify_agent_runner_provider_id",
    "coze": "coze_agent_runner_provider_id",
    "dashscope": "dashscope_agent_runner_provider_id",
}


class ThirdPartyAgentSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.conf = ctx.astrbot_config
        self.runner_type = self.conf["provider_settings"]["agent_runner_type"]
        self.prov_id = self.conf["provider_settings"].get(
            AGENT_RUNNER_TYPE_KEY.get(self.runner_type, ""),
            "",
        )
        self.prov_cfg: dict = next(
            (p for p in self.conf["provider"] if p["id"] == self.prov_id),
            {},
        )

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        req: ProviderRequest | None = None

        if provider_wake_prefix and not event.message_str.startswith(
            provider_wake_prefix
        ):
            return
        if not self.prov_id or not self.prov_cfg:
            logger.error(
                "Third Party Agent Runner provider ID is not configured properly."
            )
            return

        # make provider request
        req = ProviderRequest()
        req.session_id = event.unified_msg_origin
        req.prompt = event.message_str[len(provider_wake_prefix) :]
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                image_path = await comp.convert_to_base64()
                req.image_urls.append(image_path)

        if not req.prompt and not req.image_urls:
            return

        # call event hook
        if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
            return

        if self.runner_type == "dify":
            runner = DifyAgentRunner[AstrAgentContext]()
        elif self.runner_type == "coze":
            runner = CozeAgentRunner[AstrAgentContext]()
        elif self.runner_type == "dashscope":
            runner = DashscopeAgentRunner[AstrAgentContext]()
        else:
            raise ValueError(
                f"Unsupported third party agent runner type: {self.runner_type}",
            )

        astr_agent_ctx = AstrAgentContext(
            context=self.ctx.plugin_manager.context,
            event=event,
        )

        await runner.reset(
            request=req,
            run_context=AgentContextWrapper(
                context=astr_agent_ctx,
                tool_call_timeout=60,
            ),
            agent_hooks=MAIN_AGENT_HOOKS,
            provider_config=self.prov_cfg,
        )

        async for _ in runner.step_until_done():
            pass

        final_resp = runner.get_final_llm_resp()

        if not final_resp or not final_resp.result_chain:
            logger.warning("Agent Runner 未返回最终结果。")
            return

        event.set_result(
            MessageEventResult(
                chain=final_resp.result_chain.chain or [],
                result_content_type=ResultContentType.LLM_RESULT,
            ),
        )
        yield

        asyncio.create_task(
            Metric.upload(
                llm_tick=1,
                model_name=self.runner_type,
                provider_type=self.runner_type,
            ),
        )
