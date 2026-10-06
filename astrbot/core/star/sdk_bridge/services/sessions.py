from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from sys import maxsize
from typing import TYPE_CHECKING, Any

from astrbot_sdk.errors import Conflict, InvalidRequest, NotFound

from astrbot.core import logger

from ..convert import to_sdk_event, to_umo_string

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

    from ..bridge import SDKPluginBridge

# Round-trip budget for one consider call; it runs inside the inbound
# message pipeline, so a stuck Runner must not stall message delivery.
_CONSIDER_TIMEOUT = 1.0


@dataclass(slots=True)
class _WaitEntry:
    """One armed session wait claimed by a bridged plugin."""

    key: str
    umo_str: str
    umo_scoped: bool
    waiter_id: str
    bridge: SDKPluginBridge
    timeout: float
    deadline: asyncio.Task[None] | None = None


# Global session-key registry shared by all bridges. Waiters are scarce, so
# linear scans over values are fine and keep claiming order deterministic.
_REGISTRY: dict[str, _WaitEntry] = {}
_CLAIM_LOCK = asyncio.Lock()
_INTERCEPTOR_REGISTERED = False


def ensure_interceptor_registered() -> None:
    """Register the global session-wait pipeline interceptor exactly once.

    The interceptor is process-lifetime and a no-op while the registry is
    empty. It is anchored on a pseudo star_map entry (never listed as a
    plugin) so the activation filter lets it run.
    """
    global _INTERCEPTOR_REGISTERED
    if _INTERCEPTOR_REGISTERED:
        return
    from astrbot.core.star.filter.event_message_type import (
        EventMessageType,
        EventMessageTypeFilter,
    )
    from astrbot.core.star.star import StarMetadata, star_map
    from astrbot.core.star.star_handler import (
        EventType,
        StarHandlerMetadata,
        star_handlers_registry,
    )

    module_path = "astrbot.core.star.sdk_bridge"
    if module_path not in star_map:
        star_map[module_path] = StarMetadata(
            name="astrbot_sdk_bridge",
            module_path=module_path,
            reserved=True,
            activated=True,
        )
    star_handlers_registry.append(
        StarHandlerMetadata(
            event_type=EventType.AdapterMessageEvent,
            handler_full_name=f"{module_path}_session_wait",
            handler_name="session_wait_interceptor",
            handler_module_path=module_path,
            handler=_session_wait_interceptor,
            event_filters=[EventMessageTypeFilter(EventMessageType.ALL)],
            desc="SDK session wait interceptor",
            extras_configs={"priority": maxsize},
        )
    )
    _INTERCEPTOR_REGISTERED = True


async def _session_wait_interceptor(event: AstrMessageEvent, **_kwargs: Any) -> None:
    """Offer every inbound message to armed session waits before handlers."""
    if not _REGISTRY:
        return
    umo = event.unified_msg_origin
    async with _CLAIM_LOCK:
        candidates = [
            entry
            for entry in _REGISTRY.values()
            if not entry.umo_scoped or entry.umo_str == umo
        ]
        if not candidates:
            return
        sdk_event = to_sdk_event(event)
        bridges = {id(entry.bridge): entry.bridge for entry in candidates}
        matched: dict[int, set[tuple[str, str]]] = {}
        for bridge_id, bridge in bridges.items():
            try:
                client = bridge._require_client()
                result = await client.session_consider(
                    sdk_event,
                    timeout=_CONSIDER_TIMEOUT,
                )
            except Exception:
                # A bridge that cannot answer consider is gone or stuck; its
                # waiters can never be delivered, so drop them loudly.
                logger.warning(
                    "session consider failed for SDK plugin %s; purging its waits",
                    bridge.plugin_id,
                    exc_info=True,
                )
                purge_bridge_sessions(bridge)
                continue
            matched[bridge_id] = {
                (str(item.get("waiter_id")), str(item.get("key")))
                for item in result.get("matches", [])
            }
        for entry in candidates:
            if _REGISTRY.get(entry.key) is not entry:
                continue  # expired or evicted while considers were in flight
            if (entry.waiter_id, entry.key) in matched.get(id(entry.bridge), set()):
                await _claim(entry, event, sdk_event)
                return


async def _claim(
    entry: _WaitEntry,
    event: AstrMessageEvent,
    sdk_event: Any,
) -> None:
    """Deliver one inbound event to its session wait and stop propagation."""
    try:
        await entry.bridge._require_client().session_matched(
            entry.waiter_id,
            sdk_event,
        )
    except Exception:
        # The Runner died between consider and claim; leave propagation
        # untouched so the message still reaches normal handlers.
        logger.warning(
            "session delivery failed for SDK plugin %s; dropping the wait",
            entry.bridge.plugin_id,
            exc_info=True,
        )
        _remove(entry)
        return
    _cancel_deadline(entry)
    event.stop_event()


def _cancel_deadline(entry: _WaitEntry) -> None:
    """Cancel the pending timeout task of one entry."""
    if entry.deadline is not None:
        entry.deadline.cancel()
        entry.deadline = None


def _remove(entry: _WaitEntry) -> None:
    """Drop one entry from the registry and cancel its deadline."""
    _cancel_deadline(entry)
    if _REGISTRY.get(entry.key) is entry:
        _REGISTRY.pop(entry.key, None)


def purge_bridge_sessions(bridge: SDKPluginBridge) -> None:
    """Drop every session wait owned by one bridge (stop/crash cleanup).

    Args:
        bridge: Bridge whose waiters should be removed.
    """
    for entry in list(_REGISTRY.values()):
        if entry.bridge is bridge:
            _remove(entry)


async def _expire(key: str, entry: _WaitEntry, delay: float) -> None:
    """Expire one waiter after its deadline and notify the Runner."""
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    if _REGISTRY.get(key) is not entry:
        return
    _REGISTRY.pop(key, None)
    logger.debug(
        "session wait expired: plugin=%s waiter=%s",
        entry.bridge.plugin_id,
        entry.waiter_id,
    )
    with contextlib.suppress(Exception):
        await entry.bridge._require_client().session_timeout(entry.waiter_id)


class SessionWaitService:
    """Host side of the message.wait capability (register/rearm/stop)."""

    capability_id = "message.wait"

    def __init__(self, bridge: SDKPluginBridge) -> None:
        """Initialize the service.

        Args:
            bridge: Owning bridge used to reach the calling Runner.
        """
        self._bridge = bridge

    async def handle(self, operation: str, payload: dict[str, Any]) -> Any:
        """Serve one session wait operation."""
        if operation == "register":
            return await self._register(payload)
        if operation == "rearm":
            return await self._rearm(payload)
        if operation == "stop":
            return await self._stop(payload)
        raise NotFound(f"unknown session operation: {operation}")

    def _find_entry(self, waiter_id: str) -> _WaitEntry:
        """Look up one entry owned by this bridge or fail loudly."""
        for entry in _REGISTRY.values():
            if entry.waiter_id == waiter_id:
                if entry.bridge is not self._bridge:
                    raise Conflict(
                        f"session waiter belongs to another plugin: {waiter_id}"
                    )
                return entry
        raise NotFound(f"unknown session waiter: {waiter_id}")

    async def _register(self, payload: dict[str, Any]) -> Any:
        """Claim a session key for a new waiter and arm its first deadline."""
        waiter_id = str(payload.get("waiter_id") or "")
        key = str(payload.get("key") or "")
        umo = payload.get("umo")
        timeout = payload.get("timeout")
        if not waiter_id or not key or umo is None:
            raise InvalidRequest("session register requires waiter_id, key and umo")
        if not isinstance(timeout, int | float) or timeout <= 0:
            raise InvalidRequest("session register requires a positive timeout")
        ensure_interceptor_registered()
        existing = _REGISTRY.get(key)
        if existing is not None:
            if existing.bridge is not self._bridge:
                raise Conflict(
                    f"session is already claimed by plugin "
                    f"{existing.bridge.plugin_id}: {key}"
                )
            # Same-plugin re-registration evicts the previous waiter, mirroring
            # the legacy USER_SESSIONS overwrite semantics.
            _remove(existing)
            with contextlib.suppress(Exception):
                await existing.bridge._require_client().session_timeout(
                    existing.waiter_id
                )
        entry = _WaitEntry(
            key=key,
            umo_str=to_umo_string(umo),
            umo_scoped=bool(payload.get("umo_scoped")),
            waiter_id=waiter_id,
            bridge=self._bridge,
            timeout=float(timeout),
        )
        entry.deadline = asyncio.create_task(_expire(key, entry, entry.timeout))
        _REGISTRY[key] = entry
        return {"ok": True}

    async def _rearm(self, payload: dict[str, Any]) -> Any:
        """Reset the deadline of one waiter to a fresh timeout."""
        waiter_id = str(payload.get("waiter_id") or "")
        timeout = payload.get("timeout")
        if not isinstance(timeout, int | float) or timeout <= 0:
            raise InvalidRequest("session rearm requires a positive timeout")
        entry = self._find_entry(waiter_id)
        _cancel_deadline(entry)
        entry.timeout = float(timeout)
        entry.deadline = asyncio.create_task(_expire(entry.key, entry, entry.timeout))
        return {"ok": True}

    async def _stop(self, payload: dict[str, Any]) -> Any:
        """Release one waiter's session claim (idempotent)."""
        waiter_id = str(payload.get("waiter_id") or "")
        for entry in list(_REGISTRY.values()):
            if entry.waiter_id == waiter_id and entry.bridge is self._bridge:
                _remove(entry)
        return {"ok": True}
