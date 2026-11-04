"""AstrBot runtime delegation, scheduling, and result delivery across agent runtimes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from copy import deepcopy
from time import time
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot import logger
from astrbot.core.agent.input import parse_input_content
from astrbot.core.agent.runtime import (
    AgentPermissions,
    AgentRuntime,
    AgentTurn,
    InputReceipt,
    TurnStatus,
)
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.config_number import coerce_int_config

from .caller import AgentCaller, DelegatedAgentInput
from .context import SubAgentContext
from .delivery import AgentResultDelivery
from .store import (
    AgentRecord,
    AgentScope,
    AgentState,
    DeliveryStage,
    SubAgentStore,
    TaskRecord,
)

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class SubAgentService:
    """Expose one session API while agent runtimes own their execution details."""

    def __init__(self, store: SubAgentStore, runtimes: dict[str, AgentRuntime]) -> None:
        self.store = store
        self.runtimes = runtimes
        self._turn_handles: dict[str, AgentTurn] = {}
        self._workers: dict[str, asyncio.Task[None]] = {}
        self._deliveries: dict[str, set[asyncio.Task[None]]] = {}
        self._callers: dict[AgentScope, AgentCaller] = {}
        self._task_callers: dict[tuple[str, int], AgentCaller] = {}
        self.delivery = AgentResultDelivery(store, self._callers, self.runtimes)
        self._changed = asyncio.Condition()
        self._slots = asyncio.Condition()
        self._running: dict[str, int] = {}
        self._closing = False
        self._lifecycle_lock = asyncio.Lock()
        self._cleanup_tasks: set[asyncio.Task[None]] = set()

    async def start(self, context: Context) -> None:
        """Restore sessions and pending results without replaying interrupted inputs.

        Args:
            context: Application services with initialized platform adapters.
        """
        self.delivery.context = context
        await self.store.load()
        scopes = set()
        for agent in list(self.store.agents.values()):
            conversation = await context.conversation_manager.get_conversation(
                agent.scope.umo, agent.scope.conversation_id
            )
            if conversation is None:
                await self.store.remove(agent)
                continue
            if conversation.user_id != agent.scope.umo:
                raise ValueError("Agent session belongs to another main conversation")
            for turn in agent.turns:
                if not turn.finished:
                    turn.state = AgentState.INTERRUPTED
                    turn.error = "Interrupted by restart. Completed steps were retained; inspect the input and use send_message to continue."
                    turn.finished_at = time()
            await self.store.save(agent)
            scopes.add(agent.scope)
        for scope in scopes:
            self.delivery.schedule(scope)

    def _caller(self, context: SubAgentContext) -> AgentCaller:
        """Resolve ownership and reject nested delegation or stopped sessions.

        Args:
            context: Main agent's bound tool context.

        Returns:
            Fresh caller services, scope, and tools.

        Raises:
            ValueError: If delegation is unavailable for this execution.
        """
        if self._closing:
            raise ValueError("Cannot use subagents while AstrBot is shutting down")
        if not isinstance(context, SubAgentContext) or context.subagent_scope is None:
            raise ValueError("Subagent tools require a bound main conversation")
        if context.is_subagent:
            raise ValueError("Subagents cannot create or control further agents")
        if context.agent_session is None:
            raise ValueError("Subagent tools require an explicit parent agent session")
        if active_event_registry.get_background_stop_signal(context.event).is_set():
            raise ValueError("Cannot use subagents after the session was stopped")
        previous = self._callers.get(context.subagent_scope)
        caller = AgentCaller(
            context.context,
            context.event,
            context.subagent_scope,
            context.delegable_tools,
            context,
            limits=previous.limits if previous is not None else {},
        )
        self._callers[caller.scope] = caller
        return caller

    async def spawn(
        self,
        context: SubAgentContext,
        messages: list[dict],
        *,
        runtime: str = "astrbot",
        config: dict | None = None,
        config_id: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Accept a new agent session without waiting for its first model response.

        Args:
            context: Main execution owning the new session.
            messages: Explicit initial input components.
            runtime: Registered agent runtime name.
            config: Validated runtime configuration captured for this session.
            config_id: Optional source spec identity, retained as metadata.
            name: Optional display name.

        Returns:
            Public agent identity and initial execution metadata.

        Raises:
            ValueError: If input, runtime, or ownership is invalid.
        """
        caller = self._caller(context)
        parent = caller.agent_context.agent_session
        assert parent is not None
        content = parse_input_content(messages)
        messages = [item.model_dump(exclude_none=True) for item in content]
        if not isinstance(runtime, str) or runtime not in self.runtimes:
            raise ValueError(f"Unknown agent runtime: {runtime}")
        options: dict[str, Any] = {"config": deepcopy(config or {})}
        if config_id is not None:
            options["config_id"] = config_id
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                raise ValueError("name must be a nonempty string")
            options["name"] = name.strip()
        input = DelegatedAgentInput(
            event=caller.event,
            permissions=caller.agent_context.permissions
            or AgentPermissions.from_event(caller.event),
            content=content,
            plugin_tools=caller.agent_context.plugin_tools,
            plugin_skills=caller.agent_context.plugin_skills,
            caller=caller,
        )
        session = await self.runtimes[runtime].open_session(
            caller.scope.umo,
            options={"profile": "subagent", **options},
            input=input,
        )
        conversation_id = session.id
        async with self._lifecycle_lock:
            if self._closing:
                await session.close()
                raise ValueError("Cannot open an agent while AstrBot is shutting down")
            if not isinstance(conversation_id, str) or not conversation_id:
                raise ValueError("Agent runtime returned an empty conversation ID")
            if any(
                agent.runtime == runtime and agent.conversation_id == conversation_id
                for agent in self.store.agents.values()
            ):
                raise ValueError(
                    "Agent runtime returned a conversation already owned by another agent"
                )
            agent = AgentRecord(
                agent_id=uuid4().hex,
                scope=caller.scope,
                runtime=runtime,
                name=options.get("name") or "worker",
                options=options,
                conversation_id=conversation_id,
                owner=caller.owner_metadata(),
                parent=parent,
                turns=[TaskRecord(1, messages, permissions=input.permissions)],
                next_turn_id=2,
            )
            try:
                await self.store.save(agent)
            except BaseException:
                try:
                    await session.close()
                except Exception:
                    logger.exception(
                        "Unable to cancel an unregistered agent conversation"
                    )
                raise
            self.store.agents[agent.agent_id] = agent
            self._task_callers[(agent.agent_id, 1)] = caller
            self._schedule(agent, caller)
            return agent.describe()

    async def send(
        self, context: SubAgentContext, agent_id: str, messages: list[dict]
    ) -> dict:
        """Accept follow-up input, merging only when its runtime confirms safe delivery.

        Args:
            context: Current main execution owning the agent.
            agent_id: Public agent ID.
            messages: Structured follow-up input.

        Returns:
            Acceptance metadata; execution continues asynchronously.
        """
        async with self._lifecycle_lock:
            caller = self._caller(context)
            content = parse_input_content(messages)
            messages = [item.model_dump(exclude_none=True) for item in content]
            agent = self.store.get(agent_id, caller.scope)
            runtime = self.runtimes.get(agent.runtime)
            if runtime is None:
                raise ValueError(f"Agent runtime unavailable: {agent.runtime}")
            turn = TaskRecord(
                agent.next_turn_id,
                messages,
                permissions=caller.agent_context.permissions
                or AgentPermissions.from_event(caller.event),
            )
            agent.next_turn_id += 1
            agent.turns.append(turn)
            agent.owner = caller.owner_metadata()
            await self.store.save(agent)
            self._task_callers[(agent.agent_id, turn.turn_id)] = caller
            handle = self._turn_handles.get(agent.agent_id)
            if handle is not None:
                receipt = handle.steer(
                    DelegatedAgentInput(
                        event=caller.event,
                        permissions=turn.permissions,
                        content=content,
                        plugin_tools=caller.agent_context.plugin_tools,
                        plugin_skills=caller.agent_context.plugin_skills,
                        caller=caller,
                        sequence=turn.turn_id,
                    )
                )
                if receipt is not None:
                    task = asyncio.create_task(
                        self._confirm_follow_up(agent, turn, receipt)
                    )
                    self._deliveries.setdefault(agent.agent_id, set()).add(task)
            self._schedule(agent, caller)
            return {**agent.describe(), "accepted": True}

    async def _confirm_follow_up(
        self, agent: AgentRecord, turn: TaskRecord, receipt: InputReceipt
    ) -> None:
        """Remove queued input only after its runtime has durably consumed it.

        Args:
            agent: Agent receiving the follow-up.
            turn: Queue entry retained until delivery is confirmed.
            receipt: Runtime's safe-boundary receipt.
        """
        try:
            if await receipt:
                agent.turns.remove(turn)
                self._task_callers.pop((agent.agent_id, turn.turn_id), None)
                await self.store.save(agent)
        finally:
            current = asyncio.current_task()
            if current is not None:
                self._deliveries[agent.agent_id].discard(current)

    def list(self, context: SubAgentContext) -> list[dict]:
        """List sessions visible to the calling main conversation.

        Args:
            context: Bound main execution.

        Returns:
            Runtime-independent session metadata.
        """
        return [
            agent.describe() for agent in self.store.list(self._caller(context).scope)
        ]

    async def result(self, context: SubAgentContext, agent_id: str) -> dict:
        """Read and acknowledge a terminal result without deleting it.

        Args:
            context: Bound main execution.
            agent_id: Public agent ID.

        Returns:
            Current state and optional result with a history receipt.
        """
        agent = self.store.get(agent_id, self._caller(context).scope)
        turn = agent.current
        if turn.finished and turn.delivery != DeliveryStage.COMMITTED:
            turn.delivery = DeliveryStage.OBSERVED
            await self.store.save(agent)
        return agent.describe(turn, result=True)

    async def wait(
        self, context: SubAgentContext, agent_ids: list[str], timeout_ms: int, mode: str
    ) -> dict:
        """Wait for a fixed snapshot of executions without cancelling them on timeout.

        Args:
            context: Bound main execution.
            agent_ids: Nonempty list of owned agents.
            timeout_ms: Wait budget from zero to sixty seconds.
            mode: Whether any or all selected executions must finish.

        Returns:
            Finished results, timeout state, and result receipts.

        Raises:
            ValueError: If IDs or waiting options are invalid.
        """
        scope = self._caller(context).scope
        if (
            not agent_ids
            or not isinstance(agent_ids, list)
            or mode not in ("any", "all")
        ):
            raise ValueError("agent_ids must be nonempty and mode must be any or all")
        if (
            not isinstance(timeout_ms, int)
            or isinstance(timeout_ms, bool)
            or not 0 <= timeout_ms <= 60000
        ):
            raise ValueError("timeout_ms must be between 0 and 60000")
        selected = [
            (agent, agent.current)
            for agent in [
                self.store.get(agent_id, scope) for agent_id in dict.fromkeys(agent_ids)
            ]
        ]

        def ready() -> bool:
            return (all if mode == "all" else any)(
                turn.finished for _, turn in selected
            )

        timed_out = False
        async with self._changed:
            if not ready():
                try:
                    await asyncio.wait_for(
                        self._changed.wait_for(ready), timeout_ms / 1000
                    )
                except asyncio.TimeoutError:
                    timed_out = True
        results = []
        for agent, turn in selected:
            if turn.finished:
                if turn.delivery != DeliveryStage.COMMITTED:
                    turn.delivery = DeliveryStage.OBSERVED
                    await self.store.save(agent)
            results.append(agent.describe(turn, result=True))
        return {
            "agents": results,
            "timed_out": timed_out,
            "receipts": [item["receipt"] for item in results if "receipt" in item],
        }

    async def cancel(self, context: SubAgentContext, agent_id: str) -> dict:
        """Cancel one agent's accepted inputs while keeping its conversation reusable.

        Args:
            context: Main execution owning the agent.
            agent_id: Public agent ID.

        Returns:
            Current result and cancellation status.
        """
        caller = self._caller(context)
        agent = self.store.get(agent_id, caller.scope)
        handle = self._turn_handles.get(agent.agent_id)
        if handle is not None:
            await handle.cancel()
        task = self._workers.get(agent_id)
        if task is not None:
            active_event_registry.cancel_background_task(task)
            await asyncio.gather(task, return_exceptions=True)
            if self._workers.get(agent_id) is task:
                self._workers.pop(agent_id)
        self._stop_pending(agent, AgentState.CANCELLED, "Cancelled by caller")
        await self.store.save(agent)
        self.delivery.schedule(agent.scope)
        async with self._changed:
            self._changed.notify_all()
        return {**agent.describe(result=True), "cancel_requested": True}

    def _schedule(self, agent: AgentRecord, caller: AgentCaller) -> None:
        """Retain one driver per agent, with all inputs serialized through that driver.

        Args:
            agent: Session with accepted pending input.
            caller: Current session owner and permissions.
        """
        task = self._workers.get(agent.agent_id)
        if task is None or task.done():
            task = asyncio.create_task(self._drive(agent, caller))
            self._workers[agent.agent_id] = task
            active_event_registry.register_background_task(caller.event, task)

            def completed(done: asyncio.Task[None]) -> None:
                if (
                    self._workers.get(agent.agent_id) is not done
                    or not done.cancelled()
                ):
                    return
                # A cancellation before coroutine entry cannot execute _drive's
                # finally. Mark its inputs synchronously before accepting more.
                self._workers.pop(agent.agent_id)
                state = (
                    AgentState.INTERRUPTED if self._closing else AgentState.CANCELLED
                )
                self._stop_pending(agent, state, "Stopped before execution started")
                cleanup = asyncio.create_task(self._flush_stopped(agent))
                self._cleanup_tasks.add(cleanup)
                cleanup.add_done_callback(self._cleanup_tasks.discard)

            task.add_done_callback(completed)

    def _stop_pending(self, agent: AgentRecord, state: AgentState, error: str) -> None:
        """Terminate accepted inputs without resetting or discarding the conversation.

        Args:
            agent: Session whose unfinished inputs should stop.
            state: Cancellation or interruption outcome.
            error: Explanation retained with each unprocessed input.
        """
        for turn in agent.turns:
            if not turn.finished:
                turn.state, turn.error, turn.finished_at = state, error, time()
                self._task_callers.pop((agent.agent_id, turn.turn_id), None)

    async def _flush_stopped(self, agent: AgentRecord) -> None:
        """Persist cancellation that happened before driver startup.

        Args:
            agent: Session whose accepted inputs have already been terminated.
        """
        try:
            await self.store.save(agent)
            async with self._changed:
                self._changed.notify_all()
            self.delivery.schedule(agent.scope)
        except Exception:
            logger.exception("Unable to save cancelled agent %s", agent.agent_id)

    @asynccontextmanager
    async def _slot(self, umo: str, limit: int) -> AsyncIterator[None]:
        """Share execution capacity across agents and owner scopes in one UMO.

        Args:
            umo: Session whose capacity is limited.
            limit: Maximum simultaneous prompts.

        Yields:
            A held execution slot, released on every exit path.
        """
        async with self._slots:
            await self._slots.wait_for(lambda: self._running.get(umo, 0) < limit)
            self._running[umo] = self._running.get(umo, 0) + 1
        try:
            yield
        finally:
            async with self._slots:
                self._running[umo] -= 1
                if not self._running[umo]:
                    del self._running[umo]
                self._slots.notify_all()

    async def _execute(
        self, agent: AgentRecord, turn: TaskRecord, caller: AgentCaller, limit: int
    ) -> str:
        """Execute one accepted turn through its selected agent runtime.

        Args:
            agent: Stable public agent session.
            turn: Input being executed.
            caller: Current scope and permissions.
            limit: Concurrent prompt limit for the UMO.

        Returns:
            Final runtime response text.
        """
        async with self._slot(agent.scope.umo, limit):
            turn.state, turn.started_at = AgentState.RUNNING, time()
            await self.store.save(agent)
            session = await self.runtimes[agent.runtime].open_session(
                agent.scope.umo,
                session_id=agent.conversation_id,
                options={"profile": "subagent"},
            )
            session.runtime_name = agent.runtime
            handle = await session.run_turn(
                DelegatedAgentInput(
                    event=caller.event,
                    permissions=turn.permissions,
                    content=parse_input_content(turn.messages),
                    plugin_tools=caller.agent_context.plugin_tools,
                    plugin_skills=caller.agent_context.plugin_skills,
                    caller=caller,
                    sequence=turn.turn_id,
                )
            )
            self._turn_handles[agent.agent_id] = handle
            try:
                result = await handle.result()
                if result.metrics.steps is not None:
                    turn.completed_steps = result.metrics.steps
                    await self.store.save(agent)
                if result.status == TurnStatus.CANCELLED:
                    raise asyncio.CancelledError()
                if result.status == TurnStatus.FAILED:
                    raise RuntimeError(
                        result.error.message
                        if result.error
                        else "Agent execution failed"
                    )
                return result.text
            except BaseException:
                await handle.cancel()
                raise
            finally:
                if self._turn_handles.get(agent.agent_id) is handle:
                    self._turn_handles.pop(agent.agent_id)

    async def _drive(self, agent: AgentRecord, caller: AgentCaller) -> None:
        """Own all execution transitions and route every outcome through one exit path.

        Args:
            agent: Session whose inputs should be drained serially.
            caller: Owner supplied when work was scheduled.
        """
        stopped = False
        try:
            while (
                turn := next(
                    (item for item in agent.turns if item.state == AgentState.PENDING),
                    None,
                )
            ) is not None:
                caller = self._task_callers[(agent.agent_id, turn.turn_id)]
                config = caller.limits
                limit = coerce_int_config(
                    config.get("max_concurrent_agents", 3),
                    default=3,
                    min_value=1,
                    field_name="subagent.max_concurrent_agents",
                )
                timeout = coerce_int_config(
                    config.get("task_timeout", 600),
                    default=600,
                    min_value=1,
                    field_name="subagent.task_timeout",
                )
                outcome, result, error = AgentState.FAILED, None, None
                try:
                    result = await asyncio.wait_for(
                        self._execute(agent, turn, caller, limit),
                        max(0, timeout - (time() - turn.created_at)),
                    )
                    outcome = AgentState.COMPLETED
                except asyncio.TimeoutError:
                    outcome, error = (
                        AgentState.TIMED_OUT,
                        "Agent task timed out, including queue time",
                    )
                    handle = self._turn_handles.get(agent.agent_id)
                    if handle is not None:
                        await handle.cancel()
                except asyncio.CancelledError:
                    stopped = True
                    outcome = (
                        AgentState.INTERRUPTED
                        if self._closing
                        else AgentState.CANCELLED
                    )
                    error = (
                        "Interrupted by service shutdown"
                        if self._closing
                        else "Agent execution was cancelled"
                    )
                    handle = self._turn_handles.get(agent.agent_id)
                    if handle is not None:
                        await handle.cancel()
                    raise
                except Exception as exc:
                    error = str(exc) or type(exc).__name__
                    logger.exception(
                        "Agent %s failed through runtime %s",
                        agent.agent_id,
                        agent.runtime,
                    )
                finally:
                    # Keep the active turn visible until steering receipts have
                    # retired their queue entries. Waiters must never snapshot
                    # an input that is about to merge into this turn.
                    deliveries = list(self._deliveries.get(agent.agent_id, ()))
                    if deliveries:
                        await asyncio.gather(*deliveries, return_exceptions=False)
                    turn.state, turn.result, turn.error = outcome, result, error
                    turn.finished_at = time()
                    self._task_callers.pop((agent.agent_id, turn.turn_id), None)
                    await self.store.save(agent)
                    async with self._changed:
                        self._changed.notify_all()
                    self.delivery.schedule(agent.scope)
        finally:
            self._workers.pop(agent.agent_id, None)
            if (
                stopped
                or self._closing
                or active_event_registry.get_background_stop_signal(
                    caller.event
                ).is_set()
            ):
                self._stop_pending(
                    agent,
                    AgentState.INTERRUPTED if self._closing else AgentState.CANCELLED,
                    "Execution stopped before this input was processed",
                )
                await self.store.save(agent)
            elif any(item.state == AgentState.PENDING for item in agent.turns):
                self._schedule(agent, self._callers.get(agent.scope, caller))

    async def close(self) -> None:
        """Stop active executions, flush records, then close agent runtime resources."""
        async with self._lifecycle_lock:
            if self._closing:
                return
            self._closing = True
        await self.delivery.close()
        tasks = list(self._workers.values())
        for task in tasks:
            active_event_registry.cancel_background_task(task)
        await asyncio.gather(*tasks, return_exceptions=True)
        await asyncio.gather(*self._cleanup_tasks, return_exceptions=True)
        for agent in self.store.agents.values():
            self._stop_pending(
                agent, AgentState.INTERRUPTED, "Interrupted by service shutdown"
            )
            await self.store.save(agent)
        for runtime in self.runtimes.values():
            await runtime.close()
