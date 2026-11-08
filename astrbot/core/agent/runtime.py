"""Session and turn contracts shared by agent runtime implementations."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable, Generator
from contextlib import AbstractAsyncContextManager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from astrbot import logger
from astrbot.core.agent.input import InputComponent

from .events import (
    AgentSessionRef,
    RuntimeErrorInfo,
    RuntimeEvent,
    RuntimeEventPayload,
    RuntimeExecutionError,
    TurnFinished,
    TurnResult,
    TurnStarted,
    TurnStatus,
    UsageUpdated,
)

if TYPE_CHECKING:
    from astrbot.core.agent.run_context import ContextWrapper
    from astrbot.core.agent.tool import ToolSet
    from astrbot.core.astr_agent_context import AstrAgentContext
    from astrbot.core.platform.astr_message_event import AstrMessageEvent
    from astrbot.core.skills.skill_manager import SkillInfo


class AgentRole(str, Enum):
    """The currently supported caller roles."""

    MEMBER = "member"
    ADMIN = "admin"


@dataclass(frozen=True)
class AgentPermissions:
    """Trusted authorization supplied for one input, never shared across callers."""

    role: AgentRole = AgentRole.MEMBER

    @classmethod
    def from_event(cls, event: AstrMessageEvent) -> AgentPermissions:
        """Capture the effective role without allowing an API-key privilege upgrade.

        Args:
            event: Event after Core has resolved caller permissions.

        Returns:
            An immutable authorization value for this input.
        """
        admin = (
            getattr(event, "role", "member") == "admin"
            and getattr(event, "get_extra", lambda key: None)(
                "_api_key_allow_admin_role"
            )
            is not False
        )
        return cls(AgentRole.ADMIN if admin else AgentRole.MEMBER)

    @property
    def is_admin(self) -> bool:
        """Whether this input is authorized as an AstrBot administrator."""
        return self.role == AgentRole.ADMIN


def get_agent_permissions(
    context: ContextWrapper[AstrAgentContext],
) -> AgentPermissions:
    """Resolve input authorization for native and legacy SDK tool contexts.

    Args:
        context: Tool ContextWrapper, with optional captured runtime permissions.

    Returns:
        Explicit input permissions, or the effective event role for legacy callers.
    """
    owner = context.context
    permissions = getattr(owner, "permissions", None)
    if isinstance(permissions, AgentPermissions):
        return permissions
    return AgentPermissions.from_event(owner.event)


class SessionState(str, Enum):
    """Observable execution state of a runtime-owned session."""

    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    CLOSED = "closed"


@dataclass
class AgentInput:
    """An input with Core authorization, independent of native model requests.

    Args:
        event: Source identity and existing plugin-hook context.
        permissions: Caller authorization for this input.
        content: Explicit portable content, or None to use the source event.
        plugin_tools: Authorized plugin tool contributions before runtime filtering.
        plugin_skills: Authorized plugin skill contributions before runtime filtering.
        streaming: Requested output mode, or None to use the runtime default.
    """

    event: AstrMessageEvent
    permissions: AgentPermissions
    content: list[InputComponent] | None = None
    plugin_tools: ToolSet | None = None
    plugin_skills: list[SkillInfo] | None = None
    streaming: bool | None = None


class InputReceipt:
    """Cancellation-safe acknowledgment of input consumed at a durable boundary."""

    def __init__(self) -> None:
        self._future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    def __await__(self) -> Generator[Any, None, bool]:
        return asyncio.shield(self._future).__await__()

    def done(self) -> bool:
        """Whether consumption or rejection has been confirmed."""
        return self._future.done()

    def resolve(self, consumed: bool) -> None:
        """Acknowledge consumption after persistence, or release input for retry.

        Args:
            consumed: Whether the owning runtime has committed this input.
        """
        if not self._future.done():
            self._future.set_result(consumed)


class AgentTurn:
    """A handle onto one execution; consuming output never drives execution.

    The session owns scheduling. This handle owns a replayable event journal and
    references its single execution task. Multiple readers cannot steal events
    from each other, and result() also works without any events() subscriber.
    """

    def __init__(self, session: AgentSession, input: AgentInput) -> None:
        self.id = uuid4().hex
        self.session = session
        self.input = input
        self._events: list[RuntimeEvent] = []
        self._changed = asyncio.Event()
        self._task: asyncio.Task[TurnResult] | None = None
        self._stop_task: asyncio.Task[None] | None = None
        self._execution_started = False
        self._cancel_requested = False

    @property
    def done(self) -> bool:
        """Whether this turn has settled, including its persistence boundary."""
        return self._task is not None and self._task.done()

    @property
    def cancellation_requested(self) -> bool:
        """Whether the owner cancelled this turn, distinct from an agent stop."""
        return self._cancel_requested

    def emit(self, payload: RuntimeEventPayload) -> None:
        """Publish a detached fact without giving observers execution ownership.

        Args:
            payload: Standard event data; mutable JSON is copied before retention.

        Raises:
            RuntimeError: If execution has already published its terminal event.
        """
        if self._events and self._events[-1].type == "turn.finished":
            raise RuntimeError("Cannot publish after turn.finished")
        self._events.append(
            RuntimeEvent(
                event_id=str(uuid4()),
                session=AgentSessionRef(self.session.runtime_name, self.session.id),
                turn_id=self.id,
                created_at=datetime.now(timezone.utc),
                payload=payload.model_copy(deep=True),
            )
        )
        self._changed.set()

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        """Read this turn's ordered events, including already published events.

        Yields:
            Events through the terminal turn.finished event.
        """
        position = 0
        while True:
            self._changed.clear()
            while position < len(self._events):
                event = self._events[position]
                position += 1
                yield event.model_copy(deep=True)
                if event.type == "turn.finished":
                    return
            await self._changed.wait()

    async def result(self) -> TurnResult:
        """Wait for this turn without propagating a waiter's cancellation into it.

        Returns:
            The terminal result of this execution only.
        """
        if self._task is None:
            raise RuntimeError("Turn has not been scheduled")
        try:
            return (await asyncio.shield(self._task)).model_copy(deep=True)
        except asyncio.CancelledError:
            if self._task.cancelled():
                return TurnResult(status=TurnStatus.CANCELLED, reason="cancelled")
            raise

    def request_stop(self) -> None:
        """Request a stop once, allowing active execution to settle its history."""
        if self.done or self._cancel_requested or self._stop_task is not None:
            return
        if not self._execution_started:
            # Queued turns and admission checks have no runtime work to stop.
            self._cancel_requested = True
            if self._task is not None:
                self._task.cancel()
            return

        async def stop() -> None:
            if self.done or self._cancel_requested:
                return
            try:
                if await self.session.request_stop_turn(self):
                    return
            except Exception:
                logger.exception(
                    "Unable to request a graceful stop for turn %s", self.id
                )
            try:
                await self.cancel()
            except Exception:
                logger.exception(
                    "Unable to cancel turn %s after a stop request", self.id
                )

        self._stop_task = asyncio.create_task(stop())

    async def cancel(self) -> None:
        """Cancel this turn while leaving its session and other turns reusable."""
        if self.done:
            return
        if not self._cancel_requested:
            self._cancel_requested = True
            try:
                await self.session.cancel_turn(self)
            finally:
                if self._task is not None:
                    self._task.cancel()
        if self._task is not None:
            await asyncio.gather(asyncio.shield(self._task), return_exceptions=True)

    async def follow_up(self, input: AgentInput) -> AgentTurn:
        """Queue a separate turn through this handle's owning session.

        Args:
            input: New input carrying its own permissions and plugin capabilities.

        Returns:
            A separate handle; this turn's completion does not wait for it.
        """
        return await self.session.run_turn(input)

    def steer(self, input: AgentInput) -> InputReceipt | None:
        """Submit steering to this exact active turn at a safe execution boundary.

        Args:
            input: Additional input with independently resolved authorization.

        Returns:
            A receipt confirming durable consumption, or None when not accepted.
        """
        if (
            self.done
            or self._cancel_requested
            or self._stop_task is not None
            or self.session.active_turn is not self
        ):
            return None
        original = self.input
        if (
            input.event.unified_msg_origin != self.session.umo
            or not input.event.get_sender_id()
            or input.event.get_sender_id() != original.event.get_sender_id()
            or input.permissions != original.permissions
            or input.event.plugins_name != original.event.plugins_name
        ):
            return None
        return self.session.steer_turn(self, input)


class AgentSession(ABC):
    """One runtime-owned conversation with a single serial execution chain."""

    runtime_name: str = "astrbot"

    def __init__(
        self, session_id: str, umo: str, *, runtime_name: str = "astrbot"
    ) -> None:
        self.runtime_name = runtime_name
        self.id = session_id
        self.umo = umo
        self.active_turn: AgentTurn | None = None
        self._turns: set[AgentTurn] = set()
        self._execution_lock = asyncio.Lock()
        self._closed = False
        self._close_waiter: asyncio.Future[list[None]] | None = None

    @property
    def closed(self) -> bool:
        """Whether new input requires opening a fresh live session handle."""
        return self._closed

    @property
    def pending_turn_count(self) -> int:
        """Count accepted turns waiting to become active, excluding settled turns."""
        return sum(
            turn is not self.active_turn and not turn.done for turn in self._turns
        )

    @property
    def state(self) -> SessionState:
        """Describe execution without requiring callers to inspect private tasks."""
        if self.closed:
            return SessionState.CLOSED
        if self.active_turn is not None:
            return SessionState.RUNNING
        if self.pending_turn_count:
            return SessionState.QUEUED
        return SessionState.IDLE

    async def run_turn(
        self,
        input: AgentInput,
        *,
        admit: Callable[[], Awaitable[bool]] | None = None,
    ) -> AgentTurn:
        """Accept an independent turn, queuing behind earlier accepted turns.

        Args:
            input: Input and caller capabilities belonging to this turn.
            admit: Core admission check, run after acquiring execution guards.

        Returns:
            A scheduled turn handle without waiting for model execution.

        Raises:
            ValueError: If this session is closed or the event belongs elsewhere.
        """
        if self._closed:
            raise ValueError("Agent session is closed")
        if input.event.unified_msg_origin != self.umo:
            raise ValueError("Agent input belongs to another UMO")
        turn = AgentTurn(self, input)
        self._turns.add(turn)

        async def execute() -> TurnResult:
            result = TurnResult(status=TurnStatus.CANCELLED, reason="cancelled")
            try:
                async with self._execution_lock:
                    self.active_turn = turn
                    turn.emit(TurnStarted())
                    async with self._execution_scope():
                        if admit is not None and not await admit():
                            result = TurnResult(reason="skipped")
                        else:
                            turn._execution_started = True
                            result = await self.execute_turn(turn)
            except asyncio.CancelledError as exc:
                result = TurnResult(
                    status=TurnStatus.CANCELLED,
                    reason="cancelled",
                    error=RuntimeErrorInfo(
                        code="cancelled", message=str(exc) or "Agent turn cancelled"
                    ),
                )
            except Exception as exc:
                logger.exception("Agent turn %s failed in session %s", turn.id, self.id)
                result = TurnResult(
                    status=TurnStatus.FAILED,
                    error=RuntimeErrorInfo(
                        code=exc.code
                        if isinstance(exc, RuntimeExecutionError)
                        else "execution_failed",
                        message=str(exc) or type(exc).__name__,
                    ),
                    reason="error",
                )
            finally:
                if result.usage.source == "unknown":
                    for event in reversed(turn._events):
                        if isinstance(event.payload, UsageUpdated):
                            result = result.model_copy(
                                update={
                                    "usage": event.payload.usage,
                                    "metrics": event.payload.metrics,
                                },
                                deep=True,
                            )
                            break
                if self.active_turn is turn:
                    self.active_turn = None
                turn.emit(TurnFinished(result=result))
                self._turns.discard(turn)
            return result

        task = asyncio.create_task(execute())
        turn._task = task

        def completed(done: asyncio.Task[TurnResult]) -> None:
            # A task cancelled before coroutine entry cannot run its finally.
            if done.cancelled():
                turn.emit(
                    TurnFinished(
                        result=TurnResult(
                            status=TurnStatus.CANCELLED, reason="cancelled"
                        )
                    )
                )
                self._turns.discard(turn)

        task.add_done_callback(completed)
        return turn

    def _execution_scope(self) -> AbstractAsyncContextManager[object]:
        """Acquire implementation-owned guards before Core's queued admission.

        Returns:
            Additional serialization scope, empty for independently owned sessions.
        """
        return nullcontext()

    @abstractmethod
    async def execute_turn(self, turn: AgentTurn) -> TurnResult:
        """Execute after earlier turns have settled, including history updates.

        Args:
            turn: The single active turn and its output sink.

        Returns:
            Final output after hooks and persistence have settled.
        """

    async def cancel_turn(self, turn: AgentTurn) -> None:
        """Request implementation-specific cancellation before cancelling its task.

        Args:
            turn: Exact execution to stop, possibly still queued.
        """

    async def request_stop_turn(self, turn: AgentTurn) -> bool:
        """Ask the runtime to stop an active execution and handle its own cleanup.

        Args:
            turn: Exact active turn to stop.

        Returns:
            True if the runtime accepted the request and will settle the turn.
            False to fall back to cancellation.
        """
        return False

    def steer_turn(self, turn: AgentTurn, input: AgentInput) -> InputReceipt | None:
        """Optionally append to an active execution without changing its identity.

        Args:
            turn: Exact active turn receiving steering.
            input: Additional authorized input.

        Returns:
            A durable-consumption receipt, or None when steering is unsupported.
        """
        return None

    @abstractmethod
    async def history(self) -> list[dict]:
        """Read displayable history without exposing mutable execution contexts.

        Returns:
            A detached snapshot of the committed conversation.
        """

    async def wait_for_idle(self) -> None:
        """Wait for the session's currently accepted work, not for future input."""
        while self._turns:
            await asyncio.gather(*(turn.result() for turn in list(self._turns)))

    async def close(self) -> None:
        """Stop accepted turns and release activity without deleting history."""
        if self._close_waiter is None:
            self._closed = True
            self._close_waiter = asyncio.gather(
                *(turn.cancel() for turn in list(self._turns))
            )
        await asyncio.shield(self._close_waiter)


class AgentRuntime(ABC):
    """Host integration boundary; implementations own sessions and history."""

    def normalize_config(self, config: dict, *, delegated: bool = False) -> dict:
        """Validate runtime-owned configuration without interpreting its fields.

        Args:
            config: JSON configuration supplied by a profile or stored agent_config.
            delegated: Whether defaults should suit a reusable worker.

        Returns:
            A detached validated configuration.
        """
        from copy import deepcopy

        return deepcopy(config)

    def referenced_config_ids(self, config: dict) -> list[str]:
        """Report reusable configurations referenced by runtime-owned configuration.

        Args:
            config: This runtime's configuration.

        Returns:
            Referenced persistent IDs, empty for runtimes without delegation.
        """
        return []

    def active_turn(self, umo: str) -> AgentTurn | None:
        """Optionally locate the active main turn without opening a session.

        Args:
            umo: Core-selected conversation source.

        Returns:
            An active main turn, or None when discovery is unsupported or idle.
        """
        return None

    @abstractmethod
    async def open_session(
        self,
        umo: str,
        *,
        session_id: str | None = None,
        options: dict | None = None,
        input: AgentInput | None = None,
    ) -> AgentSession:
        """Create or restore a session with implementation-specific configuration.

        Args:
            umo: Conversation source selected by Core.
            session_id: Exact persisted session to restore, or None to select/create.
            options: Runtime-owned session configuration, independent of input.
            input: Optional initial caller capabilities needed during creation.

        Returns:
            The uniquely owned live session for this runtime identity.
        """

    @abstractmethod
    async def close(self) -> None:
        """Stop owned sessions and release runtime resources."""
