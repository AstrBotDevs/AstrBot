"""Persistent agent sessions and their input/result records, independent of runtimes."""

from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from enum import Enum
from time import time
from typing import TYPE_CHECKING

from astrbot import logger
from astrbot.core.agent.runtime import AgentPermissions, AgentRole, AgentSessionRef

from .messages import format_agent_messages

if TYPE_CHECKING:
    from astrbot.core.db import BaseDatabase


@dataclass(frozen=True)
class AgentScope:
    """Owner of delegated sessions within one main conversation."""

    umo: str
    conversation_id: str


class AgentState(str, Enum):
    """State of a single input execution, rather than the lifetime of an agent."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"
    INTERRUPTED = "interrupted"


class DeliveryStage(str, Enum):
    """Result receipt progress, confirmed against the saved main conversation."""

    PENDING = "pending"
    OBSERVED = "observed"
    COMMITTED = "committed"


@dataclass
class TaskRecord:
    """One accepted input and its result; follow-ups may merge into an active turn."""

    turn_id: int
    messages: list[dict]
    permissions: AgentPermissions = field(default_factory=AgentPermissions)
    state: AgentState = AgentState.PENDING
    result: str | None = None
    error: str | None = None
    created_at: float = field(default_factory=time)
    started_at: float | None = None
    finished_at: float | None = None
    completed_steps: int = 0
    delivery: DeliveryStage = DeliveryStage.PENDING

    @property
    def finished(self) -> bool:
        """Whether execution has reached a terminal state."""
        return self.state not in (AgentState.PENDING, AgentState.RUNNING)


@dataclass
class AgentRecord:
    """Public identity mapped to an opaque conversation owned by an agent runtime."""

    agent_id: str
    scope: AgentScope
    runtime: str
    name: str
    conversation_id: str
    options: dict
    owner: dict
    parent: AgentSessionRef
    turns: list[TaskRecord] = field(default_factory=list)
    next_turn_id: int = 1
    created_at: float = field(default_factory=time)

    @property
    def current(self) -> TaskRecord:
        """Prefer an executing input, then the oldest queued input, then the last result."""
        return next(
            (turn for turn in self.turns if turn.state == AgentState.RUNNING),
            next(
                (turn for turn in self.turns if turn.state == AgentState.PENDING),
                self.turns[-1],
            ),
        )

    def describe(self, turn: TaskRecord | None = None, *, result: bool = False) -> dict:
        """Build runtime-independent metadata for tools and the dashboard.

        Args:
            turn: Specific result to describe; defaults to the current execution.
            result: Whether to include result text, errors, and a receipt marker.

        Returns:
            Serializable public session and execution metadata.
        """
        turn = turn or self.current
        data = {
            "agent_id": self.agent_id,
            "name": self.name,
            "runtime": self.runtime,
            "conversation_id": self.conversation_id,
            "session": self.scope.umo,
            "owner_conversation_id": self.scope.conversation_id,
            "sender": self.owner["sender_id"],
            "turn_id": turn.turn_id,
            "state": turn.state.value,
            "task": format_agent_messages(turn.messages),
            "created_at": self.created_at,
            "started_at": turn.started_at,
            "finished_at": turn.finished_at,
            "completed_steps": turn.completed_steps,
            "updated_at": turn.finished_at or turn.started_at or turn.created_at,
        }
        if result:
            data.update(result=turn.result, error=turn.error)
            if turn.finished:
                data["receipt"] = f"[subagent-result:{self.agent_id}:{turn.turn_id}]"
        return data


class SubAgentStore:
    """Persist sessions without holding event objects, tasks, runtimes, or private histories."""

    def __init__(self, db: BaseDatabase) -> None:
        self.db = db
        self.agents: dict[str, AgentRecord] = {}
        self._write_lock = asyncio.Lock()

    async def load(self) -> None:
        """Load session records without starting or replaying any agent execution."""
        for row in await self.db.get_preferences(scope="subagent_session"):
            try:
                data = row.value
                scope = AgentScope(
                    data["scope"]["umo"], data["scope"]["conversation_id"]
                )
                owner = dict(data["owner"])
                if "sender_id" not in owner:
                    # Older records stored the wakeup sender in the ownership scope.
                    owner["sender_id"] = data["scope"]["sender_id"]
                if row.scope_id != scope.umo or row.key != data["agent_id"]:
                    raise ValueError(
                        "Agent session storage key does not match its owner"
                    )
                data = {
                    **data,
                    "scope": scope,
                    "owner": owner,
                    # Earlier records could only be created by the main conversation.
                    "parent": AgentSessionRef(
                        **data.get(
                            "parent",
                            {
                                "runtime": "astrbot",
                                "session_id": scope.conversation_id,
                            },
                        )
                    ),
                    "turns": [
                        TaskRecord(
                            **{
                                **turn,
                                "permissions": AgentPermissions(
                                    AgentRole(turn["permissions"]["role"])
                                ),
                                "state": AgentState(turn["state"]),
                                "delivery": DeliveryStage(turn["delivery"]),
                            }
                        )
                        for turn in data["turns"]
                    ],
                }
                agent = AgentRecord(**data)
                if not agent.turns:
                    raise ValueError("Agent session has no accepted input")
                self.agents[agent.agent_id] = agent
            except (KeyError, TypeError, ValueError):
                logger.exception("Unable to load agent session %s", row.key)

    async def save(self, agent: AgentRecord) -> None:
        """Serialize the latest state while holding the write lock.

        Args:
            agent: Session to insert or update.
        """
        async with self._write_lock:
            await self.db.insert_preference_or_update(
                "subagent_session", agent.scope.umo, agent.agent_id, asdict(agent)
            )

    async def remove(self, agent: AgentRecord) -> None:
        """Delete a session whose owning main conversation no longer exists.

        Args:
            agent: Session to remove from memory and persistent storage.
        """
        async with self._write_lock:
            await self.db.remove_preference(
                "subagent_session", agent.scope.umo, agent.agent_id
            )
            self.agents.pop(agent.agent_id, None)

    def get(self, agent_id: str, scope: AgentScope) -> AgentRecord:
        """Look up an agent belonging to the calling conversation.

        Args:
            agent_id: Public agent ID returned by spawn_agent.
            scope: Required UMO and main conversation.

        Returns:
            The caller's agent session.

        Raises:
            ValueError: If the ID is unknown or belongs to another owner.
        """
        agent = self.agents.get(agent_id)
        if agent is None or agent.scope != scope:
            raise ValueError(f"Unknown subagent: {agent_id}")
        return agent

    def list(self, scope: AgentScope) -> list[AgentRecord]:
        """Return sessions shared within one main conversation.

        Args:
            scope: Owner to filter by.

        Returns:
            Matching sessions in creation order.
        """
        return [agent for agent in self.agents.values() if agent.scope == scope]
