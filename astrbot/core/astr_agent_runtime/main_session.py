"""The main conversation's native execution, hooks, history, and steering."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.agent.input import ImageInput, format_input_content
from astrbot.core.agent.message import TextPart
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentSession,
    AgentSessionRef,
    AgentTurn,
    InputReceipt,
    TurnResult,
)
from astrbot.core.agent_input import CollectedInput, collect_initial_request
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.llm_error_messages import LLM_ERROR_MESSAGE_EXTRA_KEY
from astrbot.core.message.components import Reply
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.config_number import coerce_int_config
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.session_lock import session_lock_manager

from .execution import execute_native_loop
from .history import record_main_stats, save_main_history

if TYPE_CHECKING:
    from astrbot.core.agent.runners.tool_loop_agent_runner import FollowUpTicket
    from astrbot.core.astr_agent_runtime.main_agent.builder import MainAgentBuildResult
    from astrbot.core.astr_agent_runtime.runner import AgentRunner
    from astrbot.core.provider.entities import ProviderRequest

    from .runtime import AstrAgentRuntime


@dataclass
class MainAgentInput(AgentInput):
    """Native main input, including host preprocessing and per-turn settings."""

    build_config: MainAgentBuildConfig | None = None
    request: ProviderRequest | None = None
    admit: Callable[[], Awaitable[bool]] | None = None


class MainAgentSession(AgentSession):
    """Own one bound AstrBot conversation, independent of the current UMO selection."""

    def __init__(self, runtime: AstrAgentRuntime, session_id: str, umo: str) -> None:
        super().__init__(session_id, umo)
        self.runtime = runtime
        self._runner: AgentRunner | None = None
        self._steering: list[tuple[FollowUpTicket, InputReceipt]] = []

    async def execute_turn(self, turn: AgentTurn) -> TurnResult:
        """Build, drive and persist a complete main turn under runtime ownership.

        Args:
            turn: Accepted main input and its output sink.

        Returns:
            The settled result after native hooks and history persistence.
        """
        input = turn.input
        event = input.event
        context = self.runtime.context
        config = context.get_config(umo=self.umo)
        build_config = (
            input.build_config
            if isinstance(input, MainAgentInput) and input.build_config is not None
            else MainAgentBuildConfig.from_config(config)
        )
        async with session_lock_manager.acquire_lock(self.umo):
            if (
                event.is_stopped()
                or active_event_registry.get_background_stop_signal(event).is_set()
            ):
                raise asyncio.CancelledError()
            if (
                isinstance(input, MainAgentInput)
                and input.admit is not None
                and not await input.admit()
            ):
                return TurnResult(reason="skipped")
            result = await self._prepare_turn(turn, build_config)
            if result is None:
                return TurnResult(reason="skipped")
            runner, req, provider = (
                result.agent_runner,
                result.provider_request,
                result.provider,
            )
            runner.run_context.context.permissions = input.permissions
            runner.run_context.context.agent_session = AgentSessionRef(
                "astrbot", self.id
            )
            self._runner = runner
            self.runtime._active_main[self.umo] = turn
            active_event_registry.register_agent_stop_callback(
                event, runner.request_stop
            )
            metadata = {
                "user_prompt": req.prompt,
                "persona_id": event.get_extra("_trace_persona_id"),
                "system_prompt": req.system_prompt,
                "tools": req.func_tool.names() if req.func_tool else [],
                "stream": runner.streaming,
                "chat_provider": {
                    "id": provider.provider_config.get("id", ""),
                    "model": provider.get_model(),
                },
            }
            event.trace.record("astr_agent_prepare", **metadata)
            turn.emit("prepared", metadata)
            try:
                max_steps = coerce_int_config(
                    config.get("agent_runner", {})
                    .get("config", {})
                    .get("misc", {})
                    .get("max_steps", 128),
                    default=128,
                    min_value=1,
                    field_name="agent_runner.config.misc.max_steps",
                )
                outcome = await execute_native_loop(runner, turn, max_steps)
                return outcome
            finally:
                await self._finish_turn(turn, result)

    async def _prepare_turn(
        self, turn: AgentTurn, build_config: MainAgentBuildConfig
    ) -> MainAgentBuildResult | None:
        """Bind committed native history before building capabilities and hooks.

        Args:
            turn: Input admitted under this conversation's execution lock.
            build_config: Native settings resolved for this execution.

        Returns:
            Prepared native execution, or None when input or a hook rejects it.
        """
        from astrbot.core.astr_agent_runtime.main_agent.builder import build_main_agent
        from astrbot.core.provider.entities import ProviderRequest

        input = turn.input
        event = input.event
        context = self.runtime.context
        conversation = await context.conversation_manager.get_conversation(
            self.umo, self.id
        )
        if conversation is None:
            raise ValueError("The bound agent conversation no longer exists")
        req = input.request if isinstance(input, MainAgentInput) else None
        explicit = req is not None or event.get_extra("provider_request") is not None
        if (
            req is None
            and input.content is not None
            and event.get_extra("provider_request") is None
        ):
            req = ProviderRequest(prompt=format_input_content(input.content))
            req.image_urls = [
                item.source for item in input.content if isinstance(item, ImageInput)
            ]
        parse_quoted = req is None or (
            any(isinstance(part, Reply) for part in event.message_obj.message)
            and not any(
                isinstance(part, TextPart)
                and part.text.startswith("<Quoted Message>\n")
                for part in req.extra_user_content_parts
            )
        )
        quote_refs: set[str] = set()
        sources: list[str] = []
        req, quote_ref = await collect_initial_request(
            event,
            context,
            build_config,
            req=req,
            quoted_image_refs=quote_refs,
            materialized_paths=sources,
        )
        if req is None:
            return None
        # Explicit unbound SDK/plugin contexts keep their established semantics.
        # Ordinary turns always reload this session's history after execution admission.
        if not explicit or req.conversation is not None:
            req.conversation = conversation
            req.contexts = json.loads(conversation.history)
        if not explicit:
            event.set_extra("provider_request", req)
        collected = CollectedInput(
            req, quote_ref, quote_refs, parse_quoted=parse_quoted, source_paths=sources
        )
        result = await build_main_agent(
            event=event,
            plugin_context=context,
            config=build_config,
            req=req,
            collected_input=collected,
            plugin_tools=input.plugin_tools,
            plugin_skills=input.plugin_skills,
        )
        if result is None:
            error = event.get_extra(LLM_ERROR_MESSAGE_EXTRA_KEY)
            if error:
                raise RuntimeError(str(error))
            return None
        return result

    async def _finish_turn(self, turn: AgentTurn, result: MainAgentBuildResult) -> None:
        """Commit native state and settle steering before releasing execution.

        Args:
            turn: Execution whose history and receipts are settling.
            result: Native runner, request, and provider owned by this execution.
        """
        context = self.runtime.context
        event = turn.input.event
        runner, req, provider = (
            result.agent_runner,
            result.provider_request,
            result.provider,
        )
        saved = False
        try:
            response = runner.get_final_llm_resp()
            if not event.is_stopped() and not turn.cancellation_requested:
                await save_main_history(
                    context,
                    event=event,
                    req=req,
                    llm_response=response,
                    all_messages=runner.run_context.messages,
                    runner_stats=runner.stats,
                    user_aborted=runner.was_aborted(),
                )
                saved = True
            await record_main_stats(event, req, runner, response)
            event.trace.record(
                "astr_agent_complete",
                stats=runner.stats.to_dict(),
                resp=response.completion_text if response else None,
            )
            asyncio.create_task(
                Metric.upload(
                    llm_tick=1,
                    model_name=provider.get_model(),
                    provider_type=provider.meta().type,
                )
            )
        finally:
            runner._resolve_unconsumed_follow_ups()
            for ticket, receipt in self._steering:
                if not receipt.done():
                    receipt.resolve(saved and ticket.consumed)
            self._steering.clear()
            active_event_registry.unregister_agent_stop_callback(event)
            if self.runtime._active_main.get(self.umo) is turn:
                self.runtime._active_main.pop(self.umo)
            self._runner = None

    async def cancel_turn(self, turn: AgentTurn) -> None:
        """Stop only this session's active native turn.

        Args:
            turn: Exact turn being cancelled.
        """
        if self.active_turn is turn and self._runner is not None:
            self._runner.request_stop()

    def steer_turn(self, turn: AgentTurn, input: AgentInput) -> InputReceipt | None:
        """Use the existing runner's safe-boundary follow-up mechanism.

        Args:
            turn: Exact active turn, checked by the public handle.
            input: Additional input already authorized by the handle.

        Returns:
            A receipt resolved only after consumed input has been saved.
        """
        if self._runner is None:
            return None
        text = (
            format_input_content(input.content)
            if input.content is not None
            else input.event.get_message_str() or input.event.get_message_outline()
        )
        ticket = self._runner.follow_up(message_text=text)
        if ticket is None:
            return None
        receipt = InputReceipt()
        self._steering.append((ticket, receipt))
        return receipt

    async def history(self) -> list[dict]:
        """Read this session's committed main history.

        Returns:
            Detached model history from the native conversation store.
        """
        import json

        conversation = await self.runtime.context.conversation_manager.get_conversation(
            self.umo, self.id
        )
        return json.loads(conversation.history) if conversation is not None else []
