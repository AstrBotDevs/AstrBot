"""本地 Agent 模式的 LLM 执行器"""

import asyncio
import base64
from collections.abc import AsyncGenerator
from dataclasses import replace

from astrbot.core import logger
from astrbot.core.agent.message import Message
from astrbot.core.agent.response import AgentStats
from astrbot.core.astr_agent_run_util import run_agent, run_live_agent
from astrbot.core.astr_main_agent import (
    MainAgentBuildConfig,
    MainAgentBuildResult,
    build_main_agent,
)
from astrbot.core.message.components import File, Image
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.pipeline.context import PipelineContext, call_event_hook
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import LLMResponse, ProviderRequest
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.session_lock import session_lock_manager


class InternalAgentExecutor:
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        conf = ctx.astrbot_config
        settings = conf["provider_settings"]
        self.streaming_response: bool = settings["streaming_response"]
        self.unsupported_streaming_strategy: str = settings[
            "unsupported_streaming_strategy"
        ]
        self.max_step: int = settings.get("max_agent_step", 30)
        self.tool_call_timeout: int = settings.get("tool_call_timeout", 60)
        self.tool_schema_mode: str = settings.get("tool_schema_mode", "full")
        if self.tool_schema_mode not in ("skills_like", "full"):
            logger.warning(
                "Unsupported tool_schema_mode: %s, fallback to skills_like",
                self.tool_schema_mode,
            )
            self.tool_schema_mode = "full"
        if isinstance(self.max_step, bool):  # workaround: #2622
            self.max_step = 30
        self.show_tool_use: bool = settings.get("show_tool_use_status", True)
        self.show_reasoning = settings.get("display_reasoning_text", False)
        self.sanitize_context_by_modalities: bool = settings.get(
            "sanitize_context_by_modalities",
            False,
        )
        self.kb_agentic_mode: bool = conf.get("kb_agentic_mode", False)

        self.context_limit_reached_strategy: str = settings.get(
            "context_limit_reached_strategy", "truncate_by_turns"
        )
        self.llm_compress_instruction: str = settings.get(
            "llm_compress_instruction", ""
        )
        self.llm_compress_keep_recent: int = settings.get("llm_compress_keep_recent", 4)
        self.llm_compress_provider_id: str = settings.get(
            "llm_compress_provider_id", ""
        )
        self.max_context_length = settings["max_context_length"]
        self.dequeue_context_length: int = min(
            max(1, settings["dequeue_context_length"]),
            self.max_context_length - 1,
        )
        if self.dequeue_context_length <= 0:
            self.dequeue_context_length = 1

        self.llm_safety_mode = settings.get("llm_safety_mode", True)
        self.safety_mode_strategy = settings.get(
            "safety_mode_strategy", "system_prompt"
        )

        self.computer_use_runtime = settings.get("computer_use_runtime", "local")
        self.sandbox_cfg = settings.get("sandbox", {})

        proactive_cfg = settings.get("proactive_capability", {})
        self.add_cron_tools = proactive_cfg.get("add_cron_tools", True)

        self.conv_manager = ctx.plugin_manager.context.conversation_manager

        self.main_agent_cfg = MainAgentBuildConfig(
            tool_call_timeout=self.tool_call_timeout,
            tool_schema_mode=self.tool_schema_mode,
            sanitize_context_by_modalities=self.sanitize_context_by_modalities,
            kb_agentic_mode=self.kb_agentic_mode,
            context_limit_reached_strategy=self.context_limit_reached_strategy,
            llm_compress_instruction=self.llm_compress_instruction,
            llm_compress_keep_recent=self.llm_compress_keep_recent,
            llm_compress_provider_id=self.llm_compress_provider_id,
            max_context_length=self.max_context_length,
            dequeue_context_length=self.dequeue_context_length,
            llm_safety_mode=self.llm_safety_mode,
            safety_mode_strategy=self.safety_mode_strategy,
            computer_use_runtime=self.computer_use_runtime,
            sandbox_cfg=self.sandbox_cfg,
            add_cron_tools=self.add_cron_tools,
            provider_settings=settings,
            subagent_orchestrator=conf.get("subagent_orchestrator", {}),
            timezone=self.ctx.plugin_manager.context.get_config().get("timezone"),
        )

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None, None]:
        try:
            streaming_response = self.streaming_response
            if (enable_streaming := event.get_extra("enable_streaming")) is not None:
                streaming_response = bool(enable_streaming)

            has_provider_request = event.get_extra("provider_request") is not None
            has_valid_message = bool(event.message_str and event.message_str.strip())
            has_media_content = any(
                isinstance(comp, Image | File) for comp in event.message_obj.message
            )

            if (
                not has_provider_request
                and not has_valid_message
                and not has_media_content
            ):
                logger.debug("skip llm request: empty message and no provider_request")
                return

            logger.debug("ready to request llm provider")

            await call_event_hook(event, EventType.OnWaitingLLMRequestEvent)

            async with session_lock_manager.acquire_lock(event.unified_msg_origin):
                logger.debug("acquired session lock for llm request")

                build_cfg = replace(
                    self.main_agent_cfg,
                    provider_wake_prefix=provider_wake_prefix,
                    streaming_response=streaming_response,
                )

                build_result: MainAgentBuildResult | None = await build_main_agent(
                    event=event,
                    plugin_context=self.ctx.plugin_manager.context,
                    config=build_cfg,
                )

                if build_result is None:
                    return

                agent_runner = build_result.agent_runner
                req = build_result.provider_request
                provider = build_result.provider

                api_base = provider.provider_config.get("api_base", "")
                for host in decoded_blocked:
                    if host in api_base:
                        logger.error(
                            "Provider API base %s is blocked due to security reasons. "
                            "Please use another ai provider.",
                            api_base,
                        )
                        return

                stream_to_general = (
                    self.unsupported_streaming_strategy == "turn_off"
                    and not event.platform_meta.support_streaming_message
                )

                if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
                    return

                action_type = event.get_extra("action_type")

                event.trace.record(
                    "astr_agent_prepare",
                    system_prompt=req.system_prompt,
                    tools=req.func_tool.names() if req.func_tool else [],
                    stream=streaming_response,
                    chat_provider={
                        "id": provider.provider_config.get("id", ""),
                        "model": provider.get_model(),
                    },
                )

                if action_type == "live":
                    logger.info("[Internal Agent] 检测到 Live Mode，启用 TTS 处理")

                    tts_provider = (
                        self.ctx.plugin_manager.context.get_using_tts_provider(
                            event.unified_msg_origin
                        )
                    )

                    if not tts_provider:
                        logger.warning(
                            "[Live Mode] TTS Provider not configured, fallback to "
                            "normal streaming."
                        )

                    async def wrapped_stream():
                        async for chunk in run_live_agent(
                            agent_runner,
                            tts_provider,
                            self.max_step,
                            self.show_tool_use,
                            show_reasoning=self.show_reasoning,
                        ):
                            yield chunk

                        final_resp = agent_runner.get_final_llm_resp()
                        event.trace.record(
                            "astr_agent_complete",
                            stats=agent_runner.stats.to_dict(),
                            resp=final_resp.completion_text if final_resp else None,
                        )

                        if not event.is_stopped() and agent_runner.done():
                            await self._save_to_history(
                                event,
                                req,
                                final_resp,
                                agent_runner.run_context.messages,
                                agent_runner.stats,
                            )

                        asyncio.create_task(
                            Metric.upload(
                                llm_tick=1,
                                model_name=agent_runner.provider.get_model(),
                                provider_type=agent_runner.provider.meta().type,
                            ),
                        )

                    event.set_result(
                        MessageEventResult()
                        .set_result_content_type(ResultContentType.STREAMING_RESULT)
                        .set_async_stream(wrapped_stream()),
                    )
                    yield
                    return

                elif streaming_response and not stream_to_general:

                    async def wrapped_stream():
                        async for chunk in run_agent(
                            agent_runner,
                            self.max_step,
                            self.show_tool_use,
                            show_reasoning=self.show_reasoning,
                        ):
                            yield chunk

                        final_resp = agent_runner.get_final_llm_resp()
                        event.trace.record(
                            "astr_agent_complete",
                            stats=agent_runner.stats.to_dict(),
                            resp=final_resp.completion_text if final_resp else None,
                        )

                        if not event.is_stopped() and agent_runner.done():
                            await self._save_to_history(
                                event,
                                req,
                                final_resp,
                                agent_runner.run_context.messages,
                                agent_runner.stats,
                            )

                        asyncio.create_task(
                            Metric.upload(
                                llm_tick=1,
                                model_name=agent_runner.provider.get_model(),
                                provider_type=agent_runner.provider.meta().type,
                            ),
                        )

                    event.set_result(
                        MessageEventResult()
                        .set_result_content_type(ResultContentType.STREAMING_RESULT)
                        .set_async_stream(wrapped_stream()),
                    )
                    yield
                    return

                else:
                    async for _ in run_agent(
                        agent_runner,
                        self.max_step,
                        self.show_tool_use,
                        stream_to_general,
                        show_reasoning=self.show_reasoning,
                    ):
                        yield

                final_resp = agent_runner.get_final_llm_resp()

                event.trace.record(
                    "astr_agent_complete",
                    stats=agent_runner.stats.to_dict(),
                    resp=final_resp.completion_text if final_resp else None,
                )

                if not event.is_stopped():
                    await self._save_to_history(
                        event,
                        req,
                        final_resp,
                        agent_runner.run_context.messages,
                        agent_runner.stats,
                    )

            asyncio.create_task(
                Metric.upload(
                    llm_tick=1,
                    model_name=agent_runner.provider.get_model(),
                    provider_type=agent_runner.provider.meta().type,
                ),
            )

        except Exception as e:
            logger.error(f"Error occurred while processing agent: {e}")
            await event.send(
                MessageChain().message(
                    f"Error occurred while processing agent request: {e}"
                )
            )

    async def _save_to_history(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        llm_response: LLMResponse | None,
        all_messages: list[Message],
        runner_stats: AgentStats | None,
    ):
        if (
            not req
            or not req.conversation
            or not llm_response
            or llm_response.role != "assistant"
        ):
            return

        if not llm_response.completion_text and not req.tool_calls_result:
            logger.debug("LLM response is empty, skipping history save.")
            return

        message_to_save = []
        skipped_initial_system = False
        for message in all_messages:
            if message.role == "system" and not skipped_initial_system:
                skipped_initial_system = True
                continue
            if message.role in ["assistant", "user"] and getattr(
                message, "_no_save", None
            ):
                continue
            message_to_save.append(message.model_dump())

        token_usage = None
        if runner_stats:
            token_usage = runner_stats.token_usage.total

        await self.conv_manager.update_conversation(
            event.unified_msg_origin,
            req.conversation.cid,
            history=message_to_save,
            token_usage=token_usage,
        )


BLOCKED = {"dGZid2h2d3IuY2xvdWQuc2VhbG9zLmlv", "a291cmljaGF0"}
decoded_blocked = [base64.b64decode(b).decode("utf-8") for b in BLOCKED]
