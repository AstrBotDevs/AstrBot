"""Shared execution, steering and history settlement for native agent sessions."""

from __future__ import annotations

import asyncio
import json
from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from astrbot.core.agent.events import RuntimeExecutionError, TurnPrepared
from astrbot.core.agent.input import format_input_content
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentSession,
    AgentSessionRef,
    AgentTurn,
    InputReceipt,
    TurnResult,
)
from astrbot.core.astr_agent_runtime.main_agent.config import MainAgentBuildConfig
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.metrics import Metric
from astrbot.core.utils.session_lock import session_lock_manager

from .execution import execute_native_loop
from .history import record_agent_stats, save_agent_history

if TYPE_CHECKING:
    from astrbot.core.agent.runners.tool_loop_agent_runner import FollowUpTicket
    from astrbot.core.astr_agent_runtime.main_agent.builder import MainAgentBuildResult
    from astrbot.core.astr_agent_runtime.runner import AgentRunner

    from .runtime import AstrAgentRuntime


class NativeAgentSession(AgentSession):
    """Run every native conversation through one execution and commit lifecycle."""

    is_main = True

    def __init__(self, runtime: AstrAgentRuntime, session_id: str, umo: str) -> None:
        super().__init__(session_id, umo)
        self.runtime = runtime
        self._runner: AgentRunner | None = None
        self._steering: list[tuple[FollowUpTicket, InputReceipt]] = []

    def _build_config(self, turn: AgentTurn) -> MainAgentBuildConfig:
        """Resolve the native settings for the upcoming turn.

        Args:
            turn: Accepted input whose configuration is being resolved.

        Returns:
            Settings for request preparation and execution.
        """
        return MainAgentBuildConfig.from_config(
            self.runtime.context.get_config(umo=self.umo)
        )

    def _execution_scope(self) -> AbstractAsyncContextManager[object]:
        """Preserve native UMO serialization while child conversations stay independent.

        Returns:
            Native execution lock held through admission, hooks and history commit.
        """
        return session_lock_manager.acquire_lock(self.umo if self.is_main else self.id)

    async def _prepare_turn(
        self, turn: AgentTurn, build_config: MainAgentBuildConfig
    ) -> MainAgentBuildResult | None:
        """Prepare a request using the session's input and configuration source.

        Args:
            turn: Input admitted for this session.
            build_config: Effective native settings.

        Returns:
            Prepared runner and request, or None when the input is rejected.
        """
        raise NotImplementedError

    async def execute_turn(self, turn: AgentTurn) -> TurnResult:
        """Execute and settle a native turn before releasing session ownership.

        Args:
            turn: Input and output handle for this conversation.

        Returns:
            Native result after history and steering receipts have settled.
        """
        event = turn.input.event
        if (
            event.is_stopped()
            or active_event_registry.get_background_stop_signal(event).is_set()
        ):
            raise asyncio.CancelledError()
        config = self._build_config(turn)
        result = await self._prepare_turn(turn, config)
        if result is None:
            return TurnResult(reason="skipped")
        runner, req, provider = (
            result.agent_runner,
            result.provider_request,
            result.provider,
        )
        runner.run_context.context.permissions = turn.input.permissions
        runner.run_context.context.agent_session = AgentSessionRef("astrbot", self.id)
        self._runner = runner
        runner.run_context.context._runtime = self.runtime
        if self.is_main:
            self.runtime._active_main[self.umo] = turn
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
        turn.emit(
            TurnPrepared(
                user_prompt=req.prompt or "",
                model=provider.get_model(),
                provider_id=provider.provider_config.get("id"),
                persona_id=event.get_extra("_trace_persona_id"),
                tool_names=tuple(req.func_tool.names()) if req.func_tool else (),
                streaming=runner.streaming,
            )
        )
        try:
            return await execute_native_loop(runner, turn, config.max_steps)
        finally:
            await self._finish_turn(turn, result)

    async def _commit_history(
        self, history: list[dict], token_usage: int | None
    ) -> None:
        """Write already-normalized history to this session's conversation.

        Args:
            history: Canonical messages produced by the shared history policy.
            token_usage: Latest context token usage, or None when unknown.
        """
        await self.runtime.context.conversation_manager.update_conversation(
            self.umo, self.id, history=history, token_usage=token_usage
        )

    async def _finish_turn(self, turn: AgentTurn, result: MainAgentBuildResult) -> None:
        """Commit native history and settle steering for every execution path.

        Args:
            turn: Execution being finalized.
            result: Prepared runner, request and provider.
        """
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
                try:
                    saved = await save_agent_history(
                        req=req,
                        llm_response=response,
                        all_messages=runner.run_context.messages,
                        runner_stats=runner.stats,
                        user_aborted=runner.was_aborted(),
                        commit=self._commit_history,
                        checkpoint_id=event.get_extra("llm_checkpoint_id")
                        if self.is_main
                        else None,
                    )
                except Exception as exc:
                    raise RuntimeExecutionError(
                        "history_save_failed", str(exc)
                    ) from exc
            await record_agent_stats(event, req, runner, response)
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
            if self.is_main:
                if self.runtime._active_main.get(self.umo) is turn:
                    self.runtime._active_main.pop(self.umo)
            self._runner = None

    async def cancel_turn(self, turn: AgentTurn) -> None:
        """Stop this session's current native execution.

        Args:
            turn: Exact execution being cancelled.
        """
        await self.request_stop_turn(turn)

    async def request_stop_turn(self, turn: AgentTurn) -> bool:
        """Stop the native loop and allow the turn to save its history.

        Args:
            turn: Exact execution receiving the stop request.

        Returns:
            Whether the current loop can handle the stop itself.
        """
        if self.active_turn is turn and self._runner is not None:
            self._runner.request_stop()
            return True
        return False

    def steer_turn(self, turn: AgentTurn, input: AgentInput) -> InputReceipt | None:
        """Submit additional input through the runner's safe-boundary mechanism.

        Args:
            turn: Exact active execution.
            input: Additional authorized input.

        Returns:
            Receipt settled after durable consumption, or None if rejected.
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
        """Read the committed history owned by this session.

        Returns:
            Detached canonical model messages.
        """
        conversation = await self.runtime.context.conversation_manager.get_conversation(
            self.umo, self.id
        )
        return json.loads(conversation.history) if conversation is not None else []
