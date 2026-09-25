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
