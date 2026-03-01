import asyncio
import inspect
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import TYPE_CHECKING

from astrbot.core import astrbot_config, logger
from astrbot.core.agent.runners.coze.coze_agent_runner import CozeAgentRunner
from astrbot.core.agent.runners.dashscope.dashscope_agent_runner import (
    DashscopeAgentRunner,
)
from astrbot.core.agent.runners.deerflow.constants import (
    DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
    DEERFLOW_PROVIDER_TYPE,
)
from astrbot.core.agent.runners.deerflow.deerflow_agent_runner import (
    DeerFlowAgentRunner,
)
from astrbot.core.agent.runners.dify.dify_agent_runner import DifyAgentRunner
from astrbot.core.astr_agent_hooks import MAIN_AGENT_HOOKS
from astrbot.core.lang import t
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
from astrbot.core.utils.config_number import coerce_int_config
from astrbot.core.utils.metrics import Metric

from .....astr_agent_context import AgentContextWrapper, AstrAgentContext
from ....context import PipelineContext, call_event_hook

AGENT_RUNNER_TYPE_KEY = {
    "dify": "dify_agent_runner_provider_id",
    "coze": "coze_agent_runner_provider_id",
    "dashscope": "dashscope_agent_runner_provider_id",
    DEERFLOW_PROVIDER_TYPE: DEERFLOW_AGENT_RUNNER_PROVIDER_ID_KEY,
}
THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY = "_third_party_runner_error"
STREAM_CONSUMPTION_CLOSE_TIMEOUT_SEC = 30
RUNNER_NO_RESULT_FALLBACK_MESSAGE = "Agent Runner did not return any result."
RUNNER_NO_FINAL_RESPONSE_LOG = (
    "Agent Runner returned no final response, fallback to streamed error/result chain."
)
RUNNER_NO_RESULT_LOG = "Agent Runner did not return final result."


async def run_third_party_agent(
    runner: "BaseAgentRunner",
    stream_to_general: bool = False,
    custom_error_message: str | None = None,
) -> AsyncGenerator[tuple[MessageChain, bool], None]:
    """
    运行第三方 agent runner 并转换响应格式
    类似于 run_agent 函数，但专门处理第三方 agent runner
    """
    try:
        async for resp in runner.step_until_done(max_step=30):  # type: ignore[misc]
            if resp.type == "streaming_delta":
                if stream_to_general:
                    continue
                yield resp.data["chain"], False
            elif resp.type == "llm_result":
                if stream_to_general:
                    yield resp.data["chain"], False
            elif resp.type == "err":
                yield resp.data["chain"], True
    except Exception as e:
        logger.error(t("msg-5e551baf", e=e))
        err_msg = custom_error_message
        if not err_msg:
            err_msg = (
                f"Error occurred during AI execution.\n"
                f"Error Type: {type(e).__name__} (3rd party)\n"
                f"Error Message: {str(e)}"
            )
        yield MessageChain().message(t("msg-34f164d4", err_msg=err_msg)), True


class _RunnerResultAggregator:
    def __init__(self) -> None:
        self.merged_chain: list = []
        self.has_error = False

    def add_chunk(self, chain: MessageChain, is_error: bool) -> None:
        self.merged_chain.extend(chain.chain or [])
        if is_error:
            self.has_error = True

    def finalize(
        self,
        final_resp: "LLMResponse | None",
    ) -> tuple[list, bool]:
        if not final_resp or not final_resp.result_chain:
            if self.merged_chain:
                logger.warning(RUNNER_NO_FINAL_RESPONSE_LOG)
                return self.merged_chain, self.has_error

            logger.warning(RUNNER_NO_RESULT_LOG)
            fallback_error_chain = MessageChain().message(
                RUNNER_NO_RESULT_FALLBACK_MESSAGE,
            )
            return fallback_error_chain.chain or [], True

        final_chain = final_resp.result_chain.chain or []
        is_runner_error = self.has_error or final_resp.role == "err"
        return final_chain, is_runner_error


def _start_stream_watchdog(
    *,
    timeout_sec: int,
    is_stream_consumed: Callable[[], bool],
    close_runner_once: Callable[[], Awaitable[None]],
) -> asyncio.Task[None]:
    async def _watchdog() -> None:
        try:
            await asyncio.sleep(timeout_sec)
        except asyncio.CancelledError:
            return
        if not is_stream_consumed():
            logger.warning(
                "Third-party runner stream was never consumed in %ss; closing runner to avoid resource leak.",
                timeout_sec,
            )
            try:
                await close_runner_once()
            except Exception:
                logger.warning(
                    "Exception while closing third-party runner from stream watchdog.",
                    exc_info=True,
                )

    return asyncio.create_task(_watchdog())


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
        self.stream_consumption_close_timeout_sec: int = coerce_int_config(
            settings.get(
                "third_party_stream_consumption_close_timeout_sec",
                STREAM_CONSUMPTION_CLOSE_TIMEOUT_SEC,
            ),
            default=STREAM_CONSUMPTION_CLOSE_TIMEOUT_SEC,
            min_value=1,
            field_name="third_party_stream_consumption_close_timeout_sec",
            source="Third-party runner config",
        )

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
            logger.debug(t("msg-371b6b3d", e=e))
            return None

    async def _handle_streaming_response(
        self,
        *,
        runner: "BaseAgentRunner",
        event: AstrMessageEvent,
        custom_error_message: str | None,
        close_runner_once: Callable[[], Awaitable[None]],
        mark_stream_consumed: Callable[[], None],
    ) -> AsyncGenerator[None, None]:
        aggregator = _RunnerResultAggregator()

        async def _stream_runner_chain() -> AsyncGenerator[MessageChain, None]:
            mark_stream_consumed()
            try:
                async for chain, is_error in run_third_party_agent(
                    runner,
                    stream_to_general=False,
                    custom_error_message=custom_error_message,
                ):
                    aggregator.add_chunk(chain, is_error)
                    if is_error:
                        event.set_extra(THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY, True)
                    yield chain
            finally:
                # Streaming runner cleanup must happen after consumer
                # finishes iterating to avoid tearing down active streams.
                await close_runner_once()

        event.set_result(
            MessageEventResult()
            .set_result_content_type(ResultContentType.STREAMING_RESULT)
            .set_async_stream(_stream_runner_chain()),
        )
        yield

        if runner.done():
            final_chain, is_runner_error = aggregator.finalize(
                runner.get_final_llm_resp()
            )
            event.set_extra(THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY, is_runner_error)
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
        aggregator = _RunnerResultAggregator()
        async for chain, is_error in run_third_party_agent(
            runner,
            stream_to_general=stream_to_general,
            custom_error_message=custom_error_message,
        ):
            aggregator.add_chunk(chain, is_error)
            if is_error:
                event.set_extra(THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY, True)
            yield

        final_chain, is_runner_error = aggregator.finalize(runner.get_final_llm_resp())
        event.set_extra(THIRD_PARTY_RUNNER_ERROR_EXTRA_KEY, is_runner_error)
        result_content_type = (
            ResultContentType.AGENT_RUNNER_ERROR
            if is_runner_error
            else ResultContentType.LLM_RESULT
        )
        event.set_result(
            MessageEventResult(
                chain=final_chain,
                result_content_type=result_content_type,
            ),
        )
        # Second yield keeps scheduler progress consistent after final result update.
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
            logger.error(t("msg-f9d76893"))
            return
        if not self.prov_cfg:
            logger.error(t("msg-0f856470", res=self.prov_id))
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
        elif self.runner_type == DEERFLOW_PROVIDER_TYPE:
            runner = DeerFlowAgentRunner[AstrAgentContext]()
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
        streaming_used = streaming_response and not stream_to_general

        runner_closed = False
        stream_consumed = False
        stream_watchdog_task: asyncio.Task[None] | None = None

        async def close_runner_once() -> None:
            nonlocal runner_closed
            if runner_closed:
                return
            runner_closed = True
            await _close_runner_if_supported(runner)

        def mark_stream_consumed() -> None:
            nonlocal stream_consumed
            stream_consumed = True
            if stream_watchdog_task and not stream_watchdog_task.done():
                stream_watchdog_task.cancel()

        try:
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

            if streaming_used:
                stream_watchdog_task = _start_stream_watchdog(
                    timeout_sec=self.stream_consumption_close_timeout_sec,
                    is_stream_consumed=lambda: stream_consumed,
                    close_runner_once=close_runner_once,
                )
                async for _ in self._handle_streaming_response(
                    runner=runner,
                    event=event,
                    custom_error_message=custom_error_message,
                    close_runner_once=close_runner_once,
                    mark_stream_consumed=mark_stream_consumed,
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
            if (
                stream_watchdog_task
                and not stream_watchdog_task.done()
                and (stream_consumed or runner_closed)
            ):
                stream_watchdog_task.cancel()
            if not streaming_used:
                await close_runner_once()

        asyncio.create_task(
            Metric.upload(
                llm_tick=1,
                model_name=self.runner_type,
                provider_type=self.runner_type,
            ),
        )
