import asyncio
import inspect
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core import astrbot_config, logger
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)
from astrbot.core.agent.runners.deerflow.deerflow_agent_runner import (
    DeerFlowAgentRunner,
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
    from astrbot.core.provider.entities import LLMResponse
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
    "deerflow": "deerflow_agent_runner_provider_id",
}
THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY = "_third_party_runner_error"
STREAM_CONSUMPTION_CLOSE_TIMEOUT_SEC = 30


def _set_runner_error_extra(event: "AstrMessageEvent", is_error: bool) -> None:
    event.set_extra(THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY, is_error)


def _resolve_final_result(
    merged_chain: list,
    final_resp: "LLMResponse | None",
    has_intermediate_error: bool,
) -> tuple[list, bool, ResultContentType]:
    if not final_resp or not final_resp.result_chain:
        if merged_chain:
            is_error = has_intermediate_error
            content_type = (
                ResultContentType.AGENT_RUNNER_ERROR
                if is_error
                else ResultContentType.LLM_RESULT
            )
            return merged_chain, is_error, content_type

        fallback_error_chain = MessageChain().message(
            "Agent Runner did not return any result.",
        )
        return (
            fallback_error_chain.chain or [],
            True,
            ResultContentType.AGENT_RUNNER_ERROR,
        )

    is_error = has_intermediate_error or final_resp.role == "err"
    content_type = (
        ResultContentType.AGENT_RUNNER_ERROR
        if is_error
        else ResultContentType.LLM_RESULT
    )
    return final_resp.result_chain.chain or [], is_error, content_type


async def run_third_party_agent(
    runner: "BaseAgentRunner",
    stream_to_general: bool = False,
    custom_error_message: str | None = None,
) -> AsyncGenerator["_ThirdPartyRunnerOutput", None]:
    """
    运行第三方 agent runner 并转换响应格式
    类似于 run_agent 函数，但专门处理第三方 agent runner
    """
    try:
        async for resp in runner.step_until_done(max_step=30):  # type: ignore[misc]
            if resp.type == "streaming_delta":
                if stream_to_general:
                    continue
                yield _ThirdPartyRunnerOutput(
                    chain=resp.data["chain"],
                    is_error=False,
                )
            elif resp.type == "llm_result":
                if stream_to_general:
                    yield _ThirdPartyRunnerOutput(
                        chain=resp.data["chain"],
                        is_error=False,
                    )
            elif resp.type == "err":
                yield _ThirdPartyRunnerOutput(
                    chain=resp.data["chain"],
                    is_error=True,
                )
    except Exception as e:
        logger.error(f"Third party agent runner error: {e}")
        err_msg = custom_error_message
        if not err_msg:
            err_msg = (
                f"Error occurred during AI execution.\n"
                f"Error Type: {type(e).__name__} (3rd party)\n"
                f"Error Message: {str(e)}"
            )
        yield _ThirdPartyRunnerOutput(
            chain=MessageChain().message(err_msg),
            is_error=True,
        )


@dataclass
class _ThirdPartyRunnerOutput:
    chain: MessageChain
    is_error: bool = False


async def _close_runner_if_supported(runner: "BaseAgentRunner") -> None:
    close_callable = getattr(runner, "close", None)
    if not callable(close_callable):
        return

    try:
        close_result = close_callable()
        if inspect.isawaitable(close_result):
            await close_result
    except Exception as e:
        logger.warning(f"Failed to close third-party runner cleanly: {e}")


class _RunnerLifecycle:
    def __init__(self, runner: "BaseAgentRunner") -> None:
        self._runner = runner
        self._closed = False
        self._stream_started = False
        self._stream_consumed = False
        self._idle_task: asyncio.Task[None] | None = None

    async def reset(
        self,
        *,
        req: ProviderRequest,
        astr_agent_ctx: AstrAgentContext,
        provider_cfg: dict,
        streaming: bool,
    ) -> None:
        await self._runner.reset(
            request=req,
            run_context=AgentContextWrapper(
                context=astr_agent_ctx,
                tool_call_timeout=60,
            ),
            agent_hooks=MAIN_AGENT_HOOKS,
            provider_config=provider_cfg,
            streaming=streaming,
        )

    async def close_once(self) -> None:
        if self._closed:
            return
        self._closed = True
        await _close_runner_if_supported(self._runner)

    def mark_stream_started(self) -> None:
        self._stream_started = True
        self._idle_task = asyncio.create_task(self._close_if_never_consumed())

    def mark_stream_consumed(self) -> None:
        self._stream_consumed = True
        if self._idle_task and not self._idle_task.done():
            self._idle_task.cancel()

    async def finalize(self) -> None:
        if (
            self._idle_task
            and not self._idle_task.done()
            and (not self._stream_started or self._stream_consumed or self._closed)
        ):
            self._idle_task.cancel()

        if not self._stream_started:
            await self.close_once()

    async def _close_if_never_consumed(self) -> None:
        try:
            await asyncio.sleep(STREAM_CONSUMPTION_CLOSE_TIMEOUT_SEC)
        except asyncio.CancelledError:
            return

        if not self._stream_consumed:
            logger.warning(
                "Third-party runner stream was never consumed; closing runner to avoid resource leak.",
            )
            await self.close_once()


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

    async def _handle_streaming_response(
        self,
        *,
        lifecycle: _RunnerLifecycle,
        runner: "BaseAgentRunner",
        event: AstrMessageEvent,
        custom_error_message: str | None,
    ) -> AsyncGenerator[None, None]:
        stream_has_runner_error = False

        async def _stream_runner_chain() -> AsyncGenerator[MessageChain, None]:
            nonlocal stream_has_runner_error
            lifecycle.mark_stream_consumed()
            try:
                async for runner_output in run_third_party_agent(
                    runner,
                    stream_to_general=False,
                    custom_error_message=custom_error_message,
                ):
                    if runner_output.is_error:
                        stream_has_runner_error = True
                        _set_runner_error_extra(event, True)
                    yield runner_output.chain
            finally:
                # Streaming runner cleanup must happen after consumer
                # finishes iterating to avoid tearing down active streams.
                await lifecycle.close_once()

        event.set_result(
            MessageEventResult()
            .set_result_content_type(ResultContentType.STREAMING_RESULT)
            .set_async_stream(_stream_runner_chain()),
        )
        lifecycle.mark_stream_started()
        yield

        if runner.done():
            final_resp = runner.get_final_llm_resp()
            if final_resp and final_resp.result_chain:
                (
                    final_chain,
                    is_runner_error,
                    _,
                ) = _resolve_final_result(
                    merged_chain=[],
                    final_resp=final_resp,
                    has_intermediate_error=stream_has_runner_error,
                )
                _set_runner_error_extra(event, is_runner_error)
                event.set_result(
                    MessageEventResult(
                        chain=final_chain,
                        result_content_type=ResultContentType.STREAMING_FINISH,
                    ),
                )

    async def _handle_non_streaming_response(
        self,
        *,
        runner: "BaseAgentRunner",
        event: AstrMessageEvent,
        stream_to_general: bool,
        custom_error_message: str | None,
    ) -> AsyncGenerator[None, None]:
        merged_chain: list = []
        has_intermediate_error = False
        async for output in run_third_party_agent(
            runner,
            stream_to_general=stream_to_general,
            custom_error_message=custom_error_message,
        ):
            merged_chain.extend(output.chain.chain or [])
            if output.is_error:
                has_intermediate_error = True
            yield

        final_resp = runner.get_final_llm_resp()
        if not final_resp or not final_resp.result_chain:
            if merged_chain:
                logger.warning(
                    "Agent Runner returned no final response, fallback to streamed error/result chain."
                )
            else:
                logger.warning("Agent Runner 未返回最终结果。")

        (
            final_chain,
            is_runner_error,
            result_content_type,
        ) = _resolve_final_result(
            merged_chain=merged_chain,
            final_resp=final_resp,
            has_intermediate_error=has_intermediate_error,
        )
        _set_runner_error_extra(event, is_runner_error)
        event.set_result(
            MessageEventResult(
                chain=final_chain,
                result_content_type=result_content_type,
            ),
        )
        yield

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
            logger.error("没有填写 Agent Runner 提供商 ID，请前往配置页面配置。")
            return
        if not self.prov_cfg:
            logger.error(
                f"Agent Runner 提供商 {self.prov_id} 配置不存在，请前往配置页面修改配置。"
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
        elif self.runner_type == "deerflow":
            runner = DeerFlowAgentRunner[AstrAgentContext]()
        else:
            raise ValueError(
                f"Unsupported third party agent runner type: {self.runner_type}",
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

        lifecycle = _RunnerLifecycle(runner)

        try:
            await lifecycle.reset(
                req=req,
                astr_agent_ctx=astr_agent_ctx,
                provider_cfg=self.prov_cfg,
                streaming=streaming_response,
            )
            if streaming_response and not stream_to_general:
                async for _ in self._handle_streaming_response(
                    lifecycle=lifecycle,
                    runner=runner,
                    event=event,
                    custom_error_message=custom_error_message,
                ):
                    yield
            else:
                async for _ in self._handle_non_streaming_response(
                    runner=runner,
                    event=event,
                    stream_to_general=stream_to_general,
                    custom_error_message=custom_error_message,
                ):
                    yield
        finally:
            await lifecycle.finalize()

        asyncio.create_task(
            Metric.upload(
                llm_tick=1,
                model_name=self.runner_type,
                provider_type=self.runner_type,
            ),
        )
