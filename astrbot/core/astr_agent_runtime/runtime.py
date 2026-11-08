"""Own all built-in sessions; Core never owns their runners or history writes."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.runtime import AgentInput, AgentRuntime, AgentSession, AgentTurn
from astrbot.core.astr_agent_runtime.main_agent.request import _get_session_conv
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent

from .main_session import MainAgentSession

if TYPE_CHECKING:
    from astrbot.core.star.context import Context


class AstrAgentRuntime(AgentRuntime):
    """AstrBot host services around native main execution."""

    def __init__(
        self,
        context: Context,
    ) -> None:
        """Bind native execution to explicit host services.

        Args:
            context: Host provider, plugin, platform and conversation services.
        """
        self.context = context
        self._sessions: dict[str, AgentSession] = {}
        self._opening = asyncio.Lock()
        self._active_main: dict[str, AgentTurn] = {}
        self._closed = False

    async def initialize(self) -> None:
        """Initialize native execution environments before plugins can use them."""
        if sys.platform == "win32" and any(
            config.get("provider_settings", {}).get("computer_use_runtime") == "local"
            for config in self.context.astrbot_config_mgr.confs.values()
        ):
            try:
                from .computer.process_sandbox.windows_setup import (
                    initialize_windows_sandbox,
                )

                await asyncio.to_thread(initialize_windows_sandbox)
            except Exception as exc:
                logger.warning(f"Windows Local sandbox is unavailable: {exc}")

    async def open_session(
        self,
        umo: str,
        *,
        session_id: str | None = None,
        options: dict | None = None,
        input: AgentInput | None = None,
    ) -> AgentSession:
        """Bind the current main conversation or restore an exact identity.

        Args:
            umo: Source selected by Core.
            session_id: Exact conversation to restore, or None for current main.
            options: Runtime-specific session options.
            input: Initial event used only to create a missing main conversation.

        Returns:
            The sole live owner of the requested native conversation.

        Raises:
            ValueError: If the runtime is closed, the session is missing, or ownership differs.
        """
        if self._closed:
            raise ValueError("AstrBot agent runtime is closed")
        if input is not None and isinstance(input.event, AgentWakeupEvent):
            target = input.event.agent_session
            if target is not None:
                if session_id is not None and session_id != target.session_id:
                    raise ValueError("Wakeup and runtime session targets differ")
                session_id = target.session_id
        async with self._opening:
            if self._closed:
                raise ValueError("AstrBot agent runtime is closed")
            if session_id is None:
                if input is None:
                    session_id = await self.context.conversation_manager.get_curr_conversation_id(
                        umo
                    )
                    if session_id is None:
                        session_id = (
                            await self.context.conversation_manager.new_conversation(
                                umo
                            )
                        )
                else:
                    request = input.event.get_extra("provider_request")
                    if request is not None and request.conversation is not None:
                        session_id = request.conversation.cid
                    else:
                        conversation = await _get_session_conv(
                            input.event, self.context
                        )
                        session_id = conversation.cid
            if session_id is None:
                raise ValueError("Unable to resolve the main agent conversation")
            conversation = await self.context.conversation_manager.get_conversation(
                umo, session_id
            )
            if self._closed:
                raise ValueError("AstrBot agent runtime closed during session creation")
            if conversation is None or conversation.user_id != umo:
                raise ValueError(
                    "Agent conversation is missing or belongs to another UMO"
                )
            session = self._sessions.get(session_id)
            if session is None or session.closed:
                if session is not None:
                    await session.close()
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session = MainAgentSession(self, session_id, umo)
                self._sessions[session_id] = session
            elif session.umo != umo:
                raise ValueError("Agent session belongs to another UMO")
            return session

    def active_turn(self, umo: str) -> AgentTurn | None:
        """Find main's active execution without exposing its native runner.

        Args:
            umo: Source of an arriving message or wakeup.

        Returns:
            The current turn handle, or None while no main turn can accept steering.
        """
        return self._active_main.get(umo)

    async def close(self) -> None:
        """Stop all sessions before releasing the runtime's host services."""
        from .computer.computer_client import shutdown_local_booter

        self._closed = True
        async with self._opening:
            sessions = list(self._sessions.values())
        try:
            await asyncio.gather(*(session.close() for session in sessions))
        finally:
            self._sessions.clear()
            await shutdown_local_booter()
