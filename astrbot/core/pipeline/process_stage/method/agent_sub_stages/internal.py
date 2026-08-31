"""本地 Agent 模式的 LLM 调用 Stage"""

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, nullcontext
from copy import deepcopy
from dataclasses import replace

from astrbot import logger
from astrbot.core.agent.follow_up import FollowUpCapture
from astrbot.core.agent.llm_types import (
    LLMResponse,
    ProviderRequest,
)
from astrbot.core.agent.message import (
    Message,
    dump_messages_with_checkpoints,
)
from astrbot.core.agent.response import AgentStats
from astrbot.core.assistant_history import (
    AssistantHistoryCommitter,
    AssistantHistoryFinalized,
    PendingAssistantHistory,
    build_pending_assistant_history,
    make_projection,
)
from astrbot.core.astr_main_agent import (
    LLM_ERROR_MESSAGE_EXTRA_KEY,
    MainAgentBuildResult,
    build_main_agent,
    local_agent_runtime_from_profile,
)
from astrbot.core.conversation_mgr import load_sanitized_history
from astrbot.core.group_sender_concurrency import (
    ConcurrentTurn,
    bind_concurrent_turn,
    is_group_sender_concurrent,
    sender_id_of,
    session_lock_key,
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
from astrbot.core.platform.send_result import DeliveryReceipt
from astrbot.core.star.star_handler import EventType
from astrbot.core.utils.error_redaction import safe_error
from astrbot.core.utils.task_utils import create_tracked_task

from .....astr_agent_run_util import AgentRunner, run_agent
from ....context import PipelineContext, call_event_hook

_FALLBACK_HISTORY_COMMITTER = AssistantHistoryCommitter()
_STOP_HISTORY_USER_TEXT = "Stop output."
_STOP_HISTORY_ASSISTANT_TEXT = "Output stopped."


def _history_merge_fields(
    base_history: object,
    message_to_save: list[dict],
    checkpoint_id: str | None,
) -> tuple[list | None, int | None, int | None]:
    if not isinstance(base_history, list):
        return None, None, None
    unit_start = next(
        (
            index
            for index in range(len(message_to_save) - 1, -1, -1)
            if message_to_save[index].get("role") == "user"
        ),
        None,
    )
    expected_total = len(message_to_save) + 1
    if checkpoint_id:
        expected_total += 1
    return base_history, unit_start, expected_total


class InternalAgentSubStage:
    async def initialize(self, ctx: PipelineContext) -> None:
        self.ctx = ctx
        conf = ctx.astrbot_config
        settings = conf["provider_settings"]
        self.streaming_response: bool = settings["streaming_response"]
        self.unsupported_streaming_strategy: str = settings[
            "unsupported_streaming_strategy"
        ]
        self.show_tool_use: bool = settings.get("show_tool_use_status", True)
        self.show_tool_call_result: bool = settings.get("show_tool_call_result", False)
        self.buffer_intermediate_messages: bool = settings.get(
            "buffer_intermediate_messages",
            False,
        )
        self.show_reasoning = settings.get("display_reasoning_text", False)
        self.conv_manager = ctx.execution_context.conversation_manager
        self.main_agent_cfg, self.max_step = local_agent_runtime_from_profile(
            conf,
            timezone=self.ctx.execution_context.get_config().get("timezone"),
        )
        self.tool_call_timeout = self.main_agent_cfg.tool_call_timeout
        self.tool_schema_mode = self.main_agent_cfg.tool_schema_mode
        self.sanitize_context_by_modalities = (
            self.main_agent_cfg.sanitize_context_by_modalities
        )
        self.kb_agentic_mode = self.main_agent_cfg.kb_agentic_mode
        self.context_limit_reached_strategy = (
            self.main_agent_cfg.context_limit_reached_strategy
        )
        self.llm_compress_instruction = self.main_agent_cfg.llm_compress_instruction
        self.llm_compress_keep_recent_ratio = (
            self.main_agent_cfg.llm_compress_keep_recent_ratio
        )
        self.llm_compress_provider_id = self.main_agent_cfg.llm_compress_provider_id
        self.max_context_length = self.main_agent_cfg.max_context_length
        self.dequeue_context_length = self.main_agent_cfg.dequeue_context_length
        self.fallback_max_context_tokens = (
            self.main_agent_cfg.fallback_max_context_tokens
        )
        self.llm_safety_mode = self.main_agent_cfg.llm_safety_mode
        self.safety_mode_strategy = self.main_agent_cfg.safety_mode_strategy
        self.computer_use_runtime = self.main_agent_cfg.computer_use_runtime
        self.sandbox_cfg = self.main_agent_cfg.sandbox_cfg
        self.add_cron_tools = self.main_agent_cfg.add_cron_tools

    def _prepare_group_sender_concurrency(
        self,
        event: AstrMessageEvent,
        streaming_response: bool,
    ) -> tuple[bool, str, AbstractAsyncContextManager[None], bool]:
        concurrent = is_group_sender_concurrent(event, self._profile_config(event))
        if concurrent:
            streaming_response = False
        lock_key = session_lock_key(
            event.unified_msg_origin,
            sender_id_of(event),
            concurrent=concurrent,
        )
        outbound_gate = getattr(
            self.ctx.execution_context,
            "group_outbound_gate",
            None,
        )
        turn_cm: AbstractAsyncContextManager[None] = nullcontext()
        if concurrent and outbound_gate is not None:
            turn_cm = bind_concurrent_turn(
                ConcurrentTurn(
                    umo=event.unified_msg_origin,
                    event=event,
                    gate=outbound_gate,
                )
            )
            event.set_extra("_group_outbound_turn", True)
            event.set_extra("_group_outbound_gate", outbound_gate)
            event.set_extra("_group_outbound_umo", event.unified_msg_origin)
        return concurrent, lock_key, turn_cm, streaming_response

    def _register_follow_up_runner(
        self,
        event: AstrMessageEvent,
        agent_runner: AgentRunner,
        concurrent: bool,
    ) -> None:
        sender_id = sender_id_of(event) if concurrent else None
        event.set_extra("_follow_up_sender_id", sender_id)
        if sender_id:
            self.ctx.execution_context.follow_up_coordinator.register_active_runner(
                event.unified_msg_origin,
                agent_runner,
                sender_id=sender_id,
            )
            return
        self.ctx.execution_context.follow_up_coordinator.register_active_runner(
            event.unified_msg_origin,
            agent_runner,
        )

    def _unregister_follow_up_runner(
        self,
        event: AstrMessageEvent,
        agent_runner: AgentRunner,
    ) -> None:
        sender_id = event.get_extra("_follow_up_sender_id")
        if sender_id:
            self.ctx.execution_context.follow_up_coordinator.unregister_active_runner(
                event.unified_msg_origin,
                agent_runner,
                sender_id=sender_id,
            )
            return
        self.ctx.execution_context.follow_up_coordinator.unregister_active_runner(
            event.unified_msg_origin,
            agent_runner,
        )

    def _profile_config(self, event: AstrMessageEvent) -> dict:
        getter = getattr(self.ctx.execution_context, "get_config", None)
        if callable(getter):
            try:
                config = getter(umo=event.unified_msg_origin)
            except TypeError:
                config = getter()
            if isinstance(config, dict):
                return config
        config = getattr(self.ctx, "astrbot_config", None)
        return config if isinstance(config, dict) else {}

    async def _send_llm_error_message(self, event: AstrMessageEvent) -> None:
        await event.send(MessageChain().message(get_agent_error_message(event)))

    async def _finalize_agent_response(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        agent_runner: AgentRunner,
        *,
        history_saved: bool,
    ) -> None:
        """Record Agent facts, then finalize accepted assistant history separately."""
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
            agent_runner.done()
            and not history_saved
            and (not event.is_stopped() or agent_runner.was_aborted())
        ):
            pending = await self._capture_pending_history(event, req, agent_runner)
            await self._finalize_pending_history(event, req, pending)
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
        streaming_response: bool,
    ) -> MainAgentBuildResult | None:
        """Build a runner and reject configured provider endpoints unsafe for use."""
        build_cfg = replace(
            self.main_agent_cfg,
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

    async def process(self, event: AstrMessageEvent) -> AsyncGenerator[None]:
        follow_up_capture: FollowUpCapture | None = None
        follow_up_consumed_marked = False
        follow_up_activated = False
        typing_requested = False
        try:
            from astrbot.core.streaming_override import resolve_streaming_response

            streaming_response = await resolve_streaming_response(
                event,
                getattr(self.ctx, "astrbot_config", None),
                getattr(self.ctx, "preferences", None),
                default=self.streaming_response,
            )

            provider_manager = getattr(
                self.ctx.execution_context, "provider_manager", None
            )
            mcp_interactions = getattr(
                getattr(provider_manager, "tool_manager", None),
                "mcp_interaction_coordinator",
                None,
            )
            if (
                mcp_interactions is not None
                and await mcp_interactions.respond_from_event(event)
            ):
                event.set_extra("_mcp_input_response", True)
                return

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

            concurrent, lock_key, turn_cm, streaming_response = (
                self._prepare_group_sender_concurrency(event, streaming_response)
            )

            async with (
                turn_cm,
                self.ctx.execution_context.session_lock_manager.acquire_lock(lock_key),
            ):
                logger.debug("acquired session lock for llm request")
                agent_runner: AgentRunner | None = None
                runner_registered = False
                runner_stop_callback = None
                history_saved = False
                try:
                    build_result = await self._build_checked_agent_runner(
                        event,
                        streaming_response,
                    )
                    if build_result is None:
                        return

                    agent_runner = build_result.agent_runner
                    req = build_result.provider_request
                    history_committer = getattr(
                        self.ctx.execution_context,
                        "assistant_history_committer",
                        _FALLBACK_HISTORY_COMMITTER,
                    )
                    event.set_extra(
                        "_assistant_history_sequence",
                        history_committer.next_sequence(),
                    )
                    provider = build_result.provider
                    reset_coro = build_result.reset_coro
                    if concurrent and req.conversation is not None:
                        event.set_extra(
                            "_history_merge_base",
                            deepcopy(load_sanitized_history(req.conversation.history)),
                        )

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

                    candidate_stop_callback = getattr(
                        agent_runner,
                        "request_stop",
                        None,
                    )
                    if callable(candidate_stop_callback):
                        runner_stop_callback = candidate_stop_callback
                        registry = getattr(
                            self.ctx.execution_context,
                            "active_event_registry",
                            None,
                        )
                        if registry is not None:
                            registry.register_agent_stop_callback(
                                event,
                                runner_stop_callback,
                            )
                        else:
                            runner_stop_callback = None
                    self._register_follow_up_runner(event, agent_runner, concurrent)
                    runner_registered = True
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

                    if streaming_response and not stream_to_general:
                        # 流式响应
                        event.set_result(
                            MessageEventResult()
                            .set_result_content_type(ResultContentType.STREAMING_RESULT)
                            .set_async_stream(
                                self._stream_with_pending_history(
                                    event,
                                    req,
                                    agent_runner,
                                    run_agent(
                                        agent_runner,
                                        self.max_step,
                                        self.show_tool_use,
                                        self.show_tool_call_result,
                                        show_reasoning=self.show_reasoning,
                                        buffer_intermediate_messages=self.buffer_intermediate_messages,
                                    ),
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
                        history_saved=history_saved,
                    )
                finally:
                    if runner_registered and agent_runner is not None:
                        self._unregister_follow_up_runner(event, agent_runner)
                    if runner_stop_callback is not None:
                        self.ctx.execution_context.active_event_registry.unregister_agent_stop_callback(
                            event,
                            runner_stop_callback,
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
    ) -> PendingAssistantHistory | None:
        """Freeze an Agent result for later history projection.

        This compatibility-named private method intentionally no longer writes
        conversation storage. It only freezes the completed Agent state; a
        later platform receipt authorizes a user-visible assistant projection.
        """
        if not req or not req.conversation:
            return None

        checkpoint_id = event.get_extra("llm_checkpoint_id")
        checkpoint_id = checkpoint_id if isinstance(checkpoint_id, str) else None
        if not user_aborted and (
            llm_response is None or llm_response.role != "assistant"
        ):
            return None

        if llm_response and llm_response.role != "assistant":
            if not user_aborted:
                return
            llm_response = LLMResponse(
                role="assistant",
                completion_text=llm_response.completion_text or "",
            )
        elif llm_response is None:
            llm_response = LLMResponse(role="assistant", completion_text="")

        if user_aborted:
            llm_response = LLMResponse(
                role="assistant",
                completion_text=_STOP_HISTORY_ASSISTANT_TEXT,
            )

        if not llm_response.completion_text:
            logger.debug("LLM 响应为空，不保存记录。")
            return None

        messages_to_save: list[Message] = []
        skipped_initial_system = False
        for message in all_messages:
            if message.role == "system" and not skipped_initial_system:
                skipped_initial_system = True
                continue
            if message.role in ["assistant", "user"] and message._no_save:
                continue
            messages_to_save.append(message)

        if user_aborted:
            # A stop is one synthetic turn.  Streaming deltas and partial tool
            # work have already reached transient clients, but must never be
            # replayed as durable conversation history.
            last_user_index = max(
                (
                    index
                    for index, message in enumerate(messages_to_save)
                    if message.role == "user"
                ),
                default=0,
            )
            messages_to_save = messages_to_save[:last_user_index]
            messages_to_save.extend(
                [
                    Message(
                        role="user",
                        content=_STOP_HISTORY_USER_TEXT,
                    ),
                    Message(
                        role="assistant",
                        content=_STOP_HISTORY_ASSISTANT_TEXT,
                    ),
                ]
            )

        message_to_save = dump_messages_with_checkpoints(messages_to_save)
        # Replace only the terminal semantic assistant response later, after
        # the platform accepts the locally submitted normalized message chain.
        for index in range(len(message_to_save) - 1, -1, -1):
            message = message_to_save[index]
            if message.get("role") != "assistant":
                continue
            if "tool_calls" not in message:
                message_to_save.pop(index)
                break

        # ConversationManager aggregates usage while requests run.  A checkpoint
        # is a partial snapshot and must not overwrite the persisted aggregate.
        token_usage = (
            None if checkpoint_id else getattr(req.conversation, "token_usage", None)
        )
        run_id = event.get_extra("run_id")
        if run_id is None:
            run_id = getattr(getattr(event, "message_obj", None), "message_id", None)
        base_history, unit_start, expected_total = _history_merge_fields(
            event.get_extra("_history_merge_base"),
            message_to_save,
            checkpoint_id,
        )
        return build_pending_assistant_history(
            unified_msg_origin=event.unified_msg_origin,
            conversation_id=req.conversation.cid,
            history_snapshot=message_to_save,
            token_usage=token_usage,
            assistant_semantic_output=llm_response.completion_text,
            checkpoint_id=checkpoint_id,
            run_id=str(run_id) if run_id is not None else None,
            sequence=event.get_extra("_assistant_history_sequence") or 0,
            runtime_metadata={
                "user_aborted": user_aborted,
                "token_usage": getattr(runner_stats, "token_usage", None),
            },
            base_history=base_history,
            unit_start=unit_start,
            expected_total=expected_total,
        )

    async def _capture_pending_history(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        agent_runner: AgentRunner,
    ) -> PendingAssistantHistory | None:
        """Freeze one terminal Agent snapshot before receipt finalization."""
        captured = event.get_extra("_pending_assistant_history")
        if isinstance(captured, PendingAssistantHistory):
            return captured
        if event.get_extra("_pending_assistant_history_captured"):
            return None

        event.set_extra("_pending_assistant_history_captured", True)
        pending = await self._save_to_history(
            event,
            req,
            agent_runner.get_final_llm_resp(),
            agent_runner.run_context.messages,
            agent_runner.stats,
            user_aborted=agent_runner.was_aborted(),
        )
        event.set_extra("_pending_assistant_history", pending)
        return pending

    async def _stream_with_pending_history(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        agent_runner: AgentRunner,
        stream: AsyncGenerator[MessageChain | None],
    ) -> AsyncGenerator[MessageChain | None]:
        """Freeze streaming history after Agent completion, before send returns."""
        try:
            async for chain in stream:
                yield chain
            if agent_runner.done():
                await self._capture_pending_history(event, req, agent_runner)
        finally:
            await stream.aclose()

    async def _finalize_pending_history(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
        pending: PendingAssistantHistory | None,
    ) -> None:
        """Commit a pending assistant turn only after a platform acceptance receipt."""
        if not isinstance(pending, PendingAssistantHistory):
            pending = None
        receipt = event.get_extra("delivery_receipt")
        if not isinstance(receipt, DeliveryReceipt):
            get_platform_id = getattr(event, "get_platform_id", None)
            platform_id = get_platform_id() if callable(get_platform_id) else None
            receipt = DeliveryReceipt.skipped(
                platform_id=platform_id if isinstance(platform_id, str) else ""
            )
        projection = make_projection(receipt)
        committer = getattr(
            self.ctx.execution_context,
            "assistant_history_committer",
            _FALLBACK_HISTORY_COMMITTER,
        )
        history_committed = False
        if pending is not None:
            history_committed = await committer.commit(
                self.conv_manager,
                pending,
                projection,
            )
            if history_committed and projection is not None:
                self._schedule_runtime_memory_postprocess(event, req, projection.text)

        finalized = AssistantHistoryFinalized(
            projection=projection,
            receipt=receipt,
            conversation_id=pending.conversation_id if pending else None,
            run_id=pending.run_id if pending else None,
            history_committed=history_committed,
        )
        event.set_extra("assistant_history_finalized", finalized)
        await call_event_hook(
            event,
            EventType.OnAssistantHistoryFinalized,
            finalized,
            handler_registry=self.ctx.handlers,
            plugin_registry=self.ctx.plugins,
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
