from __future__ import annotations

import abc
import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ..errors import InvalidRequest, NotFound
from ..events import MessageEvent

if TYPE_CHECKING:
    from ..context import PluginContext
    from ..messages import MessageLike

_SESSION_WAIT_CAPABILITY = "message.wait"

logger = logging.getLogger(__name__)


class SessionFilter(abc.ABC):
    """Map an inbound message event to the session key it belongs to.

    The filter runs inside the Runner for every inbound event of a session
    candidate; a wait matches when the produced key equals the key computed
    on the initiating event.
    """

    umo_scoped: bool = False
    """Whether keys only ever match events of the initiating UMO.

    The Host uses this hint to skip the consider round-trip for events from
    unrelated sessions. Custom filters default to False (always consulted).
    """

    @abc.abstractmethod
    def filter(self, event: MessageEvent) -> str:
        """Return the session key for one event."""


class DefaultSessionFilter(SessionFilter):
    """Scope a session to its unified message origin (UMO)."""

    umo_scoped = True

    def filter(self, event: MessageEvent) -> str:
        """Return the UMO-derived session key."""
        umo = event.umo
        return f"{umo.platform_id}:{umo.message_type}:{umo.session_id}"


class SenderSessionFilter(SessionFilter):
    """Scope a session to the sending user inside its UMO."""

    umo_scoped = True

    def filter(self, event: MessageEvent) -> str:
        """Return the UMO + sender session key."""
        umo = event.umo
        return (
            f"{umo.platform_id}:{umo.message_type}:{umo.session_id}:{event.sender.id}"
        )


@dataclass(slots=True)
class _Waiter:
    """Track one armed linear wait inside the Runner."""

    id: str
    key: str
    filter: SessionFilter
    timeout: float
    queue: asyncio.Queue[MessageEvent | BaseException]


class SessionWait:
    """Linear multi-turn session wait returned by SessionService.wait().

    Use as an async context manager; each next() call waits for the next
    inbound message matching the session filter and re-arms the Host-side
    timeout clock.
    """

    def __init__(
        self,
        service: SessionService,
        waiter: _Waiter,
        event: MessageEvent,
    ) -> None:
        """Initialize the wait handle.

        Args:
            service: Owning session service.
            waiter: Runner-side waiter state.
            event: Initiating event the session was scoped from.
        """
        self._service = service
        self._waiter = waiter
        self._event = event

    async def __aenter__(self) -> SessionWait:
        """Register the waiter with the Host."""
        await self._service._register(self._waiter, self._event)
        return self

    async def __aexit__(self, *_exc: object) -> None:
        """Stop the waiter and release the Host-side session claim."""
        await self._service._stop(self._waiter)

    async def next(self, timeout: float | None = None) -> MessageEvent:  # noqa: ASYNC109
        """Wait for the next inbound message of this session.

        Args:
            timeout: Per-turn timeout override in seconds. Defaults to the
                timeout given to wait(). Re-arms the Host clock on each call.

        Returns:
            The next matched inbound message event.

        Raises:
            TimeoutError: The turn timed out or the session expired.
            HostUnavailable: The Host went away while waiting.
        """
        waiter = self._waiter
        if waiter.queue.empty():
            effective = waiter.timeout if timeout is None else timeout
            try:
                await self._service._rearm(waiter, effective)
            except NotFound as exc:
                raise TimeoutError("session wait expired") from exc
        item = await waiter.queue.get()
        if isinstance(item, BaseException):
            raise item
        return item

    async def ask(
        self,
        content: MessageLike,
        timeout: float | None = None,  # noqa: ASYNC109
    ) -> MessageEvent:
        """Send a follow-up message into the session and wait for the reply.

        Args:
            content: Message content sent through ctx.messages.send.
            timeout: Per-turn timeout override in seconds.

        Returns:
            The reply event.
        """
        await self._service._ctx.messages.send(self._event.umo, content)
        return await self.next(timeout=timeout)


class SessionService:
    """Linear multi-turn waits on inbound session messages."""

    def __init__(self, ctx: PluginContext) -> None:
        """Initialize the session service.

        Args:
            ctx: Owning plugin context used for Host invocation.
        """
        self._ctx = ctx
        self._waiters: dict[str, _Waiter] = {}

    def wait(
        self,
        event: MessageEvent | None = None,
        *,
        filter: SessionFilter | None = None,
        timeout: float = 60.0,
    ) -> SessionWait:
        """Start a linear multi-turn wait scoped from one event.

        Args:
            event: Initiating event. Defaults to the ambient handler event.
            filter: Session key mapping. Defaults to DefaultSessionFilter.
            timeout: Default per-turn timeout in seconds.

        Returns:
            Async context manager yielding the SessionWait handle.

        Raises:
            InvalidRequest: No event is available or the timeout is invalid.
        """
        if event is None:
            event = self._ctx._ambient_event()
        if event is None:
            raise InvalidRequest("sessions.wait() requires a MessageEvent")
        if timeout <= 0:
            raise InvalidRequest("session wait timeout must be positive")
        session_filter = filter if filter is not None else DefaultSessionFilter()
        waiter = _Waiter(
            id=uuid.uuid4().hex,
            key=session_filter.filter(event),
            filter=session_filter,
            timeout=float(timeout),
            queue=asyncio.Queue(),
        )
        return SessionWait(self, waiter, event)

    async def _register(self, waiter: _Waiter, event: MessageEvent) -> None:
        """Claim the session key on the Host and arm the first deadline."""
        await self._ctx._invoke_capability(
            _SESSION_WAIT_CAPABILITY,
            "register",
            {
                "waiter_id": waiter.id,
                "key": waiter.key,
                "umo": event.umo,
                "timeout": waiter.timeout,
                "umo_scoped": bool(getattr(waiter.filter, "umo_scoped", False)),
            },
        )
        self._waiters[waiter.id] = waiter

    async def _rearm(self, waiter: _Waiter, timeout: float) -> None:  # noqa: ASYNC109
        """Reset the Host-side deadline for one waiter."""
        await self._ctx._invoke_capability(
            _SESSION_WAIT_CAPABILITY,
            "rearm",
            {"waiter_id": waiter.id, "timeout": timeout},
        )

    async def _stop(self, waiter: _Waiter) -> None:
        """Release the Host-side session claim (best effort)."""
        self._waiters.pop(waiter.id, None)
        with contextlib.suppress(Exception):
            await self._ctx._invoke_capability(
                _SESSION_WAIT_CAPABILITY,
                "stop",
                {"waiter_id": waiter.id},
            )

    # Host -> Runner delivery entry points (driven by stdio_server) ----------

    def _consider(self, event: MessageEvent) -> list[dict[str, str]]:
        """Return the local waiters whose filter matches one inbound event."""
        matches: list[dict[str, str]] = []
        for waiter in self._waiters.values():
            try:
                key = waiter.filter.filter(event)
            except Exception:
                logger.warning(
                    "session filter %r failed; treated as non-match",
                    waiter.filter,
                    exc_info=True,
                )
                continue
            if key == waiter.key:
                matches.append({"waiter_id": waiter.id, "key": key})
        return matches

    def _deliver(self, waiter_id: str, event: MessageEvent) -> None:
        """Queue one matched event for a waiting next() call."""
        waiter = self._waiters.get(waiter_id)
        if waiter is not None:
            waiter.queue.put_nowait(event)

    def _timeout(self, waiter_id: str) -> None:
        """Fail one waiter with TimeoutError from the Host clock."""
        waiter = self._waiters.get(waiter_id)
        if waiter is not None:
            waiter.queue.put_nowait(TimeoutError("session wait timed out"))

    def _fail_all(self, error: BaseException) -> None:
        """Fail every pending waiter, e.g. on Runner shutdown."""
        for waiter in self._waiters.values():
            waiter.queue.put_nowait(error)
