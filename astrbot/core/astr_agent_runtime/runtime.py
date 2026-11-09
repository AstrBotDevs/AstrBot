"""Own all built-in sessions; Core never owns their runners or history writes."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.runtime import AgentInput, AgentRuntime, AgentSession, AgentTurn
from astrbot.core.astr_agent_runtime.main_agent.request import _get_session_conv
from astrbot.core.platform.agent_wakeup_event import AgentWakeupEvent

from .delegated_session import DelegatedAgentInput, DelegatedAgentSession
from .main_session import MainAgentSession

if TYPE_CHECKING:
    from astrbot.core.agent.config_store import AgentConfigStore
    from astrbot.core.astr_agent_runtime.subagents.context import SubAgentContext
    from astrbot.core.astr_agent_runtime.subagents.service import SubAgentService
    from astrbot.core.star.context import Context


class AstrAgentRuntime(AgentRuntime):
    """AstrBot host services around native main and delegated execution."""

    def __init__(
        self,
        context: Context,
        *,
        agent_configs: AgentConfigStore,
        subagents: SubAgentService,
    ) -> None:
        """Bind native execution to explicit configuration and delegation services.

        Args:
            context: Host provider, plugin, platform and conversation services.
            agent_configs: Shared storage for reusable agent configurations.
            subagents: Delegation scheduler sharing the application's runtime registry.
        """
        self.context = context
        self.agent_configs = agent_configs
        self.subagents = subagents
        self._sessions: dict[tuple[str, str], AgentSession] = {}
        self._opening = asyncio.Lock()
        self._active_main: dict[str, AgentTurn] = {}
        self._closed = False

    def normalize_config(self, config: dict, *, delegated: bool = False) -> dict:
        """Validate native options and apply role-appropriate defaults.

        Args:
            config: Native model, persona, execution and delegation options.
            delegated: Whether to retain only reusable persona/model overrides.

        Returns:
            Validated native configuration.
        """
        from astrbot.core.config.agent import normalize_agent

        return normalize_agent(
            {"runtime": "astrbot", "config": config}, delegated=delegated
        )["config"]

    def referenced_config_ids(self, config: dict) -> list[str]:
        """Return configured delegation targets, including disabled selections.

        Args:
            config: Native runtime configuration.

        Returns:
            Stable agent_config IDs referenced by this configuration.
        """
        return list(config.get("subagents", {}).get("config_ids", []))

    async def spawn_agent(
        self,
        context: SubAgentContext,
        messages: list[dict],
        *,
        config_id: str | None = None,
        name: str | None = None,
    ) -> dict:
        """Resolve this runtime's delegation policy before opening another agent.

        Args:
            context: Bound native parent execution and authorized capabilities.
            messages: Explicit structured task input.
            config_id: Optional reusable agent selected by the parent.
            name: Optional session display name.

        Returns:
            Public session identity and initial execution state.

        Raises:
            ValueError: If delegation, the agent_config, or its runtime is unavailable.
        """
        config = (
            self.context.get_config(umo=context.event.unified_msg_origin)
            .get("agent", {})
            .get("config", {})
        )
        policy = config.get("subagents", {})
        if not policy.get("enabled", False):
            raise ValueError("Subagents are disabled for this configuration profile")
        selected_runtime = "astrbot"
        selected_config = self.normalize_config({}, delegated=True)
        if config_id is not None:
            if config_id not in policy.get("config_ids", []):
                raise ValueError(
                    f"Agent configuration is not selected by this profile: {config_id}"
                )
            agent_config = await self.agent_configs.get(config_id)
            if not agent_config.enabled:
                raise ValueError(f"Agent configuration is disabled: {config_id}")
            selected_runtime, selected_config = (
                agent_config.runtime,
                agent_config.config,
            )
            name = name or agent_config.name
        runtime = self.subagents.runtimes.get(selected_runtime)
        if runtime is None:
            raise ValueError(f"Agent runtime unavailable: {selected_runtime}")
        selected_config = runtime.normalize_config(selected_config, delegated=True)
        return await self.subagents.spawn(
            context,
            messages,
            runtime=selected_runtime,
            config=selected_config,
            config_id=config_id,
            name=name,
        )

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
        profile = (options or {}).get("profile", "main")
        if session_id is not None and "profile" not in (options or {}):
            if ("subagent", session_id) in self._sessions:
                profile = "subagent"
            else:
                conversation = await self.context.conversation_manager.get_conversation(
                    umo, session_id
                )
                if conversation is None or conversation.cid != session_id:
                    profile = "subagent"
        if profile == "subagent":
            async with self._opening:
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                if session_id is not None:
                    session = self._sessions.get((profile, session_id))
                    if session is None or session.closed:
                        if session is not None:
                            await session.close()
                        session = await DelegatedAgentSession.restore(
                            self, umo, session_id
                        )
                else:
                    if not isinstance(input, DelegatedAgentInput):
                        raise ValueError(
                            "Creating a child requires delegated caller input"
                        )
                    session = await DelegatedAgentSession.create(
                        self, umo, input, options or {}
                    )
                if self._closed:
                    await session.close()
                    raise ValueError(
                        "AstrBot agent runtime closed during session creation"
                    )
                if session.umo != umo:
                    raise ValueError("Agent session belongs to another UMO")
                self._sessions[(profile, session.id)] = session
                return session
        if profile != "main":
            raise ValueError(f"Unknown built-in agent session profile: {profile}")
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
            session = self._sessions.get((profile, session_id))
            if session is None or session.closed:
                if session is not None:
                    await session.close()
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session = MainAgentSession(self, session_id, umo)
                self._sessions[(profile, session_id)] = session
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
