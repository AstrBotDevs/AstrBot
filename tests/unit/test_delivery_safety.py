"""Offline regression tests for the private delivery circuit breaker."""

import asyncio
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest
from aiocqhttp import CQHttp

from astrbot.core.platform.sources.aiocqhttp.delivery_safety import (
    DeliveryBlocked,
    DeliveryStore,
    SafeCQHttp,
)


def test_repeat_latches_across_restart_and_other_users_unaffected(tmp_path):
    path = tmp_path / "audit.db"
    store = DeliveryStore(path)
    for text in ["好的。", "好的！"]:
        store.reserve("p:FriendMessage:1", "send_private_msg", text, now=100)
    with pytest.raises(DeliveryBlocked):
        store.reserve("p:FriendMessage:1", "send_msg", "好的", now=101)
    restarted = DeliveryStore(path)
    with pytest.raises(DeliveryBlocked):
        restarted.reserve("p:FriendMessage:1", "send_msg", "换个问题？", now=99999)
    restarted.reserve("p:FriendMessage:2", "send_msg", "好的", now=102)
    assert restarted.page("p:FriendMessage:1")["items"][0]["status"] == "blocked"


def test_concurrent_burst_is_atomic(tmp_path):
    store = DeliveryStore(tmp_path / "audit.db")

    def send(index):
        try:
            store.reserve("u", "send_msg", f"[image:{index}]", now=100)
            return True
        except DeliveryBlocked:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        allowed = list(pool.map(send, range(40)))
    assert sum(allowed) == 20
    assert store.page("u")["total"] == 40


def test_sustained_limit_and_cursor_no_duplicates(tmp_path):
    store = DeliveryStore(tmp_path / "audit.db")
    for index in range(60):
        store.reserve("u", "send_msg", "[image]", now=index * 9)
    with pytest.raises(DeliveryBlocked):
        store.reserve("u", "send_msg", "[image]", now=541)
    first = store.page("u")
    second = store.page("u", first["items"][-1]["id"])
    assert len(first["items"]) == 50 and first["hasMore"]
    assert len(second["items"]) == 11 and not second["hasMore"]
    assert not {x["id"] for x in first["items"]} & {x["id"] for x in second["items"]}


def test_old_records_expire_from_counters(tmp_path):
    store = DeliveryStore(tmp_path / "audit.db")
    store.reserve("u", "send_msg", "hello", now=0)
    store.reserve("u", "send_msg", "hello", now=1)
    store.reserve("u", "send_msg", "hello", now=700)
    assert not store.blocked("u")


def test_existing_database_is_migrated_without_losing_rows(tmp_path):
    path = tmp_path / "audit.db"
    with sqlite3.connect(path) as db:
        db.executescript("""
            CREATE TABLE deliveries (
                id INTEGER PRIMARY KEY, umo TEXT NOT NULL, ts REAL NOT NULL,
                action TEXT NOT NULL, text TEXT NOT NULL, normalized TEXT NOT NULL,
                status TEXT NOT NULL, receipt TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT ''
            );
            INSERT INTO deliveries VALUES (1, 'u', 1, 'legacy', 'text', 'text', 'historical_prepared', '', '');
        """)

    item = DeliveryStore(path).page("u")["items"][0]

    assert item["id"] == 1
    assert item["direction"] == "outbound"
    assert item["params"] == {}


def test_inbound_is_visible_with_safe_params_and_not_counted_as_send(tmp_path):
    store = DeliveryStore(tmp_path / "audit.db")
    store.reserve("u", "send_msg", "hello", now=100)
    for index in range(20):
        store.record_inbound(
            "u",
            f"incoming {index}",
            {
                "user_id": 1,
                "access_token": "secret-value",
                "message": [{"type": "image", "data": {"file": "base64://abc"}}],
            },
            blocked=False,
            now=100 + index,
        )
    store.reserve("u", "send_msg", "hello!", now=121)
    with pytest.raises(DeliveryBlocked):
        store.reserve("u", "send_msg", "hello.", now=122)

    inbound = next(
        item for item in store.page("u")["items"] if item["direction"] == "inbound"
    )
    assert inbound["status"] == "received"
    assert inbound["params"]["access_token"] == "<redacted>"
    assert "base64 omitted" in inbound["params"]["message"][0]["data"]["file"]


def test_outbound_parameters_are_retained_and_redacted(tmp_path):
    store = DeliveryStore(tmp_path / "audit.db")
    store.reserve(
        "u",
        "send_msg",
        "hello",
        now=1,
        params={"user_id": 1, "password": "nope", "message": "hello"},
    )

    item = store.page("u")["items"][0]
    assert item["direction"] == "outbound"
    assert item["params"] == {
        "user_id": 1,
        "password": "<redacted>",
        "message": "hello",
    }


@pytest.mark.parametrize(
    "action",
    [
        "send_private_msg",
        "send_msg",
        "send_private_forward_msg",
        "send_private_msg_async",
    ],
)
def test_client_receipts_and_no_network_after_trip(tmp_path, monkeypatch, action):
    client = object.__new__(SafeCQHttp)
    client.delivery_platform_id = "test"
    client.delivery_store = DeliveryStore(tmp_path / "audit.db")
    api = AsyncMock(return_value={"message_id": 123})
    monkeypatch.setattr(CQHttp, "call_action", api)

    async def scenario():
        for _ in range(2):
            await client.call_action(action, user_id=1, message="重复回复")
        with pytest.raises(DeliveryBlocked):
            await client.call_action(action, user_id=1, message="重复回复")
        assert api.await_count == 2
        rows = client.delivery_store.page("test:FriendMessage:1")["items"]
        assert [row["status"] for row in rows] == ["blocked", "accepted", "accepted"]
        assert rows[1]["receipt"] == "123"
        await client.call_action("send_group_msg", group_id=1, message="群聊")
        assert api.await_count == 3

    asyncio.run(scenario())


def test_failed_call_not_reported_delivered(tmp_path, monkeypatch):
    client = object.__new__(SafeCQHttp)
    client.delivery_platform_id = "test"
    client.delivery_store = DeliveryStore(tmp_path / "audit.db")
    monkeypatch.setattr(CQHttp, "call_action", AsyncMock(side_effect=TimeoutError))
    with pytest.raises(TimeoutError):
        asyncio.run(client.call_action("send_msg", user_id=1, message="请求"))
    assert (
        client.delivery_store.page("test:FriendMessage:1")["items"][0]["status"]
        == "uncertain"
    )


def test_pre_send_recheck_blocks_before_network(tmp_path, monkeypatch):
    client = object.__new__(SafeCQHttp)
    client.delivery_platform_id = "test"
    client.delivery_store = DeliveryStore(tmp_path / "audit.db")
    original_blocked = client.delivery_store.blocked
    checks = 0

    def latch_after_reservation(umo):
        nonlocal checks
        checks += 1
        if checks == 1:
            with client.delivery_store.connect() as db:
                db.execute("INSERT INTO circuits VALUES (?, ?, ?)", (umo, 1, "test"))
        return original_blocked(umo)

    monkeypatch.setattr(client.delivery_store, "blocked", latch_after_reservation)
    api = AsyncMock(return_value={"message_id": 123})
    monkeypatch.setattr(CQHttp, "call_action", api)

    with pytest.raises(DeliveryBlocked):
        asyncio.run(client.call_action("send_msg", user_id=1, message="request"))

    api.assert_not_awaited()
    item = client.delivery_store.page("test:FriendMessage:1")["items"][0]
    assert item["status"] == "blocked"


@pytest.mark.asyncio
async def test_idle_private_locks_are_reclaimed(tmp_path, monkeypatch):
    """Reclaim idle locks after each distinct contact finishes sending.

    Args:
        tmp_path: Isolated audit database directory.
        monkeypatch: Scoped replacement of the network transport.
    """
    client = object.__new__(SafeCQHttp)
    client.delivery_platform_id = "test"
    client.delivery_store = DeliveryStore(tmp_path / "audit.db")
    monkeypatch.setattr(
        CQHttp, "call_action", AsyncMock(return_value={"message_id": 1})
    )
    for user_id in range(1, 51):
        await client.call_action("send_private_msg", user_id=user_id, message="hello")
        assert len(client._delivery_locks) == 0


@pytest.mark.asyncio
async def test_waiter_cancellation_keeps_one_shared_send_lock(tmp_path, monkeypatch):
    """Canceling one waiter must not create a second concurrent lock.

    Args:
        tmp_path: Isolated audit database directory.
        monkeypatch: Scoped replacement of the network transport.
    """
    client = object.__new__(SafeCQHttp)
    client.delivery_platform_id = "test"
    client.delivery_store = DeliveryStore(tmp_path / "audit.db")
    entered = asyncio.Event()
    release = asyncio.Event()
    active = 0
    maximum = 0

    async def network(*args, **kwargs):
        """Hold transport calls until the test releases their shared gate.

        Args:
            args: Unused action arguments.
            kwargs: Unused action parameters.

        Returns:
            A confirmed simulated platform receipt.
        """
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        entered.set()
        try:
            await release.wait()
            return {"message_id": 1}
        finally:
            active -= 1

    monkeypatch.setattr(CQHttp, "call_action", network)
    first = asyncio.create_task(
        client.call_action("send_private_msg", user_id=1, message="alpha")
    )
    await asyncio.wait_for(entered.wait(), 2)
    second = asyncio.create_task(
        client.call_action("send_private_msg", user_id=1, message="beta")
    )
    third = asyncio.create_task(
        client.call_action("send_private_msg", user_id=1, message="gamma")
    )
    await asyncio.sleep(0)
    assert len(client._delivery_locks) == 1
    second.cancel()
    with pytest.raises(asyncio.CancelledError):
        await second
    assert len(client._delivery_locks) == 1
    release.set()
    await asyncio.gather(first, third)
    assert maximum == 1
    assert len(client._delivery_locks) == 0


@pytest.mark.asyncio
async def test_audit_failure_still_prevents_outbound_network(monkeypatch):
    """Keep outgoing reservations mandatory when persistence fails.

    Args:
        monkeypatch: Scoped replacement of audit persistence and transport.
    """
    from types import SimpleNamespace
    from unittest.mock import Mock

    client = object.__new__(SafeCQHttp)
    client.delivery_platform_id = "test"
    client.delivery_store = SimpleNamespace(
        reserve=Mock(side_effect=sqlite3.OperationalError("locked"))
    )
    network = AsyncMock()
    monkeypatch.setattr(CQHttp, "call_action", network)
    with pytest.raises(sqlite3.OperationalError):
        await client.call_action("send_private_msg", user_id=1, message="hello")
    network.assert_not_awaited()


@pytest.mark.parametrize(
    ("lookup_error", "blocked", "record_error", "routed"),
    [
        (sqlite3.OperationalError("locked"), False, None, True),
        (OSError("unavailable"), False, None, True),
        (None, False, sqlite3.OperationalError("locked"), True),
        (None, True, sqlite3.OperationalError("locked"), False),
        (None, False, None, True),
    ],
)
@pytest.mark.asyncio
async def test_inbound_routing_survives_audit_failures(
    monkeypatch, lookup_error, blocked, record_error, routed
):
    """Separate inbound routing from audit errors without bypassing known circuits.

    Args:
        monkeypatch: Scoped replacement of the platform client.
        lookup_error: Optional circuit lookup failure.
        blocked: Circuit state returned by a successful lookup.
        record_error: Optional inbound persistence failure.
        routed: Whether message conversion and dispatch should run.
    """
    from types import SimpleNamespace
    from unittest.mock import Mock

    from astrbot.core.platform.sources.aiocqhttp import (
        aiocqhttp_platform_adapter as module,
    )

    handlers = {}
    store = SimpleNamespace(
        blocked=Mock(return_value=blocked, side_effect=lookup_error),
        record_inbound=Mock(side_effect=record_error),
    )
    bot = SimpleNamespace(
        delivery_store=store,
        on_request=lambda: lambda fn: fn,
        on_notice=lambda: lambda fn: fn,
        on_message=lambda kind: lambda fn: handlers.setdefault(kind, fn),
        on_websocket_connection=lambda fn: fn,
    )
    monkeypatch.setattr(module, "SafeCQHttp", lambda **kwargs: bot)
    adapter = module.AiocqhttpAdapter(
        {"id": "test", "ws_reverse_host": "127.0.0.1", "ws_reverse_port": 1},
        {},
        asyncio.Queue(),
    )
    adapter.convert_message = AsyncMock(return_value=object())
    adapter.handle_msg = AsyncMock()
    event = {"user_id": 1, "raw_message": "hello"}
    await handlers["private"](event)
    assert adapter.convert_message.await_count == int(routed)
    assert adapter.handle_msg.await_count == int(routed)
    if lookup_error:
        store.record_inbound.assert_not_called()
