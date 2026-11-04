"""Programmatic agent inputs integrated with Core policy and output delivery."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import replace
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
    AgentPermissions,
    AgentRuntime,
    AgentSession,
    AgentSessionRef,
    AgentTurn,
    InputReceipt,
    RuntimeEvent,
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
from astrbot.core.utils.trace import trace_execution

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class AgentRun:
    """SDK view of one runtime turn, including Core-managed output completion.

    Execution, identity, scheduling and history remain on the underlying turn.
    This adapter prepares subsequent SDK inputs and waits for output delivery.
    """

    def __init__(
        self, service: AgentService, event: AgentWakeupEvent, send_to_user: bool
    ) -> None:
        self._service = service
        self._event = event
        self.send_to_user = send_to_user
        self._ready: asyncio.Future[AgentTurn] = (
            asyncio.get_running_loop().create_future()
        )
        self._task: asyncio.Task[TurnResult] | None = None

    @property
    def runtime_turn(self) -> AgentTurn:
        """Return the existing runtime handle without copying execution state."""
        return self._ready.result()

    @property
    def id(self) -> str:
        """Return the runtime turn identity."""
        return self.runtime_turn.id

    @property
    def session(self) -> AgentSession:
        """Return the owning session, including its read-only execution state."""
        return self.runtime_turn.session

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
            return await asyncio.shield(self._task)
        except asyncio.CancelledError:
            if self._task.cancelled():
                return await self.runtime_turn.result()
            raise

    async def events(self) -> AsyncIterator[RuntimeEvent]:
        """Observe runtime output without changing explicit message sends.

        Yields:
            Replayable runtime events, then turn_finished after any automatic
            output presentation has completed.
        """
        async for event in self.runtime_turn.events():
            if event.type == "turn_finished":
                break
            yield event
        result = await self.result()
        yield RuntimeEvent(self.id, "turn_finished", result)

    async def cancel(self) -> None:
        """Cancel this execution and its output handler, keeping the session open."""
        await self.runtime_turn.cancel()
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
        if self.session.closed:
            raise ValueError("Agent session is closed")
        return await self._service.run_turn(
            umo=self.session.umo,
            input_message=input_message,
            send_to_user=self.send_to_user if send_to_user is None else send_to_user,
            source_event=self._event,
            permissions=self.runtime_turn.input.permissions,
            session_id=self.session.id,
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
        if self.runtime_turn.done:
            return None
        event = self._service._make_event(
            self.session.umo,
            input_message,
            self._event,
            self.runtime_turn.input.permissions,
        )
        from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildConfig

        config = MainAgentBuildConfig.from_config(
            self._service.context.get_config(umo=self.session.umo)
        )
        with (
            log_context(event.get_platform_id(), event.get_platform_name()),
            event_context(event),
            trace_execution(event.trace),
        ):
            input = await prepare_agent_input(
                self._service.context,
                event,
                config,
                content=list(input_message),
            )
            if input is None:
                return None
            return self.runtime_turn.steer(input)


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
        permissions: AgentPermissions | None,
    ) -> AgentWakeupEvent:
        """Adapt portable input to plugin event contracts without owning execution.

        Args:
            umo: Already resolved target, including conversation isolation.
            content: Ordered immutable plain, image and file components.
            source_event: Optional trusted source of caller identity.
            permissions: Explicit input authorization, or inherited/member rights.

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
        permissions = permissions or (
            AgentPermissions.from_event(source_event)
            if source_event is not None
            else AgentPermissions()
        )
        if (
            source_event is not None
            and source_event.get_extra("_api_key_allow_admin_role") is False
            and permissions.is_admin
        ):
            permissions = AgentPermissions()
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
        permissions: AgentPermissions | None = None,
        session_id: str | None = None,
    ) -> AgentRun:
        """Submit a built-in agent turn without waiting for model execution.

        Args:
            umo: Target conversation source, including existing isolation.
            input_message: Portable plain, image and file content.
            send_to_user: Automatically present runtime output to the target
                conversation. Explicit tool and plugin sends are unaffected.
                History is saved regardless of this setting.
            source_event: Caller identity; defaults to the active same-UMO event.
            permissions: Explicit authorization; defaults to source/member rights.
            session_id: Bind an exact conversation, or select the current one.

        Returns:
            An SDK view of the runtime turn with independent output observation.

        Raises:
            RuntimeError: If the service or built-in runtime is unavailable.
            ValueError: If input is invalid or the session uses a foreign runner.
        """
        if self._closed or "astrbot" not in self._runtimes:
            raise RuntimeError("Agent service is unavailable")
        config = self.context.get_config(umo=umo)
        if config.get("agent", {}).get("runtime", "astrbot") != "astrbot":
            raise ValueError("ctx.agent currently supports the built-in runtime only")
        if source_event is None:
            current = current_message_event.get()
            if (
                current is not None
                and current._execution_active
                and current.unified_msg_origin == umo
            ):
                source_event = current
        content = tuple(input_message)
        event = self._make_event(umo, content, source_event, permissions)
        run = AgentRun(self, event, send_to_user)
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
        from astrbot.core.astr_agent_runtime.main_agent import MainAgentBuildConfig
        from astrbot.core.astr_agent_runtime.main_session import MainAgentInput

        event = run._event
        turn = None

        try:
            with (
                log_context(event.get_platform_id(), event.get_platform_name()),
                event_context(event),
                trace_execution(event.trace),
            ):
                input = MainAgentInput(
                    event=event, permissions=AgentPermissions.from_event(event)
                )

                async def admit() -> bool:
                    """Resolve current Core policy after this queued turn acquires its lock.

                    Returns:
                        Whether the runtime may prepare and execute this input.
                    """
                    enabled = self.context.get_config(umo=event.unified_msg_origin).get(
                        "plugin_set", ["*"]
                    )
                    event.plugins_name = None if enabled == ["*"] else list(enabled)
                    config = MainAgentBuildConfig.from_config(
                        self.context.get_config(umo=event.unified_msg_origin)
                    )
                    prepared = await prepare_agent_input(
                        self.context,
                        event,
                        replace(
                            config,
                            streaming_response=False,
                            call_request_hook=True,
                            validate_provider_endpoint=True,
                        ),
                    )
                    if prepared is None:
                        return False
                    input.permissions = prepared.permissions
                    input.plugin_tools = prepared.plugin_tools
                    input.plugin_skills = prepared.plugin_skills
                    input.build_config = prepared.build_config
                    return True

                input.admit = admit
                runtime = self._runtimes.get("astrbot")
                if runtime is None:
                    raise RuntimeError("Built-in agent runtime is unavailable")
                session = await runtime.open_session(
                    event.unified_msg_origin, session_id=session_id, input=input
                )
                event.agent_session = AgentSessionRef("astrbot", session.id)
                turn = await session.run_turn(input)
                run._ready.set_result(turn)
                if run.send_to_user:
                    await deliver_agent_turn(self.context, turn)
                return await turn.result()
        except BaseException as exc:
            if not run._ready.done():
                run._ready.set_exception(exc)
            raise
        finally:
            if turn is not None and not turn.done:
                await turn.cancel()
            self._runs.discard(run)

    async def close(self) -> None:
        """Stop accepted SDK calls and output handlers before host shutdown."""
        self._closed = True
        tasks = [run._task for run in self._runs if run._task is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
