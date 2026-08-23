"""Opt-in group sender-concurrent Agent runs.

LLM locks may split by sender. Group outbound is serialized per UMO for the
whole concurrent turn. History merging lives in AssistantHistoryCommitter.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from astrbot.core.platform.message_type import MessageType
from astrbot.core.utils.session_lock import SessionLockManager

SENDER_LOCK_SEP = "\x1f"
OUTBOUND_LOCK_SUFFIX = f"{SENDER_LOCK_SEP}outbound"


@dataclass(frozen=True, slots=True)
class ConcurrentTurn:
    """The in-task concurrent group turn that owns outbound serialization."""

    umo: str
    event: object
    gate: GroupOutboundGate


_current_turn: ContextVar[ConcurrentTurn | None] = ContextVar(
    "group_sender_concurrent_turn",
    default=None,
)


def session_lock_key(umo: str, sender_id: str | None, *, concurrent: bool) -> str:
    """Return the LLM session lock key for one Agent run."""
    if concurrent and sender_id:
        return f"{umo}{SENDER_LOCK_SEP}sender:{sender_id}"
    return umo


def sender_id_of(event: object) -> str:
    """Return a non-blank sender id, or an empty string."""
    getter = getattr(event, "get_sender_id", None)
    if not callable(getter):
        return ""
    value = getter()
    return value.strip() if isinstance(value, str) else ""


def is_group_sender_concurrent(event: object, config: object | None) -> bool:
    """Return whether this event should use sender-split LLM locks."""
    if not isinstance(config, dict):
        return False
    platform_settings = config.get("platform_settings", {})
    if not isinstance(platform_settings, dict):
        return False
    if not platform_settings.get("group_sender_concurrency"):
        return False
    if platform_settings.get("unique_session"):
        return False
    get_extra = getattr(event, "get_extra", None)
    event_extra = (
        get_extra if callable(get_extra) else lambda _key, default=None: default
    )
    if event_extra("action_type") == "live":
        return False
    if event_extra("active_reply") or event_extra("cron_job"):
        return False
    platform_meta = getattr(event, "platform_meta", None)
    if getattr(platform_meta, "name", "") == "cron":
        return False
    get_message_type = getattr(event, "get_message_type", None)
    if not callable(get_message_type):
        return False
    if get_message_type() != MessageType.GROUP_MESSAGE:
        return False
    return bool(sender_id_of(event))


def current_concurrent_turn() -> ConcurrentTurn | None:
    """Return the concurrent turn bound to this task, if any."""
    return _current_turn.get()


@asynccontextmanager
async def bind_concurrent_turn(turn: ConcurrentTurn) -> AsyncIterator[None]:
    """Bind a concurrent turn to the current task until the Agent run ends."""
    token = _current_turn.set(turn)
    try:
        yield
    finally:
        _current_turn.reset(token)
        await turn.gate.release_turn(turn.event)


class GroupOutboundGate:
    """Serialize group outbound for concurrent sender turns.

    A concurrent turn holds the UMO lock from its first real send until
    ``release_turn``. Other tasks wait on the same lock for one send.
    The same task may re-enter without deadlocking.
    """

    def __init__(self, lock_manager: SessionLockManager | None = None) -> None:
        self._locks = lock_manager or SessionLockManager()
        self._turn_cms: dict[int, Any] = {}
        self._turn_umos: dict[int, str] = {}
        self._depth: dict[tuple[int, str], int] = defaultdict(int)

    def has_turn_holder(self, umo: str) -> bool:
        """Return whether a concurrent turn currently holds this UMO."""
        return any(held == umo for held in self._turn_umos.values())

    def _task_key(self, umo: str) -> tuple[int, str]:
        task = asyncio.current_task()
        return (id(task) if task is not None else 0, umo)

    async def hold_turn(self, umo: str, event: object) -> None:
        """Acquire the UMO outbound lock for this concurrent turn if needed."""
        event_id = id(event)
        if event_id in self._turn_cms:
            return
        key = self._task_key(umo)
        if self._depth[key]:
            self._depth[key] += 1
            self._turn_cms[event_id] = None
            self._turn_umos[event_id] = umo
            return
        cm = self._locks.acquire_lock(f"{umo}{OUTBOUND_LOCK_SUFFIX}")
        await cm.__aenter__()
        self._turn_cms[event_id] = cm
        self._turn_umos[event_id] = umo
        self._depth[key] = 1

    async def release_turn(self, event: object) -> None:
        """Release a turn lock acquired by ``hold_turn``."""
        event_id = id(event)
        umo = self._turn_umos.pop(event_id, None)
        cm = self._turn_cms.pop(event_id, None)
        if umo is None:
            return
        key = self._task_key(umo)
        depth = self._depth.get(key, 0)
        if depth > 1:
            self._depth[key] = depth - 1
            return
        self._depth.pop(key, None)
        if cm is not None:
            await cm.__aexit__(None, None, None)

    @asynccontextmanager
    async def around_send(self, umo: str) -> AsyncIterator[None]:
        """Wait for the UMO outbound lock unless this task already holds it."""
        key = self._task_key(umo)
        if self._depth[key]:
            self._depth[key] += 1
            try:
                yield
            finally:
                self._depth[key] -= 1
                if self._depth[key] <= 0:
                    self._depth.pop(key, None)
            return
        async with self._locks.acquire_lock(f"{umo}{OUTBOUND_LOCK_SUFFIX}"):
            self._depth[key] += 1
            try:
                yield
            finally:
                self._depth[key] -= 1
                if self._depth[key] <= 0:
                    self._depth.pop(key, None)


@asynccontextmanager
async def serialize_group_outbound(
    umo: str, gate: GroupOutboundGate | None
) -> AsyncIterator[None]:
    """Hold or wait for the group outbound lock when a concurrent turn is active."""
    turn = current_concurrent_turn()
    active_gate = gate or (turn.gate if turn is not None else None)
    if active_gate is None:
        yield
        return
    if turn is not None:
        await active_gate.hold_turn(turn.umo, turn.event)
        if umo == turn.umo:
            yield
            return
    if active_gate.has_turn_holder(umo):
        async with active_gate.around_send(umo):
            yield
        return
    yield
