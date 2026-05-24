"""本地 Agent 模式的 LLM 调用 Stage"""

import asyncio
import base64
from collections.abc import AsyncGenerator
from dataclasses import replace

from astrbot.core import db_helper, logger
from astrbot.core.agent.mcp_elicitation_registry import (
    try_capture_pending_mcp_elicitation,
)
from astrbot.core.agent.message import (
    CheckpointData,
    CheckpointMessageSegment,
    Message,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.response import AgentStats
from astrbot.core.astr_agent_run_util import (
    DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD,
    AgentRunner,
    normalize_config_repeat_reply_guard_threshold,
    run_agent,
    run_live_agent,
)
from astrbot.core.astr_main_agent import (
    LLM_ERROR_MESSAGE_EXTRA_KEY,
    MainAgentBuildConfig,
    MainAgentBuildResult,
    build_main_agent,
    pre_caption_images,
)
from astrbot.core.message.components import File, Image, Record, Video
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    extract_persona_custom_error_message_from_event,
)
from astrbot.core.pipeline.context import PipelineContext, call_event_hook
from astrbot.core.pipeline.process_stage.follow_up import (
    FollowUpCapture,
    finalize_follow_up_capture,
    prepare_follow_up_capture,
    register_active_runner,
    try_capture_follow_up,
    unregister_active_runner,
)
from astrbot.core.pipeline.stage import Stage
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.provider.entities import (
    LLMResponse,
    ProviderRequest,
)
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.config_normalization import to_non_negative_int, to_ratio
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.session_lock import session_lock_manager
from astrbot.core.utils.trace import _current_span


def _count_conversation_turns(messages: list[Message]) -> int:
    """Count persisted conversation turns by user messages.

    A turn starts with a user message and may include assistant tool calls,
    tool results, and the final assistant answer. Counting user messages avoids
    treating tool call/result pairs as additional conversation turns.
    """
    return sum(1 for message in messages if message.role == "user")


def _history_exceeds_turn_limit(messages: list[Message], max_turns: int) -> bool:
    """Return whether persisted history exceeds the configured turn limit."""
    if max_turns == -1:
        return False
    if max_turns <= 0:
        return False
    return _count_conversation_turns(messages) > max_turns


def _has_valid_summary_message(messages: list[Message]) -> bool:
    """Return whether LLM compression produced a non-empty summary block."""
    summary_prefix = "Our previous history conversation summary:"
    for message in messages:
        if message.role != "user" or not isinstance(message.content, str):
            continue
        if not message.content.startswith(summary_prefix):
            continue
        summary_text = message.content.removeprefix(summary_prefix).strip()
        return bool(summary_text)
    return False


class InternalAgentSubStage(Stage):
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
        self.tool_call_approval: dict = settings.get("tool_call_approval", {})
        self.tool_schema_mode: str = settings.get("tool_schema_mode", "full")
        if self.tool_schema_mode not in ("skills_like", "full", "tool_search", "auto"):
            logger.warning(
                "Unsupported tool_schema_mode: %s, fallback to full",
                self.tool_schema_mode,
            )
            self.tool_schema_mode = "full"
        if isinstance(self.max_step, bool):  # workaround: #2622
            self.max_step = 30
        self.repeat_reply_guard_threshold: int = settings.get(
            "repeat_reply_guard_threshold",
            DEFAULT_REPEAT_REPLY_GUARD_THRESHOLD,
        )
        self.repeat_reply_guard_threshold = (
            normalize_config_repeat_reply_guard_threshold(
                self.repeat_reply_guard_threshold
            )
        )
        self.show_tool_use: bool = settings.get("show_tool_use_status", True)
        self.show_tool_call_result: bool = settings.get("show_tool_call_result", False)
        self.buffer_intermediate_messages: bool = settings.get(
            "buffer_intermediate_messages",
            False,
        )
        self.provider_wake_prefix: str = settings.get("wake_prefix", "")
        self.show_reasoning = settings.get("display_reasoning_text", False)
        self.sanitize_context_by_modalities: bool = settings.get(
            "sanitize_context_by_modalities",
            False,
        )
        self.kb_agentic_mode: bool = conf.get("kb_agentic_mode", False)

        file_extract_conf: dict = settings.get("file_extract", {})
        self.file_extract_enabled: bool = file_extract_conf.get("enable", False)
        self.file_extract_prov: str = file_extract_conf.get("provider", "moonshotai")
        self.file_extract_msh_api_key: str = file_extract_conf.get(
            "moonshotai_api_key",
            "",
        )

        # 上下文管理相关
        self.context_limit_reached_strategy: str = settings.get(
            "context_limit_reached_strategy",
            "truncate_by_turns",
        )
        self.llm_compress_instruction: str = settings.get(
            "llm_compress_instruction",
            "",
        )
        self.llm_compress_keep_recent: int = settings.get("llm_compress_keep_recent", 4)
        self.llm_compress_provider_id: str = settings.get(
            "llm_compress_provider_id",
            "",
        )
        self.llm_compress_use_compact_api: bool = settings.get(
            "llm_compress_use_compact_api", True
        )
        self.context_token_counter_mode: str = str(
            settings.get("context_token_counter_mode", "estimate")
        )
        self.compact_context_after_tool_call: bool = settings.get(
            "compact_context_after_tool_call",
            False,
        )
        self.compact_context_soft_ratio: float = to_ratio(
            settings.get("compact_context_soft_ratio", 0.3),
            0.3,
        )
        self.compact_context_hard_ratio: float = to_ratio(
            settings.get("compact_context_hard_ratio", 0.7),
            0.7,
        )
        self.compact_context_min_delta_tokens: int = to_non_negative_int(
            settings.get("compact_context_min_delta_tokens", 0),
            0,
        )
        self.compact_context_min_delta_turns: int = to_non_negative_int(
            settings.get("compact_context_min_delta_turns", 0),
            0,
        )
        self.compact_context_debounce_seconds: int = to_non_negative_int(
            settings.get("compact_context_debounce_seconds", 0),
            0,
        )
        self.max_context_length = settings["max_context_length"]  # int
        self.dequeue_context_length: int = min(
            max(1, settings["dequeue_context_length"]),
            self.max_context_length - 1,
        )
        if self.dequeue_context_length <= 0:
            self.dequeue_context_length = 1
        self.fallback_max_context_tokens: int = settings.get(
            "fallback_max_context_tokens",
            128000,
        )

        self.llm_safety_mode = settings.get("llm_safety_mode", True)
        self.safety_mode_strategy = settings.get(
            "safety_mode_strategy",
            "system_prompt",
        )

        self.computer_use_runtime = settings.get("computer_use_runtime")
        self.sandbox_cfg = settings.get("sandbox", {})

        # Proactive capability configuration
        proactive_cfg = settings.get("proactive_capability", {})
        self.add_cron_tools = proactive_cfg.get("add_cron_tools", True)

        self.conv_manager = ctx.plugin_manager.context.conversation_manager

        self.main_agent_cfg = MainAgentBuildConfig(
            tool_call_timeout=self.tool_call_timeout,
            tool_schema_mode=self.tool_schema_mode,
            sanitize_context_by_modalities=self.sanitize_context_by_modalities,
            kb_agentic_mode=self.kb_agentic_mode,
            file_extract_enabled=self.file_extract_enabled,
            file_extract_prov=self.file_extract_prov,
            file_extract_msh_api_key=self.file_extract_msh_api_key,
            context_limit_reached_strategy=self.context_limit_reached_strategy,
            llm_compress_instruction=self.llm_compress_instruction,
            llm_compress_keep_recent=self.llm_compress_keep_recent,
            llm_compress_provider_id=self.llm_compress_provider_id,
            context_token_counter_mode=self.context_token_counter_mode,
            compact_context_after_tool_call=self.compact_context_after_tool_call,
            compact_context_soft_ratio=self.compact_context_soft_ratio,
            compact_context_hard_ratio=self.compact_context_hard_ratio,
            compact_context_min_delta_tokens=self.compact_context_min_delta_tokens,
            compact_context_min_delta_turns=self.compact_context_min_delta_turns,
            compact_context_debounce_seconds=self.compact_context_debounce_seconds,
            max_context_length=self.max_context_length,
            dequeue_context_length=self.dequeue_context_length,
            fallback_max_context_tokens=self.fallback_max_context_tokens,
            llm_safety_mode=self.llm_safety_mode,
            safety_mode_strategy=self.safety_mode_strategy,
            computer_use_runtime=self.computer_use_runtime,
            sandbox_cfg=self.sandbox_cfg,
            add_cron_tools=self.add_cron_tools,
            provider_settings=settings,
            subagent_orchestrator=conf.get("subagent_orchestrator", {}),
            timezone=self.ctx.plugin_manager.context.get_config().get("timezone"),
            max_quoted_fallback_images=settings.get("max_quoted_fallback_images", 20),
            tool_call_approval=self.tool_call_approval,
        )

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None, None]:
        provider_wake_prefix = self.provider_wake_prefix
        follow_up_capture: FollowUpCapture | None = None
        follow_up_consumed_marked = False
        follow_up_activated = False
        typing_requested = False
        try:
            streaming_response = self.streaming_response
            if (enable_streaming := event.get_extra("enable_streaming")) is not None:
                streaming_response = bool(enable_streaming)

            has_provider_request = event.get_extra("provider_request") is not None
            has_valid_message = bool(event.message_str and event.message_str.strip())
            has_media_content = any(
                isinstance(comp, (Image, File, Record, Video))
                for comp in event.message_obj.message
            )

            if (
                not has_provider_request
                and not has_valid_message
                and not has_media_content
            ):
                logger.debug("skip llm request: empty message and no provider_request")
                return

            logger.debug("ready to request llm provider")
            if try_capture_pending_mcp_elicitation(event):
                logger.info(
                    "Captured MCP elicitation reply for active agent run, umo=%s",
                    event.unified_msg_origin,
                )
                return
            follow_up_capture = try_capture_follow_up(event)
            if follow_up_capture:
                (
                    follow_up_consumed_marked,
                    follow_up_activated,
                ) = await prepare_follow_up_capture(follow_up_capture)
                if follow_up_consumed_marked:
                    logger.info(
                        "Follow-up ticket already consumed, stopping processing. umo=%s, seq=%s",
                        event.unified_msg_origin,
                        follow_up_capture.ticket.seq,
                    )
                    return

            try:
                typing_requested = True
                await event.send_typing()
            except Exception:
                logger.warning("send_typing failed", exc_info=True)
            await call_event_hook(event, EventType.OnWaitingLLMRequestEvent)

            if not event.get_extra("provider_request"):
                plugin_context = self.ctx.plugin_manager.context
                cfg = plugin_context.get_config(umo=event.unified_msg_origin).get(
                    "provider_settings", {}
                )
                if cfg.get("image_caption_wait_for_context_order", True):
                    await pre_caption_images(event, plugin_context, cfg)
                else:
                    event.set_extra("_skip_img_caption", True)

            async with session_lock_manager.acquire_lock(event.unified_msg_origin):
                logger.debug("acquired session lock for llm request")
                agent_runner: AgentRunner | None = None
                runner_registered = False
                _llm_span_token = None
                try:
                    build_cfg = replace(
                        self.main_agent_cfg,
                        provider_wake_prefix=provider_wake_prefix,
                        streaming_response=streaming_response,
                    )

                    build_result: MainAgentBuildResult | None = await build_main_agent(
                        event=event,
                        plugin_context=self.ctx.plugin_manager.context,
                        config=build_cfg,
                        apply_reset=False,
                    )

                    if build_result is None:
                        if llm_error_message := event.get_extra(
                            LLM_ERROR_MESSAGE_EXTRA_KEY
                        ):
                            await self._send_llm_error_message(
                                event,
                                llm_error_message,
                            )
                        return

                    agent_runner = build_result.agent_runner
                    req = build_result.provider_request
                    provider = build_result.provider
                    reset_coro = build_result.reset_coro

                    api_base = provider.provider_config.get("api_base", "")
                    for host in decoded_blocked:
                        if host in api_base:
                            error_message = (
                                f"LLM 请求失败：Provider API base `{api_base}` "
                                "因安全原因被拦截，请更换可用的 AI 提供商。"
                            )
                            logger.error(error_message)
                            await self._send_llm_error_message(event, error_message)
                            return

                    stream_to_general = (
                        self.unsupported_streaming_strategy == "turn_off"
                        and not event.platform_meta.support_streaming_message
                    )

                    system_prompt_before_hooks = req.system_prompt or ""
                    if await call_event_hook(event, EventType.OnLLMRequestEvent, req):
                        if reset_coro:
                            reset_coro.close()
                        return
                    system_prompt_after_hooks = req.system_prompt or ""
                    if system_prompt_after_hooks != system_prompt_before_hooks:
                        logger.warning(
                            "LLM system prompt was modified by request hooks. umo=%s, before_chars=%s, after_chars=%s",
                            event.unified_msg_origin,
                            len(system_prompt_before_hooks),
                            len(system_prompt_after_hooks),
                        )

                    # apply reset
                    if reset_coro:
                        await reset_coro

                    register_active_runner(event.unified_msg_origin, agent_runner)
                    runner_registered = True
                    action_type = event.get_extra("action_type")

                    _llm_parent = _current_span.get() or event.trace
                    llm_agent_span = _llm_parent.child(
                        "LLMAgent", span_type="llm_agent"
                    )
                    _sys_prompt = req.system_prompt or ""
                    llm_agent_span.set_input(
                        system_prompt=_sys_prompt,
                        system_prompt_chars=len(_sys_prompt),
                        context_length=len(req.contexts) if req.contexts else 0,
                        tools=req.func_tool.names() if req.func_tool else [],
                        stream=streaming_response,
                        provider=provider.provider_config.get("id", ""),
                        model=provider.get_model(),
                    )
                    # Expose span both on the event (legacy) and via ContextVar so
                    # astr_agent_run_util and any downstream code can resolve the
                    # parent without an explicit event reference.
                    event._llm_agent_span = llm_agent_span
                    _llm_span_token = _current_span.set(llm_agent_span)  # noqa: F841

                    # 检测 Live Mode
                    if action_type == "live":
                        # Live Mode: 使用 run_live_agent
                        logger.info("[Internal Agent] 检测到 Live Mode，启用 TTS 处理")

                        # 获取 TTS Provider
                        tts_provider = (
                            self.ctx.plugin_manager.context.get_using_tts_provider(
                                event.unified_msg_origin,
                            )
                        )

                        if not tts_provider:
                            logger.warning(
                                "[Live Mode] TTS Provider 未配置，将使用普通流式模式",
                            )

                        # 使用 run_live_agent，总是使用流式响应
                        event.set_result(
                            MessageEventResult()
                            .set_result_content_type(ResultContentType.STREAMING_RESULT)
                            .set_async_stream(
                                run_live_agent(
                                    agent_runner,
                                    tts_provider,
                                    self.max_step,
                                    self.show_tool_use,
                                    self.show_tool_call_result,
                                    show_reasoning=self.show_reasoning,
                                    repeat_reply_guard_threshold=self.repeat_reply_guard_threshold,
                                ),
                            ),
                        )
                        yield

                        # 保存历史记录
                        if agent_runner.done() and (
                            not event.is_stopped() or agent_runner.was_aborted()
                        ):
                            await self._save_to_history(
                                event,
                                req,
                                agent_runner.get_final_llm_resp(),
                                agent_runner.run_context.messages,
                                agent_runner.stats,
                                user_aborted=agent_runner.was_aborted(),
                            )

                    elif streaming_response and not stream_to_general:
                        # 流式响应
                        event.set_result(
                            MessageEventResult()
                            .set_result_content_type(ResultContentType.STREAMING_RESULT)
                            .set_async_stream(
                                run_agent(
                                    agent_runner,
                                    self.max_step,
                                    self.show_tool_use,
                                    self.show_tool_call_result,
                                    show_reasoning=self.show_reasoning,
                                    repeat_reply_guard_threshold=self.repeat_reply_guard_threshold,
                                ),
                            ),
                        )
                        yield
                        if agent_runner.done():
                            if final_llm_resp := agent_runner.get_final_llm_resp():
                                if final_llm_resp.completion_text:
                                    chain = (
                                        MessageChain()
                                        .message(final_llm_resp.completion_text)
                                        .chain
                                    )
                                elif final_llm_resp.result_chain:
                                    chain = final_llm_resp.result_chain.chain
                                else:
                                    chain = MessageChain().chain
                                event.set_result(
                                    MessageEventResult(
                                        chain=chain,
                                        result_content_type=ResultContentType.STREAMING_FINISH,
                                    ),
                                )
                    else:
                        async for _ in run_agent(
                            agent_runner,
                            self.max_step,
                            self.show_tool_use,
                            self.show_tool_call_result,
                            stream_to_general,
                            show_reasoning=self.show_reasoning,
                            repeat_reply_guard_threshold=self.repeat_reply_guard_threshold,
                        ):
                            yield

                    final_resp = agent_runner.get_final_llm_resp()

                    _output: dict = {
                        "response": final_resp.completion_text if final_resp else None,
                    }
                    if final_resp:
                        if final_resp.reasoning_content:
                            _output["reasoning"] = final_resp.reasoning_content
                        if final_resp.tools_call_args:
                            _output["tool_calls"] = final_resp.tools_call_args
                    llm_agent_span.set_output(**_output)
                    llm_agent_span.set_meta(**agent_runner.stats.to_dict())
                    if llm_agent_span.finished_at is None:
                        llm_agent_span.finish()
                    event.trace.set_output(
                        response=final_resp.completion_text if final_resp else None,
                    )

                    asyncio.create_task(
                        _record_internal_agent_stats(
                            event,
                            req,
                            agent_runner,
                            final_resp,
                        ),
                    )

                    # 检查事件是否被停止，如果被停止则不保存历史记录
                    if not event.is_stopped() or agent_runner.was_aborted():
                        await self._save_to_history(
                            event,
                            req,
                            final_resp,
                            agent_runner.run_context.messages,
                            agent_runner.stats,
                            user_aborted=agent_runner.was_aborted(),
                        )

                    asyncio.create_task(
                        Metric.upload(
                            llm_tick=1,
                            model_name=agent_runner.provider.get_model(),
                            provider_type=agent_runner.provider.meta().type,
                        ),
                    )
                finally:
                    # clean all subagents if enabled
                    if build_cfg.subagent_orchestrator.get("main_enable"):
                        try:
                            from astrbot.core.subagent_manager import (
                                SubAgentManager,
                            )

                            session_id = event.unified_msg_origin
                            if SubAgentManager.is_auto_cleanup_per_turn():
                                SubAgentManager.cleanup_session_turn_end(session_id)
                        except Exception as e:
                            logger.warning(
                                f"[SubAgent] Cleanup on agent done failed: {e}"
                            )

                    if runner_registered and agent_runner is not None:
                        unregister_active_runner(event.unified_msg_origin, agent_runner)
                    # Ensure llm_agent_span is always finished
                    llm_span = getattr(event, "_llm_agent_span", None)
                    if llm_span is not None and llm_span.finished_at is None:
                        llm_span.finish(status="error")
                    # Reset ContextVar to the span that was active before this stage
                    if _llm_span_token is not None:
                        _current_span.reset(_llm_span_token)

        except Exception as e:
            logger.error(f"Error occurred while processing agent: {e}", exc_info=True)
            custom_error_message = extract_persona_custom_error_message_from_event(
                event,
            )
            error_text = custom_error_message or (
                f"Error occurred while processing agent request: {e}"
            )
            await event.send(MessageChain().message(error_text))
        finally:
            if typing_requested:
                try:
                    await event.stop_typing()
                except Exception:
                    logger.warning("stop_typing failed", exc_info=True)
            if follow_up_capture:
                await finalize_follow_up_capture(
                    follow_up_capture,
                    activated=follow_up_activated,
                    consumed_marked=follow_up_consumed_marked,
                )

    async def _save_to_history(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        llm_response: LLMResponse | None,
        all_messages: list[Message],
        runner_stats: AgentStats | None,
        user_aborted: bool = False,
    ) -> None:
        if not req or not req.conversation:
            return

        if not llm_response and not user_aborted:
            return

        if llm_response and llm_response.role != "assistant":
            if not user_aborted:
                return
            llm_response = LLMResponse(
                role="assistant",
                completion_text=llm_response.completion_text or "",
            )
        elif llm_response is None:
            llm_response = LLMResponse(role="assistant", completion_text="")

        if (
            not llm_response.completion_text
            and not req.tool_calls_result
            and not user_aborted
        ):
            logger.debug("LLM 响应为空，不保存记录。")
            return

        messages_to_save: list[Message] = []
        skipped_initial_system = False
        for message in all_messages:
            if message.role == "system" and not skipped_initial_system:
                skipped_initial_system = True
                continue
            if message.role in ["assistant", "user"] and message._no_save:
                continue
            messages_to_save.append(message)

        # Persistent conversation compaction — either turn-based truncation OR
        # LLM summary, mutually exclusive. Only compact persisted history when
        # the configured turn limit is exceeded; request-time token guarding is
        # handled separately by the agent runner.
        if _history_exceeds_turn_limit(messages_to_save, self.max_context_length):
            from astrbot.core.agent.context.truncator import ContextTruncator

            def fallback_truncate() -> list[Message]:
                truncator = ContextTruncator()
                return truncator.truncate_by_turns(
                    messages_to_save,
                    keep_most_recent_turns=self.max_context_length,
                    drop_turns=self.dequeue_context_length,
                )

            compress_provider = None
            if self.context_limit_reached_strategy == "llm_compress":
                from astrbot.api.provider import Provider as ApiProvider

                provider_source = (
                    self.llm_compress_provider_id or "(current chat model)"
                )
                if self.llm_compress_provider_id:
                    raw_provider = self.ctx.plugin_manager.context.get_provider_by_id(
                        self.llm_compress_provider_id
                    )
                else:
                    raw_provider = self.ctx.plugin_manager.context.get_using_provider(
                        umo=event.unified_msg_origin
                    )

                if raw_provider is not None and isinstance(raw_provider, ApiProvider):
                    compress_provider = raw_provider
                    if not self.llm_compress_provider_id:
                        logger.info("llm_compress 使用当前聊天模型进行持久化历史压缩")
                else:
                    logger.warning(
                        "上下文压缩模型 %s 不可用，将回退为按对话轮数截断",
                        provider_source,
                    )

            if compress_provider is not None:
                # LLM summary strategy: compress old turns into a summary.
                from astrbot.core.agent.context.compressor import (
                    LLMSummaryCompressor,
                )

                original_messages = messages_to_save
                compressor = LLMSummaryCompressor(
                    provider=compress_provider,
                    keep_recent=self.llm_compress_keep_recent,
                    instruction_text=self.llm_compress_instruction,
                )
                compressed_messages = await compressor(original_messages)
                if (
                    compressed_messages is original_messages
                    or not _has_valid_summary_message(compressed_messages)
                ):
                    logger.warning(
                        "LLM 上下文压缩未产生有效摘要，将回退为按对话轮数截断"
                    )
                    messages_to_save = fallback_truncate()
                else:
                    messages_to_save = compressed_messages
            else:
                # Fallback: turn-based truncation only.
                messages_to_save = fallback_truncate()

        checkpoint_id = event.get_extra("llm_checkpoint_id")
        message_to_save = dump_messages_with_checkpoints(messages_to_save)
        if isinstance(checkpoint_id, str) and checkpoint_id:
            message_to_save.append(
                CheckpointMessageSegment(
                    content=CheckpointData(id=checkpoint_id),
                ).model_dump(),
            )

        # if user_aborted:
        #     message_to_save.append(
        #         Message(
        #             role="assistant",
        #             content="[User aborted this request. Partial output before abort was preserved.]",
        #         ).model_dump()
        #     )

        token_usage = None
        if runner_stats:
            # token_usage = runner_stats.token_usage.total
            token_usage = llm_response.usage.total if llm_response.usage else None

        await self.conv_manager.update_conversation(
            event.unified_msg_origin,
            req.conversation.cid,
            history=message_to_save,
            token_usage=token_usage,
        )


# we prevent astrbot from connecting to known malicious hosts
# these hosts are base64 encoded
BLOCKED = {"dGZid2h2d3IuY2xvdWQuc2VhbG9zLmlv", "a291cmljaGF0"}
decoded_blocked = [base64.b64decode(b).decode("utf-8") for b in BLOCKED]


async def _record_internal_agent_stats(
    event: AstrMessageEvent,
    req: ProviderRequest | None,
    agent_runner: AgentRunner | None,
    final_resp: LLMResponse | None,
) -> None:
    """Persist internal agent stats without affecting the user response flow."""
    if agent_runner is None:
        return

    provider = agent_runner.provider
    stats = agent_runner.stats
    if provider is None or stats is None:
        return

    try:
        provider_config = getattr(provider, "provider_config", {}) or {}
        conversation_id = (
            req.conversation.cid
            if req is not None and req.conversation is not None
            else None
        )

        if agent_runner.was_aborted():
            status = "aborted"
        elif final_resp is not None and final_resp.role == "err":
            status = "error"
        else:
            status = "completed"

        await db_helper.insert_provider_stat(
            umo=event.unified_msg_origin,
            conversation_id=conversation_id,
            provider_id=provider_config.get("id", "") or provider.meta().id,
            provider_model=provider.get_model(),
            status=status,
            stats=stats.to_dict(),
            agent_type="internal",
        )
    except Exception as e:
        logger.warning("Persist provider stats failed: %s", e, exc_info=True)
