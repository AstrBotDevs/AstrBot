from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest
from astrbot_sdk.errors import Conflict, InvalidRequest, NotFound
from astrbot_sdk.events import UMO, MessageType

import astrbot.core.star.sdk_bridge.services.sessions as bridge_sessions
from astrbot.core.star.sdk_bridge.services.sessions import (
    SessionWaitService,
    purge_bridge_sessions,
)


class FakeClient:
    """Runner stub recording session pushes and answering consider."""

    def __init__(self, matches: list[dict[str, str]] | None = None) -> None:
        self.matches = matches or []
        self.matched: list[tuple[str, Any]] = []
        self.timeouts: list[str] = []

    async def session_consider(self, event, *, timeout: float = 1.0):
        return {"matches": list(self.matches)}

    async def session_matched(self, waiter_id: str, event):
        self.matched.append((waiter_id, event))
        return {"ok": True}

    async def session_timeout(self, waiter_id: str):
        self.timeouts.append(waiter_id)
        return {"ok": True}


def make_bridge(plugin_id: str, client: FakeClient) -> Any:
    """Build the minimal bridge surface the session service touches."""
    return SimpleNamespace(
        plugin_id=plugin_id,
        _require_client=lambda: client,
    )


def make_umo() -> UMO:
    return UMO(
        platform_id="webchat",
        message_type=MessageType.PRIVATE,
        session_id="user-1",
    )


@pytest.fixture(autouse=True)
def clean_registry():
    yield
    for entry in list(bridge_sessions._REGISTRY.values()):
        if entry.deadline is not None:
            entry.deadline.cancel()
    bridge_sessions._REGISTRY.clear()


def register_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "waiter_id": "w1",
        "key": "webchat:FriendMessage:user-1",
        "umo": make_umo(),
        "timeout": 30.0,
        "umo_scoped": True,
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_register_claims_key_and_arms_deadline() -> None:
    service = SessionWaitService(make_bridge("a", FakeClient()))
    result = await service.handle("register", register_payload())
    assert result == {"ok": True}
    entry = bridge_sessions._REGISTRY["webchat:FriendMessage:user-1"]
    assert entry.waiter_id == "w1"
    assert entry.timeout == 30.0
    assert entry.deadline is not None and not entry.deadline.done()


@pytest.mark.asyncio
async def test_register_validates_payload() -> None:
    service = SessionWaitService(make_bridge("a", FakeClient()))
    with pytest.raises(InvalidRequest):
        await service.handle("register", register_payload(waiter_id=""))
    with pytest.raises(InvalidRequest):
        await service.handle("register", register_payload(umo=None))
    with pytest.raises(InvalidRequest):
        await service.handle("register", register_payload(timeout=0))
    with pytest.raises(NotFound):
        await service.handle("bogus", {})


@pytest.mark.asyncio
async def test_register_conflicts_across_plugins() -> None:
    await SessionWaitService(make_bridge("a", FakeClient())).handle(
        "register", register_payload()
    )
    other = SessionWaitService(make_bridge("b", FakeClient()))
    with pytest.raises(Conflict):
        await other.handle("register", register_payload(waiter_id="w2"))


@pytest.mark.asyncio
async def test_same_plugin_reregister_evicts_previous_waiter() -> None:
    client = FakeClient()
    service = SessionWaitService(make_bridge("a", client))
    await service.handle("register", register_payload())
    await service.handle("register", register_payload(waiter_id="w2"))
    entry = bridge_sessions._REGISTRY["webchat:FriendMessage:user-1"]
    assert entry.waiter_id == "w2"
    assert client.timeouts == ["w1"]


@pytest.mark.asyncio
async def test_rearm_resets_deadline() -> None:
    service = SessionWaitService(make_bridge("a", FakeClient()))
    await service.handle("register", register_payload())
    entry = bridge_sessions._REGISTRY["webchat:FriendMessage:user-1"]
    old_deadline = entry.deadline
    await service.handle("rearm", {"waiter_id": "w1", "timeout": 5})
    assert entry.timeout == 5.0
    assert entry.deadline is not old_deadline
    assert old_deadline.cancelling()
    with pytest.raises(InvalidRequest):
        await service.handle("rearm", {"waiter_id": "w1", "timeout": -1})
    with pytest.raises(NotFound):
        await service.handle("rearm", {"waiter_id": "ghost", "timeout": 5})


@pytest.mark.asyncio
async def test_rearm_rejects_waiter_of_another_plugin() -> None:
    await SessionWaitService(make_bridge("a", FakeClient())).handle(
        "register", register_payload()
    )
    other = SessionWaitService(make_bridge("b", FakeClient()))
    with pytest.raises(Conflict):
        await other.handle("rearm", {"waiter_id": "w1", "timeout": 5})


@pytest.mark.asyncio
async def test_stop_releases_claim_idempotently() -> None:
    service = SessionWaitService(make_bridge("a", FakeClient()))
    await service.handle("register", register_payload())
    await service.handle("stop", {"waiter_id": "w1"})
    assert bridge_sessions._REGISTRY == {}
    # Stopping twice must stay a no-op.
    await service.handle("stop", {"waiter_id": "w1"})


@pytest.mark.asyncio
async def test_deadline_expiry_pops_entry_and_notifies_runner() -> None:
    client = FakeClient()
    service = SessionWaitService(make_bridge("a", client))
    await service.handle("register", register_payload(timeout=0.05))
    await asyncio.sleep(0.15)
    assert bridge_sessions._REGISTRY == {}
    assert client.timeouts == ["w1"]


@pytest.mark.asyncio
async def test_purge_bridge_sessions_drops_only_own_entries() -> None:
    bridge_a = make_bridge("a", FakeClient())
    bridge_b = make_bridge("b", FakeClient())
    await SessionWaitService(bridge_a).handle("register", register_payload())
    await SessionWaitService(bridge_b).handle(
        "register",
        register_payload(waiter_id="w2", key="other:key", umo_scoped=False),
    )
    purge_bridge_sessions(bridge_a)
    assert list(bridge_sessions._REGISTRY) == ["other:key"]


@pytest.mark.asyncio
async def test_interceptor_claims_match_and_stops_event() -> None:
    from tests.unit.test_sdk_bridge import FakeCoreEvent

    client = FakeClient(
        matches=[{"waiter_id": "w1", "key": "webchat:FriendMessage:user-1"}]
    )
    service = SessionWaitService(make_bridge("a", client))
    await service.handle("register", register_payload())

    event = FakeCoreEvent()
    await bridge_sessions._session_wait_interceptor(event)
    assert event.is_stopped()
    assert [waiter_id for waiter_id, _ in client.matched] == ["w1"]
    # The entry survives a claim so the next turn can match again.
    assert "webchat:FriendMessage:user-1" in bridge_sessions._REGISTRY


@pytest.mark.asyncio
async def test_interceptor_skips_unrelated_umo() -> None:
    from tests.unit.test_sdk_bridge import FakeCoreEvent

    client = FakeClient(
        matches=[{"waiter_id": "w1", "key": "webchat:FriendMessage:user-1"}]
    )
    service = SessionWaitService(make_bridge("a", client))
    await service.handle("register", register_payload())

    event = FakeCoreEvent()
    event.unified_msg_origin = "webchat:GroupMessage:group-9"
    await bridge_sessions._session_wait_interceptor(event)
    assert not event.is_stopped()
    assert client.matched == []


@pytest.mark.asyncio
async def test_interceptor_without_match_leaves_event_alone() -> None:
    from tests.unit.test_sdk_bridge import FakeCoreEvent

    client = FakeClient(matches=[])
    service = SessionWaitService(make_bridge("a", client))
    await service.handle("register", register_payload())

    event = FakeCoreEvent()
    await bridge_sessions._session_wait_interceptor(event)
    assert not event.is_stopped()
    assert "webchat:FriendMessage:user-1" in bridge_sessions._REGISTRY
