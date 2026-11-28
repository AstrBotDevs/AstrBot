"""Own all built-in sessions; Core never owns their runners or history writes."""

from __future__ import annotations

import asyncio
import sys
from collections import OrderedDict
from typing import TYPE_CHECKING
from weakref import WeakSet, WeakValueDictionary

from astrbot import logger
from astrbot.core.agent.runtime import (
    AgentInput,
    AgentRuntime,
    AgentSession,
    AgentTurn,
    SessionState,
)
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

    MAX_IDLE_SESSIONS: int = 256

    def __init__(
        self,
        context: Context,
        *,
        agent_configs: AgentConfigStore,
        subagents: SubAgentService,
        max_idle_sessions: int = MAX_IDLE_SESSIONS,
    ) -> None:
        """Bind native execution to explicit configuration and delegation services.

        Args:
            context: Host provider, plugin, platform and conversation services.
            agent_configs: Shared storage for reusable agent configurations.
            subagents: Delegation scheduler sharing the application's runtime registry.
            max_idle_sessions: Soft limit for retained idle session handles.
        """
        self.context = context
        self.agent_configs = agent_configs
        self.subagents = subagents
        self._max_idle_sessions = max(1, max_idle_sessions)
        self._sessions: OrderedDict[tuple[str, str], AgentSession] = OrderedDict()
        # Keep live references weakly so LRU cache eviction does not close handles
        # retained by callers, while still preserving the single-owner invariant.
        self._live_sessions: WeakValueDictionary[tuple[str, str], AgentSession] = (
            WeakValueDictionary()
        )
        self._pending_close_sessions: WeakSet[AgentSession] = WeakSet()
        self._deferred_close_tasks: set[asyncio.Task[None]] = set()
        self._opening = asyncio.Lock()
        self._active_main: dict[str, AgentTurn] = {}
        self._session_deleted_callback_registered = False
        self._conversation_deleted_callback_registered = False
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
        conv_mgr = getattr(self.context, "conversation_manager", None)
        if (
            not self._session_deleted_callback_registered
            and conv_mgr is not None
            and hasattr(conv_mgr, "register_on_session_deleted")
        ):
            conv_mgr.register_on_session_deleted(self.evict_umo)
            self._session_deleted_callback_registered = True
        if (
            not self._conversation_deleted_callback_registered
            and conv_mgr is not None
            and hasattr(conv_mgr, "register_on_conversation_deleted")
        ):
            conv_mgr.register_on_conversation_deleted(self.evict_conversation)
            self._conversation_deleted_callback_registered = True

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
            input: Event for creating a main conversation or opening a delegated one.

        Returns:
            The sole live owner of the requested native conversation.

        Raises:
            ValueError: If the runtime is closed, the session is missing, or ownership differs.
        """
        if self._closed:
            raise ValueError("AstrBot agent runtime is closed")
        profile = (options or {}).get("profile", "main")
        if (
            profile == "main"
            and input is not None
            and isinstance(input.event, AgentWakeupEvent)
        ):
            target = input.event.agent_session
            if target is not None:
                if session_id is not None and session_id != target.session_id:
                    raise ValueError("Wakeup and runtime session targets differ")
                session_id = target.session_id
        manager = self.context.conversation_manager
        if profile == "subagent":
            async with self._opening:
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session = None
                if session_id is not None:
                    key = (profile, session_id)
                    candidate = self._sessions.get(key)
                    if candidate is None:
                        live = self._live_sessions.get(key)
                        if live is not None and not live.closed:
                            candidate = live
                        elif live is not None:
                            self._live_sessions.pop(key, None)
                    if (
                        candidate is not None
                        and candidate not in self._pending_close_sessions
                    ):
                        session = candidate
                if session is not None and session.umo != umo:
                    raise ValueError("Agent session belongs to another UMO")
                if session is None or session.closed:
                    if not isinstance(input, DelegatedAgentInput):
                        raise ValueError(
                            "Opening a child requires delegated caller input"
                        )
                    if session is not None:
                        await session.close()
                    session = await DelegatedAgentSession.open(
                        self, umo, input, options or {}, session_id=session_id
                    )
                if self._closed:
                    await session.close()
                    raise ValueError(
                        "AstrBot agent runtime closed during session creation"
                    )
                if session.umo != umo:
                    raise ValueError("Agent session belongs to another UMO")
                key = (profile, session.id)
                self._live_sessions[key] = session
                self._sessions[key] = session
                self._sessions.move_to_end(key)
                self._evict_idle_sessions(keep=key)
            return session
        if profile != "main":
            raise ValueError(f"Unknown built-in agent session profile: {profile}")
        conversation = None
        select_current = session_id is None
        if select_current and input is not None:
            request = input.event.get_extra("provider_request")
            if request is not None and request.conversation is not None:
                session_id = request.conversation.cid
                select_current = False
        if select_current:
            session_id = await manager.get_curr_conversation_id(umo)
        if conversation is None and session_id is not None:
            conversation = await manager.db.conversation_store.get_metadata(session_id)
        if conversation is None and select_current:
            # Only first creation needs serialization; recheck after acquiring the
            # lock so concurrent first messages cannot create competing sessions.
            async with self._opening:
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session_id = await manager.get_curr_conversation_id(umo)
                conversation = (
                    await manager.db.conversation_store.get_metadata(session_id)
                    if session_id is not None
                    else None
                )
                if conversation is None:
                    session_id = await manager.new_conversation(
                        umo,
                        platform_id=input.event.get_platform_id() if input else None,
                    )
                    conversation = await manager.db.conversation_store.get_metadata(
                        session_id
                    )
        if (
            session_id is None
            or conversation is None
            or conversation.umo != umo
            or self.subagents.store.find_native_conversation(umo, session_id)
            is not None
        ):
            raise ValueError("Agent conversation is missing or belongs to another UMO")
        # Existing conversations perform all database reads outside this registry
        # lock. Their execution lock controls when fresh history is loaded.
        async with self._opening:
            if self._closed:
                raise ValueError("AstrBot agent runtime closed during session creation")
            key = (profile, session_id)
            candidate = self._sessions.get(key)
            if candidate is None:
                live = self._live_sessions.get(key)
                if live is not None and not live.closed:
                    candidate = live
                elif live is not None:
                    self._live_sessions.pop(key, None)
            session = (
                candidate
                if candidate is not None
                and candidate not in self._pending_close_sessions
                else None
            )
            if session is None or session.closed:
                if session is not None:
                    await session.close()
                if self._closed:
                    raise ValueError("AstrBot agent runtime is closed")
                session = MainAgentSession(self, session_id, umo)
            elif session.umo != umo:
                raise ValueError("Agent session belongs to another UMO")
            self._live_sessions[key] = session
            self._sessions[key] = session
            self._sessions.move_to_end(key)
            self._evict_idle_sessions(keep=key)
        return session

    def _evict_idle_sessions(self, *, keep: tuple[str, str] | None = None) -> None:
        """Evict oldest idle or closed handles from the cache without closing them."""
        if len(self._sessions) <= self._max_idle_sessions:
            return
        for key in list(self._sessions):
            if len(self._sessions) <= self._max_idle_sessions:
                break
            if key == keep:
                continue
            session = self._sessions[key]
            if session.state in (SessionState.IDLE, SessionState.CLOSED):
                self._sessions.pop(key, None)

    async def _close_sessions(self, sessions: list[AgentSession]) -> None:
        """Close explicitly evicted sessions and log any close failures."""
        if not sessions:
            return
        results = await asyncio.gather(
            *(session.close() for session in sessions),
            return_exceptions=True,
        )
        for session, result in zip(sessions, results):
            if isinstance(result, BaseException) and not isinstance(
                result, asyncio.CancelledError
            ):
                logger.warning(
                    f"Failed to close evicted session {session.id}: {result}"
                )

    def _evict_matching_sessions(self, predicate) -> list[AgentSession]:
        """Collect idle matches for immediate close and mark active ones for deferred close."""
        evicted: list[AgentSession] = []
        seen_ids: set[int] = set()
        for source in (self._sessions, self._live_sessions):
            for key in list(source):
                session = source.get(key)
                if session is None or id(session) in seen_ids or not predicate(session):
                    continue
                seen_ids.add(id(session))
                self._sessions.pop(key, None)
                self._live_sessions.pop(key, None)
                if session.state in (SessionState.IDLE, SessionState.CLOSED):
                    evicted.append(session)
                else:
                    self._pending_close_sessions.add(session)
        return evicted

    async def evict_umo(self, umo: str) -> None:
        """Evict sessions and delegated callers belonging to a deleted UMO.

        Args:
            umo: Unified message origin whose conversations were removed.
        """
        async with self._opening:
            evicted = self._evict_matching_sessions(lambda s: s.umo == umo)
        await self._close_sessions(evicted)
        if hasattr(self.subagents, "evict_umo"):
            self.subagents.evict_umo(umo)

    async def evict_conversation(self, umo: str, conversation_id: str) -> None:
        """Evict sessions and delegated callers for a deleted conversation.

        Args:
            umo: Unified message origin owning the deleted conversation.
            conversation_id: Deleted conversation identifier.
        """
        async with self._opening:
            evicted = self._evict_matching_sessions(
                lambda s: s.umo == umo and s.id == conversation_id
            )
        await self._close_sessions(evicted)
        if hasattr(self.subagents, "evict_scope"):
            self.subagents.evict_scope(umo, conversation_id)

    def on_session_idle(self, key: tuple[str, str], session: AgentSession) -> None:
        """Apply deferred deletion closing or capacity eviction once a turn settles.

        Args:
            key: Session registry key ``(profile, session_id)``.
            session: Session that just transitioned to idle.
        """
        if self._closed:
            return
        if session in self._pending_close_sessions:
            self._pending_close_sessions.discard(session)
            if self._sessions.get(key) is session:
                self._sessions.pop(key, None)
            if self._live_sessions.get(key) is session:
                self._live_sessions.pop(key, None)
            task = asyncio.create_task(self._close_sessions([session]))
            self._deferred_close_tasks.add(task)
            task.add_done_callback(self._deferred_close_tasks.discard)
            return
        self._evict_idle_sessions()

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
        if self._deferred_close_tasks:
            await asyncio.gather(
                *list(self._deferred_close_tasks), return_exceptions=True
            )
        async with self._opening:
            unique_sessions: list[AgentSession] = []
            seen_ids: set[int] = set()
            for session in (
                *self._sessions.values(),
                *self._live_sessions.values(),
                *self._pending_close_sessions,
            ):
                if id(session) not in seen_ids:
                    seen_ids.add(id(session))
                    unique_sessions.append(session)
        try:
            await asyncio.gather(*(session.close() for session in unique_sessions))
        finally:
            self._sessions.clear()
            self._live_sessions.clear()
            self._pending_close_sessions.clear()
            self._deferred_close_tasks.clear()
            await shutdown_local_booter()
