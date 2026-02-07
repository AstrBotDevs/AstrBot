import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from astrbot.core import astrbot_config, logger
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)
from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)

if TYPE_CHECKING:
    from astrbot.core.agent.runners.base import BaseAgentRunner
from astrbot.core.astr_agent_context import AgentContextWrapper, AstrAgentContext
from astrbot.core.astr_agent_hooks import MAIN_AGENT_HOOKS
from astrbot.core.pipeline.agent.runner_config import AGENT_RUNNER_PROVIDER_KEY
from astrbot.core.pipeline.agent.types import AgentRunOutcome
from astrbot.core.pipeline.context import PipelineContext, call_event_hook
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import (
    ProviderRequest,
)
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.metrics import Metric


async def run_third_party_agent(
    runner: "BaseAgentRunner",
    stream_to_general: bool = False,
) -> AsyncGenerator[MessageChain | None, None]:
    """
    运行第三方 agent runner 并转换响应格式
    类似于 run_agent 函数，但专门处理第三方 agent runner
    """
    try:
        async for resp in runner.step_until_done(max_step=30):  # type: ignore[misc]
            if resp.type == "streaming_delta":
                if stream_to_general:
                    continue
                yield resp.data["chain"]
            elif resp.type == "llm_result":
                if stream_to_general:
                    yield resp.data["chain"]
    except Exception as e:
        logger.error(f"Third party agent runner error: {e}")
        err_msg = (
            f"\nAstrBot 请求失败。\n错误类型: {type(e).__name__}\n"
            f"错误信息: {e!s}\n\n请在平台日志查看和分享错误详情。\n"
        )
        yield MessageChain().message(err_msg)


class ThirdPartyAgentExecutor:
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.conf = ctx.astrbot_config
        settings = ctx.astrbot_config["provider_settings"]
        self.streaming_response: bool = settings["streaming_response"]
        self.unsupported_streaming_strategy: str = settings[
            "unsupported_streaming_strategy"
        ]

    async def run(
        self,
        event: AstrMessageEvent,
        provider_wake_prefix: str,
        *,
        runner_type: str,
        provider_id: str,
    ) -> AgentRunOutcome:
        outcome = AgentRunOutcome()
        req: ProviderRequest | None = None

        if provider_wake_prefix and not event.message_str.startswith(
            provider_wake_prefix
        ):
            return outcome

        if runner_type not in AGENT_RUNNER_PROVIDER_KEY:
            logger.error("Unsupported third party agent runner type: %s", runner_type)
            return outcome

        if not provider_id:
            logger.error("没有填写 Agent Runner 提供商 ID，请在 Agent 节点配置中设置。")
            return outcome

        prov_cfg: dict = next(
            (p for p in astrbot_config["provider"] if p["id"] == provider_id),
            {},
        )
        if not prov_cfg:
            logger.error(
                "Agent Runner 提供商 %s 配置不存在，请检查 Agent 节点配置。",
                provider_id,
            )
            return outcome

        # make provider request
        req = ProviderRequest()
        req.session_id = event.unified_msg_origin
        req.prompt = event.message_str[len(provider_wake_prefix) :]
        for comp in event.message_obj.message:
            if isinstance(comp, Image):
                image_path = await comp.convert_to_base64()
                req.image_urls.append(image_path)

        if not req.prompt and not req.image_urls:
            return outcome

        # call event hook
        if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
            return outcome

        if runner_type == "dify":
            runner = DifyAgentRunner[AstrAgentContext]()
        elif runner_type == "coze":
            runner = CozeAgentRunner[AstrAgentContext]()
        elif runner_type == "dashscope":
            runner = DashscopeAgentRunner[AstrAgentContext]()
        else:
            raise ValueError(
                f"Unsupported third party agent runner type: {runner_type}",
            )

        astr_agent_ctx = AstrAgentContext(
            context=self.ctx.plugin_manager.context,
            event=event,
        )

        streaming_response = self.streaming_response
        if (enable_streaming := event.get_extra("enable_streaming")) is not None:
            streaming_response = bool(enable_streaming)

        stream_to_general = (
            self.unsupported_streaming_strategy == "turn_off"
            and not event.platform_meta.support_streaming_message
        )

        await runner.reset(
            request=req,
            run_context=AgentContextWrapper(
                context=astr_agent_ctx,
                tool_call_timeout=60,
            ),
            agent_hooks=MAIN_AGENT_HOOKS,
            provider_config=prov_cfg,
            streaming=streaming_response,
        )
        outcome.handled = True

        if streaming_response and not stream_to_general:
            # 流式响应
            async def wrapped_stream():
                async for chunk in run_third_party_agent(
                    runner,
                    stream_to_general=False,
                ):
                    yield chunk

                asyncio.create_task(
                    Metric.upload(
                        llm_tick=1,
                        model_name=runner_type,
                        provider_type=runner_type,
                    ),
                )

            event.set_result(
                MessageEventResult()
                .set_result_content_type(ResultContentType.STREAMING_RESULT)
                .set_async_stream(wrapped_stream()),
            )
            outcome.streaming = True
            outcome.result = event.get_result()
            outcome.stopped = event.is_stopped()
            return outcome
        else:
            # 非流式响应或转换为普通响应
            async for _ in run_third_party_agent(
                runner,
                stream_to_general=stream_to_general,
            ):
                pass

            final_resp = runner.get_final_llm_resp()

            if not final_resp or not final_resp.result_chain:
                logger.warning("Agent Runner 未返回最终结果。")
                return outcome

            event.set_result(
                MessageEventResult(
                    chain=final_resp.result_chain.chain or [],
                    result_content_type=ResultContentType.LLM_RESULT,
                ),
            )

        asyncio.create_task(
            Metric.upload(
                llm_tick=1,
                model_name=runner_type,
                provider_type=runner_type,
            ),
        )

        outcome.result = event.get_result()
        outcome.stopped = event.is_stopped()
        return outcome
