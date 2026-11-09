"""Programmatic agent inputs integrated with Core policy and output delivery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.input import (
    FileInput,
    ImageInput,
    InputComponent,
    PlainInput,
    format_input_content,
)
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentPermissions,
    AgentRuntime,
    AgentSessionRef,
    AgentTurn,
    InputReceipt,
    RuntimeEvent,
    SessionState,
    TurnResult,
)
from astrbot.core.agent_input import prepare_agent_input
from astrbot.core.agent_output import deliver_agent_turn
from astrbot.core.log import log_context
from astrbot.core.message import components as Comp
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent
from astrbot.core.platform.astr_message_event import (
    AstrMessageEvent,
    current_message_event,
    event_context,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.utils.active_event_registry import active_event_registry
from astrbot.core.utils.trace import trace_execution

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


@dataclass(frozen=True, slots=True)
class AgentSessionStatus:
    """Read-only execution state sampled from the owning runtime session."""

    ref: AgentSessionRef
    state: SessionState
    pending_turn_count: int
    active_turn_id: str | None

    @property
    def id(self) -> str:
        """Return the conversation's runtime session ID."""
        return self.ref.session_id


class AgentRun:
    """SDK view of one runtime turn, including Core-managed output completion.

    Execution, identity, scheduling and history remain on the underlying turn.
    This adapter prepares subsequent SDK inputs and waits for output delivery.
    """

    def __init__(
        self,
        service: AgentService,
        event: AgentWakeupEvent,
        send_to_user: bool,
        runtime_name: str,
        options: dict | None,
        content: Sequence[InputComponent],
    ) -> None:
        """Bind a submission to its runtime and Core output policy.

        Args:
            service: Core input and output integration services.
            event: Authorized source and target of this programmatic turn.
            send_to_user: Whether Core presents runtime output to the platform.
            runtime_name: Registered runtime selected for this submission.
            options: New-session configuration, or None when restoring a session.
            content: Explicit portable input, retained for execution-time admission.
        """
        self._service = service
        self._event = event
        self.send_to_user = send_to_user
        self._runtime_name = runtime_name
        self._options = options
        self._content = list(content)
        self._ready: asyncio.Future[AgentTurn] = (
            asyncio.get_running_loop().create_future()
        )
        self._task: asyncio.Task[TurnResult] | None = None

    @property
    def _turn(self) -> AgentTurn:
        """Return the existing runtime handle without copying execution state."""
        return self._ready.result()

    @property
    def id(self) -> str:
        """Return the runtime turn identity."""
        return self._turn.id

    @property
    def session(self) -> AgentSessionStatus:
        """Sample the owning session's execution state for the caller."""
        session = self._turn.session
        active_turn = session.active_turn
        return AgentSessionStatus(
            ref=AgentSessionRef(session.runtime_name, session.id),
            state=session.state,
            pending_turn_count=session.pending_turn_count,
            active_turn_id=active_turn.id if active_turn is not None else None,
        )

    @property
    def done(self) -> bool:
        """Whether execution and Core output handling have both finished."""
        return self._task is not None and self._task.done()

    async def result(self) -> TurnResult:
        """Wait for execution, history persistence and framework output handling.

        Returns:
            The runtime result; caller cancellation does not cancel execution.
        """
        assert self._task is not None
        try:
            return (await asyncio.shield(self._task)).model_copy(deep=True)
        except asyncio.CancelledError:
            if self._task.cancelled():
                return await self._turn.result()
            raise

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        """Observe runtime output without changing explicit message sends.

        Yields:
            Replayable runtime events, then turn.finished after any automatic
            output presentation has completed.
        """
        async for event in self._turn.events():
            if event.type == "turn.finished":
                await self.result()
                yield event
                return
            yield event

    async def cancel(self) -> None:
        """Cancel this execution and its output handler, keeping the session open."""
        await self._turn.cancel()
        if self._task is not None and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)

    async def follow_up(
        self,
        *,
        input_message: Sequence[InputComponent],
        send_to_user: bool | None = None,
    ) -> AgentRun:
        """Queue another input in this exact session through Core admission.

        Args:
            input_message: New portable content, independent of this turn.
            send_to_user: Output policy, or None to inherit this run's policy.

        Returns:
            A new SDK handle backed by a separate runtime turn.
        """
        session = self._turn.session
        if session.closed:
            raise ValueError("Agent session is closed")
        return await self._service.run_turn(
            umo=session.umo,
            input_message=input_message,
            send_to_user=self.send_to_user if send_to_user is None else send_to_user,
            source_event=self._event,
            session_id=session.id,
        )

    async def steer(
        self, *, input_message: Sequence[InputComponent]
    ) -> InputReceipt | None:
        """Prepare additional input and submit it to this exact active turn.

        Args:
            input_message: Additional content; attachments follow native steering
                semantics and are represented by their references as text.

        Returns:
            A durable-consumption receipt, or None when admission or steering
            rejects it. Await the returned receipt to confirm persistence.
        """
        if self._turn.done:
            return None
        event = self._service._make_event(
            self._turn.session.umo,
            input_message,
            self._event,
        )
        with (
            log_context(event.get_platform_id(), event.get_platform_name()),
            event_context(event),
            trace_execution(event.trace),
        ):
            input = await prepare_agent_input(
                self._service.context,
                event,
                streaming=False,
                content=list(input_message),
            )
            if input is None:
                return None
            return self._turn.steer(input)


class AgentService:
    """Core integration shared by programmatic agent callers."""

    def __init__(self, context: Context, runtimes: dict[str, AgentRuntime]) -> None:
        """Bind plugin-facing agent operations to lifecycle-owned runtime instances.

        Args:
            context: Core input preparation and platform delivery services.
            runtimes: Registry shared with execution and configuration management.
        """
        self.context = context
        self._runtimes = runtimes
        self._runs: set[AgentRun] = set()
        self._closed = False

    def register_runtime(self, name: str, runtime: AgentRuntime) -> None:
        """Register a runtime without exposing the mutable application registry.

        Args:
            name: Stable runtime name used by persisted AgentConfigs.
            runtime: Implementation responsible for its own sessions and history.

        Raises:
            RuntimeError: If the agent service is closed.
            ValueError: If the name is invalid or already registered.
            TypeError: If the implementation is not an AgentRuntime.
        """
        if self._closed:
            raise RuntimeError("Agent service is unavailable")
        if (
            not isinstance(name, str)
            or not name.strip()
            or name != name.strip()
            or name in self._runtimes
        ):
            raise ValueError(f"Agent runtime already registered or invalid: {name!r}")
        if not isinstance(runtime, AgentRuntime):
            raise TypeError("runtime must implement AgentRuntime")
        self._runtimes[name] = runtime

    def _make_event(
        self,
        umo: str,
        content: Sequence[InputComponent],
        source_event: AstrMessageEvent | None,
    ) -> AgentWakeupEvent:
        """Adapt portable input to plugin event contracts without owning execution.

        Args:
            umo: Already resolved target, including conversation isolation.
            content: Ordered immutable plain, image and file components.
            source_event: Optional trusted source of caller identity.

        Returns:
            A Core-owned programmatic event with current plugin selection.

        Raises:
            ValueError: If content, source identity or target adapter is invalid.
        """
        if not content or any(
            not isinstance(part, (PlainInput, ImageInput, FileInput))
            for part in content
        ):
            raise ValueError("input_message must contain plain, image or file inputs")
        session = MessageSession.from_str(umo)
        platform = self.context.get_platform_inst(session.platform_id)
        if platform is None:
            raise ValueError(f"Platform adapter {session.platform_id!r} not found")
        if source_event is not None and source_event.unified_msg_origin != umo:
            raise ValueError("Source event belongs to another UMO")
        permissions = (
            AgentPermissions.from_event(source_event)
            if source_event is not None
            else AgentPermissions()
        )
        event = AgentWakeupEvent(
            context=self.context,
            session=session,
            platform_meta=platform.meta(),
            prompt=format_input_content(content),
            source="plugin",
            role=permissions.role.value,
        )
        if source_event is not None:
            event.message_obj.sender.user_id = source_event.get_sender_id()
            event.message_obj.sender.nickname = source_event.get_sender_name()
            event.message_obj.self_id = source_event.get_self_id()
            event.message_obj.group_id = source_event.get_group_id()
            event.set_extra(
                "_api_key_allow_admin_role",
                source_event.get_extra("_api_key_allow_admin_role"),
            )
        event.message_obj.message = []
        for part in content:
            if isinstance(part, PlainInput):
                event.message_obj.message.append(Comp.Plain(part.text))
            elif isinstance(part, ImageInput):
                event.message_obj.message.append(
                    Comp.Image.fromFileSystem(part.path)
                    if part.path is not None
                    else Comp.Image.fromURL(part.source)
                )
            else:
                event.message_obj.message.append(
                    Comp.File(
                        name=part.text or "attachment",
                        file=part.path or "",
                        url=part.url or "",
                    )
                )
        enabled = self.context.get_config(umo=umo).get("plugin_set", ["*"])
        event.plugins_name = None if enabled == ["*"] else list(enabled)
        return event

    async def run_turn(
        self,
        *,
        umo: str,
        input_message: Sequence[InputComponent],
        send_to_user: bool = True,
        source_event: AstrMessageEvent | None = None,
        session_id: str | None = None,
    ) -> AgentRun:
        """Submit a configured runtime turn without waiting for model execution.

        Args:
            umo: Target conversation source, including existing isolation.
            input_message: Portable plain, image and file content.
            send_to_user: Automatically present runtime output to the target
                conversation. Explicit tool and plugin sends are unaffected.
                History is saved regardless of this setting.
            source_event: Caller identity; defaults to the active same-UMO event.
            session_id: Bind an exact conversation, or select the current one.

        Returns:
            An SDK view of the runtime turn with independent output observation.

        Raises:
            RuntimeError: If the service or selected runtime is unavailable.
            ValueError: If input or the explicit session target is invalid.
        """
        if self._closed:
            raise RuntimeError("Agent service is unavailable")
        if source_event is None:
            current = current_message_event.get()
            if (
                current is not None
                and current._execution_active
                and current.unified_msg_origin == umo
            ):
                source_event = current
        config = self.context.get_config(umo=umo).get("agent", {})
        target = (
            source_event.agent_session
            if isinstance(source_event, AgentWakeupEvent)
            else None
        )
        if (
            target is not None
            and session_id is not None
            and target.session_id == session_id
        ):
            runtime_name = target.runtime
        else:
            runtime_name = config.get("runtime", "astrbot")
        if runtime_name not in self._runtimes:
            raise RuntimeError(f"Agent runtime unavailable: {runtime_name}")
        options = (
            {"config": deepcopy(config.get("config", {}))}
            if session_id is None
            else None
        )
        content = tuple(input_message)
        event = self._make_event(umo, content, source_event)
        run = AgentRun(self, event, send_to_user, runtime_name, options, content)
        self._runs.add(run)
        run._task = asyncio.create_task(self._execute(run, session_id))

        def completed(task: asyncio.Task[TurnResult]) -> None:
            """Release ownership and settle submissions cancelled before startup.

            Args:
                task: Completed Core scope and output task.
            """
            self._runs.discard(run)
            if task.cancelled():
                if not run._ready.done():
                    run._ready.cancel()
            elif (error := task.exception()) is not None:
                logger.error("Programmatic agent output failed: %s", error)

        run._task.add_done_callback(completed)
        try:
            await asyncio.shield(run._ready)
        except BaseException:
            run._task.cancel()
            await asyncio.gather(run._task, return_exceptions=True)
            raise
        return run

    async def _execute(self, run: AgentRun, session_id: str | None) -> TurnResult:
        """Own Core scopes while the runtime drives and persists its turn.

        Args:
            run: SDK adapter receiving the actual runtime handle.
            session_id: Optional exact target, retained by subsequent inputs.

        Returns:
            The settled runtime result after framework presentation.
        """
        event = run._event
        turn = None

        try:
            with (
                log_context(event.get_platform_id(), event.get_platform_name()),
                event_context(event),
                trace_execution(event.trace),
            ):
                input = AgentInput(
                    event=event,
                    permissions=AgentPermissions.from_event(event),
                    content=run._content,
                    streaming=False,
                )

                async def admit() -> bool:
                    """Resolve current Core policy after this queued turn acquires its lock.

                    Returns:
                        Whether the runtime may prepare and execute this input.
                    """
                    prepared = await prepare_agent_input(
                        self.context, event, streaming=False, content=run._content
                    )
                    if prepared is None:
                        return False
                    input.content = prepared.content
                    input.permissions = prepared.permissions
                    input.plugin_tools = prepared.plugin_tools
                    input.plugin_skills = prepared.plugin_skills
                    return True

                runtime = self._runtimes.get(run._runtime_name)
                if runtime is None:
                    raise RuntimeError(
                        f"Agent runtime unavailable: {run._runtime_name}"
                    )
                session = await runtime.open_session(
                    event.unified_msg_origin,
                    session_id=session_id,
                    input=input,
                    options=run._options,
                )
                session.runtime_name = run._runtime_name
                event.agent_session = AgentSessionRef(run._runtime_name, session.id)
                turn = await session.run_turn(input, admit=admit)
                active_event_registry.register_agent_stop_callback(
                    event, turn.request_stop
                )
                run._ready.set_result(turn)
                if run.send_to_user:
                    try:
                        await deliver_agent_turn(self.context, turn)
                    except Exception:
                        # Presentation failure does not rewrite an executing runtime's outcome.
                        await turn.result()
                        raise
                return await turn.result()
        except BaseException as exc:
            if not run._ready.done():
                run._ready.set_exception(exc)
            raise
        finally:
            if turn is not None:
                active_event_registry.unregister_agent_stop_callback(
                    event, turn.request_stop
                )
                if not turn.done:
                    await turn.cancel()
            self._runs.discard(run)

    async def close(self) -> None:
        """Stop accepted SDK calls and output handlers before host shutdown."""
        self._closed = True
        tasks = [run._task for run in self._runs if run._task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
