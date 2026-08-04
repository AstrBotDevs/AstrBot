"""本地 Agent 模式的 LLM 调用 Stage"""

from collections.abc import AsyncGenerator
from dataclasses import replace

from astrbot import logger
from astrbot.core.agent.follow_up import FollowUpCapture
from astrbot.core.agent.history_sanitizer import sanitize_history_for_storage
from astrbot.core.agent.llm_types import (
    LLMResponse,
    ProviderRequest,
)
from astrbot.core.agent.message import (
    CheckpointData,
    CheckpointMessageSegment,
    Message,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.response import AgentStats
from astrbot.core.astr_main_agent import (
    LLM_ERROR_MESSAGE_EXTRA_KEY,
    MainAgentBuildConfig,
    MainAgentBuildResult,
    build_main_agent,
)
from astrbot.core.message.components import (
    ComponentType,
    File,
    Image,
    Record,
    Reply,
    Video,
)
from astrbot.core.message.message_event_result import (
    MessageChain,
    MessageEventResult,
    ResultContentType,
)
from astrbot.core.persona_error_reply import (
    get_agent_error_message,
)
from astrbot.core.platform.astr_message_event import AstrMessageEvent
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.task_utils import create_tracked_task

from .....astr_agent_run_util import AgentRunner, run_agent, run_live_agent
from ....context import PipelineContext, call_event_hook


class InternalAgentSubStage:
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
        self.show_tool_call_result: bool = settings.get("show_tool_call_result", False)
        self.buffer_intermediate_messages: bool = settings.get(
            "buffer_intermediate_messages",
            False,
        )
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
            "moonshotai_api_key", ""
        )

        # 上下文管理相关
        self.context_limit_reached_strategy: str = settings.get(
            "context_limit_reached_strategy", "truncate_by_turns"
        )
        self.llm_compress_instruction: str = settings.get(
            "llm_compress_instruction", ""
        )
        self.llm_compress_keep_recent_ratio: float = settings.get(
            "llm_compress_keep_recent_ratio", 0.15
        )
        self.llm_compress_provider_id: str = settings.get(
            "llm_compress_provider_id", ""
        )
        self.max_context_length = settings["max_context_length"]  # int
        configured_dequeue_context_length = max(1, settings["dequeue_context_length"])
        if self.max_context_length == -1:
            self.dequeue_context_length = configured_dequeue_context_length
        else:
            self.dequeue_context_length = min(
                configured_dequeue_context_length,
                self.max_context_length - 1,
            )
        if self.dequeue_context_length <= 0:
            self.dequeue_context_length = 1
        self.fallback_max_context_tokens: int = settings.get(
            "fallback_max_context_tokens", 128000
        )

        self.llm_safety_mode = settings.get("llm_safety_mode", True)
        self.safety_mode_strategy = settings.get(
            "safety_mode_strategy", "system_prompt"
        )

        self.computer_use_runtime = settings.get("computer_use_runtime")
        self.sandbox_cfg = settings.get("sandbox", {})

        # Proactive capability configuration
        proactive_cfg = settings.get("proactive_capability", {})
        self.add_cron_tools = proactive_cfg.get("add_cron_tools", True)

        self.conv_manager = ctx.execution_context.conversation_manager

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
            llm_compress_keep_recent_ratio=self.llm_compress_keep_recent_ratio,
            llm_compress_provider_id=self.llm_compress_provider_id,
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
            timezone=self.ctx.execution_context.get_config().get("timezone"),
            max_quoted_fallback_images=settings.get("max_quoted_fallback_images", 20),
        )

    async def _send_llm_error_message(self, event: AstrMessageEvent) -> None:
        await event.send(MessageChain().message(get_agent_error_message(event)))

    async def _finalize_agent_response(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        agent_runner: AgentRunner,
        *,
        action_type: str | None,
        history_saved: bool,
    ) -> None:
        """Record completion state and persist a completed ordinary response."""
        final_resp = agent_runner.get_final_llm_resp()
        event.trace.record(
            "astr_agent_complete",
            stats=agent_runner.stats.to_dict(),
            resp=final_resp.completion_text if final_resp else None,
        )
        create_tracked_task(
            self.ctx.execution_context.background_tasks,
            _record_internal_agent_stats(
                event,
                req,
                agent_runner,
                final_resp,
                self.ctx.execution_context.database,
            ),
            name="record_internal_agent_stats",
        )
        if (
            action_type != "live"
            and not history_saved
            and (not event.is_stopped() or agent_runner.was_aborted())
        ):
            await self._save_to_history(
                event,
                req,
                final_resp,
                agent_runner.run_context.messages,
                agent_runner.stats,
                user_aborted=agent_runner.was_aborted(),
            )
        create_tracked_task(
            self.ctx.execution_context.background_tasks,
            self.ctx.execution_context.metrics.upload(
                llm_tick=1,
                model_name=agent_runner.provider.get_model(),
                provider_type=agent_runner.provider.meta().type,
            ),
            name="upload_agent_metric",
        )

    async def _build_checked_agent_runner(
        self,
        event: AstrMessageEvent,
        provider_wake_prefix: str,
        streaming_response: bool,
    ) -> MainAgentBuildResult | None:
        """Build a runner and reject configured provider endpoints unsafe for use."""
        build_cfg = replace(
            self.main_agent_cfg,
            provider_wake_prefix=provider_wake_prefix,
            streaming_response=streaming_response,
        )
        build_result = await build_main_agent(
            event=event,
            plugin_context=self.ctx.execution_context,
            config=build_cfg,
            apply_reset=False,
        )
        if build_result is None:
            if event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY):
                await self._send_llm_error_message(event)
            return None

        api_base = build_result.provider.provider_config.get("api_base", "")
        for host in BLOCKED_PROVIDER_HOSTS:
            if host in api_base:
                logger.warning(
                    "Blocked provider API base for safety policy. api_base=%s, blocked_host=%s",
                    safe_error("", api_base),
                    host,
                )
                await self._send_llm_error_message(event)
                return None
        return build_result

    async def process(
        self, event: AstrMessageEvent, provider_wake_prefix: str
    ) -> AsyncGenerator[None]:
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
            has_reply = any(
                isinstance(comp, Reply) for comp in event.message_obj.message
            )
            has_structured_content = any(
                comp.type
                not in {
                    ComponentType.Plain,
                    ComponentType.At,
                }
                for comp in event.message_obj.message
            )

            if (
                not has_provider_request
                and not has_valid_message
                and not has_media_content
                and not has_reply
                and not has_structured_content
            ):
                logger.debug("skip llm request: empty message and no provider_request")
                return

            logger.debug("ready to request llm provider")
            follow_up_capture = (
                self.ctx.execution_context.follow_up_coordinator.try_capture(event)
            )
            if follow_up_capture:
                (
                    follow_up_consumed_marked,
                    follow_up_activated,
                ) = await self.ctx.execution_context.follow_up_coordinator.prepare_capture(
                    follow_up_capture
                )
                if follow_up_consumed_marked:
                    event.set_extra(
                        "_follow_up_captured",
                        {"target_run_id": follow_up_capture.target_run_id},
                    )
                    logger.info(
                        "Follow-up ticket already consumed, stopping processing. umo=%s, seq=%s",
                        event.unified_msg_origin,
                        follow_up_capture.ticket.seq,
                    )
                    return

            try:
                typing_requested = True
                await event.send_typing()
            except Exception as exc:
                logger.warning("send_typing failed: %s", safe_error("", exc))
            if await call_event_hook(
                event,
                EventType.OnWaitingLLMRequestEvent,
                handler_registry=self.ctx.handlers,
                plugin_registry=self.ctx.plugins,
            ):
                return

            async with self.ctx.execution_context.session_lock_manager.acquire_lock(
                event.unified_msg_origin
            ):
                logger.debug("acquired session lock for llm request")
                agent_runner: AgentRunner | None = None
                runner_registered = False
                history_saved = False
                try:
                    build_result = await self._build_checked_agent_runner(
                        event,
                        provider_wake_prefix,
                        streaming_response,
                    )
                    if build_result is None:
                        return

                    agent_runner = build_result.agent_runner
                    req = build_result.provider_request
                    provider = build_result.provider
                    reset_coro = build_result.reset_coro

                    stream_to_general = (
                        self.unsupported_streaming_strategy == "turn_off"
                        and not event.platform_meta.support_streaming_message
                    )

                    if await call_event_hook(
                        event,
                        EventType.OnLLMRequestEvent,
                        req,
                        handler_registry=self.ctx.handlers,
                        plugin_registry=self.ctx.plugins,
                    ):
                        if reset_coro:
                            reset_coro.close()
                        return

                    # apply reset
                    if reset_coro:
                        await reset_coro

                    self.ctx.execution_context.follow_up_coordinator.register_active_runner(
                        event.unified_msg_origin,
                        agent_runner,
                    )
                    runner_registered = True
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

                    # 检测 Live Mode
                    if action_type == "live":
                        # Live Mode: 使用 run_live_agent
                        logger.info("[Internal Agent] 检测到 Live Mode，启用 TTS 处理")

                        # 获取 TTS Provider
                        tts_provider = (
                            self.ctx.execution_context.get_using_tts_provider(
                                event.unified_msg_origin
                            )
                        )

                        if not tts_provider:
                            logger.warning(
                                "[Live Mode] TTS Provider 未配置，将使用普通流式模式"
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
                                    buffer_intermediate_messages=self.buffer_intermediate_messages,
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
                            history_saved = True

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
                                    buffer_intermediate_messages=self.buffer_intermediate_messages,
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
                            buffer_intermediate_messages=self.buffer_intermediate_messages,
                        ):
                            yield

                    await self._finalize_agent_response(
                        event,
                        req,
                        agent_runner,
                        action_type=action_type,
                        history_saved=history_saved,
                    )
                finally:
                    if runner_registered and agent_runner is not None:
                        self.ctx.execution_context.follow_up_coordinator.unregister_active_runner(
                            event.unified_msg_origin,
                            agent_runner,
                        )

        except Exception as e:
            logger.error(
                "Error occurred while processing agent: %s",
                safe_error("", e),
            )
            await event.send(MessageChain().message(get_agent_error_message(event)))
        finally:
            if typing_requested:
                try:
                    await event.stop_typing()
                except Exception as exc:
                    logger.warning("stop_typing failed: %s", safe_error("", exc))
            if follow_up_capture:
                await self.ctx.execution_context.follow_up_coordinator.finalize_capture(
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

        checkpoint_id = event.get_extra("llm_checkpoint_id")
        if not user_aborted and (
            llm_response is None or llm_response.role != "assistant"
        ):
            if isinstance(checkpoint_id, str) and checkpoint_id:
                messages_to_save: list[Message] = []
                skipped_initial_system = False
                for message in all_messages:
                    if message.role == "system" and not skipped_initial_system:
                        skipped_initial_system = True
                        continue
                    if message.role in ["assistant", "user"] and message._no_save:
                        continue
                    messages_to_save.append(message)
                message_to_save = dump_messages_with_checkpoints(messages_to_save)
                message_to_save.append(
                    CheckpointMessageSegment(
                        content=CheckpointData(id=checkpoint_id),
                    ).model_dump()
                )
                await self.conv_manager.update_conversation(
                    event.unified_msg_origin,
                    req.conversation.cid,
                    history=sanitize_history_for_storage(message_to_save),
                    token_usage=None,
                )
                return
            if not req.tool_calls_result:
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

        message_to_save = dump_messages_with_checkpoints(messages_to_save)
        if isinstance(checkpoint_id, str) and checkpoint_id:
            message_to_save.append(
                CheckpointMessageSegment(
                    content=CheckpointData(id=checkpoint_id),
                ).model_dump()
            )

        message_to_save = sanitize_history_for_storage(message_to_save)

        # if user_aborted:
        #     message_to_save.append(
        #         Message(
        #             role="assistant",
        #             content="[User aborted this request. Partial output before abort was preserved.]",
        #         ).model_dump()
        #     )

        # ConversationManager aggregates usage while requests run.  A checkpoint
        # is a partial snapshot and must not overwrite the persisted aggregate.
        token_usage = (
            None
            if isinstance(checkpoint_id, str) and checkpoint_id
            else getattr(req.conversation, "token_usage", None)
        )

        await self.conv_manager.update_conversation(
            event.unified_msg_origin,
            req.conversation.cid,
            history=message_to_save,
            token_usage=token_usage,
        )
        if llm_response.completion_text:
            self._schedule_runtime_memory_postprocess(
                event,
                req,
                llm_response.completion_text,
            )

    def _schedule_runtime_memory_postprocess(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        assistant_text: str,
    ) -> None:
        execution_context = getattr(self.ctx, "execution_context", None)
        if execution_context is None:
            return

        persona_runtime_manager = getattr(
            execution_context,
            "persona_runtime_manager",
            None,
        )
        memory_manager = getattr(execution_context, "memory_manager", None)
        if persona_runtime_manager is None and memory_manager is None:
            return

        try:
            create_tracked_task(
                self.ctx.execution_context.background_tasks,
                _run_runtime_memory_postprocess(
                    event=event,
                    req=req,
                    assistant_text=assistant_text,
                    persona_runtime_manager=persona_runtime_manager,
                    memory_manager=memory_manager,
                ),
                name="runtime_memory_postprocess",
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Failed to schedule runtime/memory postprocess: %s",
                safe_error("", exc),
            )


# We prevent AstrBot from connecting to known malicious hosts.
# Keep this list transparent so operators can audit why an API base is blocked.
BLOCKED_PROVIDER_HOSTS = frozenset(
    {
        "tfbwhvwr.cloud.sealos.io",
        "kourichat",
    }
)


async def _record_internal_agent_stats(
    event: AstrMessageEvent,
    req: ProviderRequest | None,
    agent_runner: AgentRunner | None,
    final_resp: LLMResponse | None,
    db,
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

        await db.insert_provider_stat(
            umo=event.unified_msg_origin,
            conversation_id=conversation_id,
            provider_id=provider_config.get("id", "") or provider.meta().id,
            provider_model=provider.get_model(),
            status=status,
            stats=stats.to_dict(),
            agent_type="internal",
        )
    except Exception as e:
        logger.warning("Persist provider stats failed: %s", safe_error("", e))


async def _run_runtime_memory_postprocess(
    *,
    event: AstrMessageEvent,
    req: ProviderRequest,
    assistant_text: str,
    persona_runtime_manager,
    memory_manager,
) -> None:
    conversation_id = req.conversation.cid if req.conversation else None
    if persona_runtime_manager is not None:
        persona_id = event.get_extra("selected_persona_id")
        if isinstance(persona_id, str) and persona_id and persona_id != "[%None]":
            try:
                await persona_runtime_manager.process_turn(
                    event=event,
                    persona_id=persona_id,
                    conversation_id=conversation_id,
                    assistant_text=assistant_text,
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Persona runtime postprocess failed for umo=%s: %s",
                    event.unified_msg_origin,
                    safe_error("", exc),
                )

    if memory_manager is not None:
        try:
            await memory_manager.enqueue_turn(
                event=event,
                conversation_id=conversation_id,
                assistant_text=assistant_text,
            )
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "Memory writeback enqueue failed for umo=%s: %s",
                event.unified_msg_origin,
                safe_error("", exc),
            )
