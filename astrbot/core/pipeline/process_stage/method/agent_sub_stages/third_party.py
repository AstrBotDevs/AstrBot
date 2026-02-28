from astrbot.core.lang import t
import asyncio
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from astrbot.core import astrbot_config, logger
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)
from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner
from astrbot.core.astr_agent_hooks import MAIN_AGENT_HOOKS
from astrbot.core.message.components import Image
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    resolve_event_conversation_persona_id,
    resolve_persona_custom_error_message,
    set_persona_custom_error_message_on_event,
)

if TYPE_CHECKING:
    from astrbot.core.agent.runners.base import BaseAgentRunner
from astrbot.core.pipeline.stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import (
    ProviderRequest,
)
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.metrics import Metric

from .....astr_agent_context import AgentContextWrapper, AstrAgentContext
from ....context import PipelineContext, call_event_hook

AGENT_RUNNER_TYPE_KEY = {
    "dify": "dify_agent_runner_provider_id",
    "coze": "coze_agent_runner_provider_id",
    "dashscope": "dashscope_agent_runner_provider_id",
}


async def run_third_party_agent(
    runner: "BaseAgentRunner",
    stream_to_general: bool = False,
    custom_error_message: str | None = None,
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
<<<<<<< HEAD
        logger.error(t("msg-5e551baf", e=e))
        err_msg = (
            f"\nAstrBot 请求失败。\n错误类型: {type(e).__name__}\n"
            f"错误信息: {e!s}\n\n请在平台日志查看和分享错误详情。\n"
        )
        yield MessageChain().message(t("msg-34f164d4", err_msg=err_msg))
=======
        logger.error(f"Third party agent runner error: {e}")
        err_msg = custom_error_message
        if not err_msg:
            err_msg = (
                f"\nAstrBot 请求失败。\n错误类型: {type(e).__name__}\n"
                f"错误信息: {e!s}\n\n请在平台日志查看和分享错误详情。\n"
            )
        yield MessageChain().message(err_msg)
>>>>>>> 9214d48a2d9d411c784cf0ee9f852aaf08d45a90


class ThirdPartyAgentSubStage(Stage):
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        self.conf = ctx.astrbot_config
        self.runner_type = self.conf["provider_settings"]["agent_runner_type"]
        self.prov_id = self.conf["provider_settings"].get(
            AGENT_RUNNER_TYPE_KEY.get(self.runner_type, ""),
            "",
        )
        settings = ctx.astrbot_config["provider_settings"]
        self.streaming_response: bool = settings["streaming_response"]
        self.unsupported_streaming_strategy: str = settings[
            "unsupported_streaming_strategy"
        ]

    async def _resolve_persona_custom_error_message(
        self, event: AstrMessageEvent
    ) -> str | None:
        try:
            conversation_persona_id = await resolve_event_conversation_persona_id(
                event,
                self.ctx.plugin_manager.context.conversation_manager,
            )
            return await resolve_persona_custom_error_message(
                event=event,
                persona_manager=self.ctx.plugin_manager.context.persona_manager,
                provider_settings=self.conf["provider_settings"],
                conversation_persona_id=conversation_persona_id,
            )
        except Exception as e:
            logger.debug("Failed to resolve persona custom error message: %s", e)
            return None

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        req: ProviderRequest | None = None

        if provider_wake_prefix and not event.message_str.startswith(
            provider_wake_prefix
        ):
            return

        self.prov_cfg: dict = next(
            (p for p in astrbot_config["provider"] if p["id"] == self.prov_id),
            {},
        )
        if not self.prov_id:
            logger.error(t("msg-f9d76893"))
            return
        if not self.prov_cfg:
            logger.error(
                t("msg-0f856470", res=self.prov_id)
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

        custom_error_message = await self._resolve_persona_custom_error_message(event)
        set_persona_custom_error_message_on_event(event, custom_error_message)

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
                t("msg-b3f25c81", res=self.runner_type),
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
            provider_config=self.prov_cfg,
            streaming=streaming_response,
        )

        if streaming_response and not stream_to_general:
            # 流式响应
            event.set_result(
                MessageEventResult()
                .set_result_content_type(ResultContentType.STREAMING_RESULT)
                .set_async_stream(
                    run_third_party_agent(
                        runner,
                        stream_to_general=False,
                        custom_error_message=custom_error_message,
                    ),
                ),
            )
            yield
            if runner.done():
                final_resp = runner.get_final_llm_resp()
                if final_resp and final_resp.result_chain:
                    event.set_result(
                        MessageEventResult(
                            chain=final_resp.result_chain.chain or [],
                            result_content_type=ResultContentType.STREAMING_FINISH,
                        ),
                    )
        else:
            # 非流式响应或转换为普通响应
            async for _ in run_third_party_agent(
                runner,
                stream_to_general=stream_to_general,
                custom_error_message=custom_error_message,
            ):
                yield

            final_resp = runner.get_final_llm_resp()

            if not final_resp or not final_resp.result_chain:
                logger.warning(t("msg-6c63eb68"))
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
