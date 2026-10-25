from __future__ import annotations

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from enum import Enum
from time import time
from typing import TYPE_CHECKING
from uuid import uuid4

from astrbot.core.agent.agent import Agent
from astrbot.core.agent.message import Message
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import ToolSet

if TYPE_CHECKING:
    from astrbot.core.agent.runners.tool_loop_agent_runner import (
        FollowUpTicket,
        ToolLoopAgentRunner,
    )

    from .context import SubAgentContext as AstrAgentContext
    from .store import SubAgentStore


class SubAgentState(str, Enum):
    """Lifecycle states of one delegated execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


class SubAgentScheduler:
    """Share execution slots across root turns in the same session."""

    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._running: dict[str, int] = {}

    @asynccontextmanager
    async def slot(self, origin: str, limit: int):
        """Wait for a session slot and release it even on cancellation.

        Args:
            origin: Session whose concurrent executions are limited.
            limit: Maximum active workers for this submission.

        Yields:
            Control while one execution slot is held.
        """
        async with self._condition:
            await self._condition.wait_for(lambda: self._running.get(origin, 0) < limit)
            self._running[origin] = self._running.get(origin, 0) + 1
        try:
            yield
        finally:
            async with self._condition:
                remaining = self._running[origin] - 1
                if remaining:
                    self._running[origin] = remaining
                else:
                    del self._running[origin]
                self._condition.notify_all()


@dataclass
class SubAgentInstance:
    """A template snapshot and execution context owned by one parent task.

    The platform event, plugin context and tool/hook implementations are
    shared resources. Messages, task metadata and template dialogue are private
    to the instance. This is context isolation, not an authorization boundary.
    """

    agent_id: str
    parent_agent_id: str
    unified_msg_origin: str
    conversation_id: str | None
    agent: Agent[AstrAgentContext]
    run_context: ContextWrapper[AstrAgentContext]
    task: str | None
    provider_id: str | None = None
    execution_task: asyncio.Task | None = field(default=None, init=False, repr=False)
    created_at: float = field(default_factory=time)
    started_at: float | None = field(default=None, init=False)
    finished_at: float | None = field(default=None, init=False)
    result: str | None = field(default=None, init=False)
    error: str | None = field(default=None, init=False)
    finished: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _state: SubAgentState = field(default=SubAgentState.PENDING, init=False)
    result_received: bool = field(default=False, init=False)
    turn_id: int = field(default=1, init=False)
    pending_messages: list[str] = field(default_factory=list, init=False, repr=False)
    steering_tickets: list[FollowUpTicket] = field(
        default_factory=list, init=False, repr=False
    )
    runner: ToolLoopAgentRunner | None = field(default=None, init=False, repr=False)
    cancel_requested: bool = field(default=False, init=False)
    completed_steps: int = field(default=0, init=False)
    updated_at: float = field(default_factory=time, init=False)
    checkpoint_messages: list[Message] | None = field(
        default=None, init=False, repr=False
    )

    @property
    def state(self) -> SubAgentState:
        """Return the current lifecycle state."""
        return self._state

    def to_dict(self, *, include_result: bool = False) -> dict:
        """Describe a worker without exposing its intermediate messages.

        Args:
            include_result: Include final text and error details when requested.

        Returns:
            JSON-compatible worker metadata and optional result fields.
        """
        data = {
            "agent_id": self.agent_id,
            "parent_agent_id": self.parent_agent_id,
            "name": self.agent.name,
            "provider_id": self.provider_id,
            "state": self.state.value,
            "turn_id": self.turn_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "completed_steps": self.completed_steps,
            "updated_at": self.updated_at,
        }
        if include_result:
            data.update(result=self.result, error=self.error)
        return data

    def start(self) -> None:
        """Mark a pending instance as running.

        Raises:
            ValueError: If the instance has already started or finished.
        """
        if self._state != SubAgentState.PENDING:
            raise ValueError(f"Cannot start a subagent in state {self._state.value}")
        self._state = SubAgentState.RUNNING
        self.started_at = time()
        self.updated_at = self.started_at

    def finish(
        self,
        state: SubAgentState,
        *,
        result: str | None = None,
        error: str | None = None,
    ) -> None:
        """Publish the terminal state and wake any result waiters.

        Args:
            state: Terminal lifecycle state.
            result: Final text returned by a completed execution.
            error: Failure, timeout or cancellation details.

        Raises:
            ValueError: If the transition is invalid or the instance is finished.
        """
        if state not in {
            SubAgentState.COMPLETED,
            SubAgentState.FAILED,
            SubAgentState.CANCELLED,
            SubAgentState.TIMED_OUT,
            SubAgentState.INTERRUPTED,
        }:
            raise ValueError(f"Not a terminal subagent state: {state}")
        if self.finished.is_set():
            raise ValueError("Subagent has already finished")
        if state == SubAgentState.COMPLETED and self._state != SubAgentState.RUNNING:
            raise ValueError("Cannot complete a subagent that has not started")
        self._state = state
        self.result = result
        self.error = error
        self.finished_at = time()
        self.updated_at = self.finished_at
        self.finished.set()


@dataclass(frozen=True)
class SubAgentCompletion:
    """Capture one completed turn independently of a worker's later turns."""

    agent_id: str
    parent_agent_id: str
    unified_msg_origin: str
    conversation_id: str | None
    turn_id: int
    data: dict

    def to_dict(self, *, include_result: bool = False) -> dict:
        """Return a detached view of the completed turn.

        Args:
            include_result: Include the final result and error text.

        Returns:
            Metadata captured when this turn finished.
        """
        data = dict(self.data)
        if not include_result:
            data.pop("result", None)
            data.pop("error", None)
        return data


class SubAgentRuntime:
    """Track delegated instances, messages, and per-turn completion receipts.

    Managed runtimes are shared across root turns for one session, conversation,
    and sender, and checkpointed through SubAgentStore. Standalone SDK contexts
    without a storage binding keep their own in-memory registry.
    """

    def __init__(self, scheduler: SubAgentScheduler | None = None) -> None:
        self._instances: dict[str, SubAgentInstance] = {}
        self.scheduler = scheduler or SubAgentScheduler()
        self.parent_agent_id: str | None = None
        self.parent_idle = asyncio.Event()
        self.parent_idle.set()
        self._active_parent_runs = 0
        self._pending_results: dict[tuple[str, int], SubAgentCompletion] = {}
        self._received_results: set[tuple[str, int]] = set()
        self._durable_received: set[tuple[str, int]] = set()
        self._completions: dict[tuple[str, int], SubAgentCompletion] = {}
        self.store: SubAgentStore | None = None
        self.storage_scope: tuple[str, str, str] | None = None
        self.parent_context: ContextWrapper[AstrAgentContext] | None = None
        self._persistence_lock = asyncio.Lock()
        self.wakeup_task: asyncio.Task | None = None
        self.settings: dict = {}
        self.wakeup_queued = False

    async def checkpoint(
        self, run_context: ContextWrapper[AstrAgentContext] | None = None
    ) -> None:
        """Save a checkpoint, retiring steering receipts only after a full step.

        Args:
            run_context: Present only at a completed runner step, when tool-call
                pairs and their steering notices are retained in its history.
        """
        if run_context is not None:
            instance = self._instances.get(run_context.context.agent_id)
            if instance is not None:
                instance.steering_tickets[:] = [
                    ticket
                    for ticket in instance.steering_tickets
                    if not ticket.consumed
                ]
        if self.store is not None and self._instances:
            async with self._persistence_lock:
                await self.store.save(self)

    async def commit_received(
        self, receipts: set[tuple[str, int]] | None = None
    ) -> None:
        """Confirm receipts included in a successfully saved parent transcript.

        Args:
            receipts: Receipt snapshot taken before writing parent history.
                Defaults to the receipts currently observed by the parent.
        """
        self._durable_received.update(
            self._received_results if receipts is None else receipts
        )
        await self.checkpoint()

    def begin_parent(
        self,
        run_context: ContextWrapper[AstrAgentContext],
        runner: ToolLoopAgentRunner | None = None,
    ) -> None:
        """Bind worker steering or defer completion delivery while the parent runs.

        Args:
            run_context: Runner context; worker runners do not activate the parent.
            runner: Active runner used to deliver worker steering messages.
        """
        agent_id = run_context.context.agent_id
        if (instance := self._instances.get(agent_id)) is not None:
            instance.runner = runner
            if runner is not None:
                pending = instance.pending_messages
                instance.pending_messages = []
                for message in pending:
                    ticket = runner.follow_up(message_text=message)
                    if ticket is not None:
                        instance.steering_tickets.append(ticket)
                    else:
                        instance.pending_messages.append(message)
            return
        if self.parent_agent_id is None:
            self.parent_agent_id = agent_id
        if agent_id == self.parent_agent_id:
            self.parent_context = run_context
            self._active_parent_runs += 1
            self.parent_idle.clear()

    def end_parent(self, run_context: ContextWrapper[AstrAgentContext]) -> None:
        """Release queued wakeups when the parent run ends or is interrupted.

        Args:
            run_context: Context of the runner leaving its execution scope.
        """
        if (instance := self._instances.get(run_context.context.agent_id)) is not None:
            instance.runner = None
            return
        if (
            run_context.context.agent_id == self.parent_agent_id
            and self._active_parent_runs
        ):
            self._active_parent_runs -= 1
            if not self._active_parent_runs:
                self.parent_idle.set()

    def publish_result(self, instance: SubAgentInstance | SubAgentCompletion) -> None:
        """Queue a terminal result without mutating a running model's messages.

        Args:
            instance: Completed worker owned by this runtime.

        Raises:
            ValueError: If the worker is unknown or has not finished.
        """
        current = self._instances.get(instance.agent_id)
        if (
            current is None
            or (
                isinstance(instance, SubAgentInstance)
                and (current is not instance or not instance.finished.is_set())
            )
            or instance.parent_agent_id != current.parent_agent_id
            or instance.turn_id > current.turn_id
        ):
            raise ValueError("Only terminal results from this runtime can be queued")
        key = (instance.agent_id, instance.turn_id)
        if isinstance(instance, SubAgentInstance):
            instance = SubAgentCompletion(
                agent_id=instance.agent_id,
                parent_agent_id=instance.parent_agent_id,
                unified_msg_origin=instance.unified_msg_origin,
                conversation_id=instance.conversation_id,
                turn_id=instance.turn_id,
                data=instance.to_dict(include_result=True),
            )
        self._completions[key] = instance
        if key in self._received_results:
            return
        self._pending_results[key] = instance

    def take_results(self) -> list[SubAgentCompletion]:
        """Remove one original-conversation batch for delivery.

        Returns:
            Unreceived results for the first queued conversation, in arrival order.
        """
        pending = list(self._pending_results.values())
        if not pending:
            self._pending_results.clear()
            return []
        first = pending[0]
        batch = [
            item
            for item in pending
            if (
                item.unified_msg_origin == first.unified_msg_origin
                and item.conversation_id == first.conversation_id
                and item.parent_agent_id == first.parent_agent_id
            )
        ]
        for item in batch:
            self._pending_results.pop((item.agent_id, item.turn_id), None)
        return batch

    def acknowledge(
        self,
        instances: list[SubAgentInstance] | list[SubAgentCompletion],
        parent_agent_id: str,
    ) -> None:
        """Mark results received without consuming their repeatable result records.

        Args:
            instances: Results returned by a query, a wait, or mailbox delivery.
            parent_agent_id: Parent allowed to receive the results.
        """
        for instance in instances:
            current = self._instances.get(instance.agent_id)
            if (
                current is None
                or current.parent_agent_id != parent_agent_id
                or instance.parent_agent_id != parent_agent_id
            ):
                continue
            if isinstance(instance, SubAgentInstance) and (
                current is not instance or not instance.finished.is_set()
            ):
                continue
            key = (instance.agent_id, instance.turn_id)
            self._received_results.add(key)
            self._pending_results.pop(key, None)
            if current.turn_id == instance.turn_id:
                current.result_received = True

    def receive_results(self, run_context: ContextWrapper[AstrAgentContext]) -> None:
        """Append queued results only at a runner's complete step boundary.

        Args:
            run_context: Parent context whose tool-call/result pairs are complete.
        """
        root = run_context.context
        if root.agent_id != self.parent_agent_id or not self._pending_results:
            return
        if root.event.get_extra("agent_stop_requested"):
            return
        batch = [
            item
            for item in self._pending_results.values()
            if (
                item.parent_agent_id == root.agent_id
                and item.conversation_id == root.conversation_id
                and item.unified_msg_origin == root.event.unified_msg_origin
            )
        ]
        if not batch:
            return
        run_context.messages.append(
            Message(
                role="user",
                content=(
                    "[Subagent results]\n"
                    + " ".join(
                        f"[subagent-result:{item.agent_id}:{item.turn_id}]"
                        for item in batch
                    )
                    + "\nThe following are results of your delegated tasks. "
                    "Review them and continue the original task; these are not new user requests.\n"
                    + json.dumps(
                        [item.to_dict(include_result=True) for item in batch],
                        ensure_ascii=False,
                    )
                ),
            )
        )
        self.acknowledge(batch, root.agent_id)

    def create_instance(
        self,
        *,
        agent: Agent[AstrAgentContext],
        parent_context: ContextWrapper[AstrAgentContext],
        task: str | None,
        provider_id: str | None = None,
    ) -> SubAgentInstance:
        """Snapshot a template without inheriting the parent's chat history.

        Args:
            agent: Expert template to snapshot for this execution.
            parent_context: Parent identity, session and shared resources.
            task: Task text explicitly delegated by the parent.
            provider_id: Optional chat provider override.

        Returns:
            A pending instance with its own identity and mutable context.

        Raises:
            ValueError: If the parent belongs to another task's runtime.
        """
        parent = parent_context.context
        if parent.subagent_runtime is not self:
            raise ValueError("Parent context belongs to a different subagent runtime")
        agent_id = uuid4().hex
        template = replace(
            agent,
            tools=list(agent.tools) if agent.tools is not None else None,
            begin_dialogs=copy.deepcopy(agent.begin_dialogs),
        )
        context = replace(
            parent,
            agent_id=agent_id,
            extra={},
            subagent_runtime=self,
            delegable_tools=ToolSet(),
        )
        instance = SubAgentInstance(
            agent_id=agent_id,
            parent_agent_id=parent.agent_id,
            unified_msg_origin=parent.event.unified_msg_origin,
            conversation_id=parent.conversation_id,
            agent=template,
            run_context=ContextWrapper(
                context=context,
                tool_call_timeout=parent_context.tool_call_timeout,
            ),
            task=task,
            provider_id=provider_id,
        )
        self._instances[agent_id] = instance
        return instance

    def get_instance(
        self, agent_id: str, *, parent_agent_id: str | None = None
    ) -> SubAgentInstance:
        """Find an instance in this task's registry.

        Args:
            agent_id: Identifier returned when the instance was created.
            parent_agent_id: Optional owner restriction for model-facing access.

        Returns:
            The matching instance.

        Raises:
            KeyError: If the instance does not belong to this runtime or parent.
        """
        instance = self._instances[agent_id]
        if parent_agent_id is not None and instance.parent_agent_id != parent_agent_id:
            raise KeyError(agent_id)
        return instance

    async def wait_instances(
        self,
        *,
        parent_agent_id: str,
        agent_ids: list[str],
        timeout_ms: int = 30_000,
        mode: str = "any",
    ) -> tuple[list[SubAgentInstance], bool]:
        """Wait on completion events without awaiting or cancelling worker tasks.

        Args:
            parent_agent_id: Agent allowed to inspect the requested workers.
            agent_ids: Nonempty list of worker IDs; duplicates are collapsed.
            timeout_ms: Waiting budget from zero to 60000 milliseconds.
            mode: Wait for any requested worker or all requested workers to finish.

        Returns:
            Requested instances and whether the condition remained unmet at timeout.

        Raises:
            ValueError: If parameters are invalid or an ID is unknown to the parent.
            asyncio.CancelledError: If the caller stops waiting. Workers continue.
        """
        if (
            not isinstance(agent_ids, list)
            or not agent_ids
            or any(
                not isinstance(agent_id, str) or not agent_id.strip()
                for agent_id in agent_ids
            )
        ):
            raise ValueError("agent_ids must be a nonempty list of worker IDs")
        if type(timeout_ms) is not int or not 0 <= timeout_ms <= 60_000:
            raise ValueError("timeout_ms must be an integer between 0 and 60000")
        if mode not in ("any", "all"):
            raise ValueError("mode must be 'any' or 'all'")
        try:
            instances = [
                self.get_instance(agent_id, parent_agent_id=parent_agent_id)
                for agent_id in dict.fromkeys(agent_ids)
            ]
        except KeyError as exc:
            raise ValueError(f"Unknown subagent: {exc.args[0]}") from None

        states = [instance.finished.is_set() for instance in instances]
        satisfied = any(states) if mode == "any" else all(states)
        if satisfied or timeout_ms == 0:
            return instances, not satisfied
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_ms / 1000
        while not satisfied and (remaining := deadline - loop.time()) > 0:
            waits = [
                asyncio.create_task(instance.finished.wait())
                for instance in instances
                if not instance.finished.is_set()
            ]
            try:
                await asyncio.wait(
                    waits,
                    timeout=remaining,
                    return_when=asyncio.FIRST_COMPLETED
                    if mode == "any"
                    else asyncio.ALL_COMPLETED,
                )
            finally:
                for wait in waits:
                    if not wait.done():
                        wait.cancel()
                await asyncio.gather(*waits, return_exceptions=True)
            # Completion can immediately hand off to another turn with queued input.
            states = [instance.finished.is_set() for instance in instances]
            satisfied = any(states) if mode == "any" else all(states)
        return instances, not satisfied

    def list_instances(self, parent_agent_id: str) -> list[SubAgentInstance]:
        """List the direct children of an agent in creation order.

        Args:
            parent_agent_id: Identity of the agent that created the instances.

        Returns:
            Direct children belonging to this parent task.
        """
        return [
            instance
            for instance in self._instances.values()
            if instance.parent_agent_id == parent_agent_id
        ]
