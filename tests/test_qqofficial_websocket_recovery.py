import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiohttp import web
from botpy import ConnectionSession

from astrbot.core.platform.sources.qqofficial.qqofficial_platform_adapter import (
    ManagedBotWebSocket,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("opcode", "data", "expected_opcode"),
    [(9, False, 2), (9, True, 6), (7, None, 6)],
)
async def test_gateway_control_recovers_through_the_sdk_receive_loop(
    opcode, data, expected_opcode
):
    token = SimpleNamespace(check_token=AsyncMock(), get_string=lambda: "test-token")
    session = {
        "session_id": "expired-session",
        "last_seq": 42,
        "intent": 1,
        "token": token,
        "shards": {"shard_id": 0, "shard_count": 1},
    }
    connection = ConnectionSession(
        max_async=1,
        connect=AsyncMock(),
        dispatch=lambda *args: None,
        loop=asyncio.get_running_loop(),
    )
    client = SimpleNamespace(is_shutting_down=False)
    payloads = []
    delivered = asyncio.Event()
    connection.parser["test_event"] = lambda msg: delivered.set()

    async def gateway(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"op": 10, "d": {"heartbeat_interval": 30000}})
        payloads.append(await ws.receive_json())
        if len(payloads) == 1:
            await ws.send_json({"op": opcode, "d": data})
        else:
            await ws.send_json({"op": 0, "t": "TEST_EVENT", "s": 43, "d": {}})
        # Keep the server open: the adapter must initiate recovery itself.
        async for _ in ws:
            pass
        return ws

    app = web.Application()
    app.router.add_get("/gateway", gateway)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    session["url"] = f"http://127.0.0.1:{runner.addresses[0][1]}/gateway"
    first = ManagedBotWebSocket(session, connection, client)
    second = None
    receive_task = None
    try:
        await asyncio.wait_for(first.ws_connect(), timeout=5)
        assert payloads[0]["op"] == 6
        assert len(connection._session_list) == 1
        recovered = connection._session_list.pop()
        assert recovered is session
        assert session["session_id"] == (
            "" if expected_opcode == 2 else "expired-session"
        )
        assert session["last_seq"] == (0 if expected_opcode == 2 else 42)

        second = ManagedBotWebSocket(recovered, connection, client)
        receive_task = asyncio.create_task(second.ws_connect())
        await asyncio.wait_for(delivered.wait(), timeout=5)
        assert payloads[1]["op"] == expected_opcode
        if expected_opcode == 6:
            assert payloads[1]["d"]["session_id"] == "expired-session"
            assert payloads[1]["d"]["seq"] == 42
        assert session["last_seq"] == 43

        # A late close/error must not enqueue the old socket a second time.
        await first.on_closed(1000, "late close")
        await first.on_error(ConnectionError("late error"))
        assert connection._session_list == []
    finally:
        client.is_shutting_down = True
        await first.close()
        if second is not None:
            await second.close()
        if receive_task is not None:
            receive_task.cancel()
            await asyncio.gather(receive_task, return_exceptions=True)
        await runner.cleanup()
    assert connection._session_list == []


@pytest.mark.asyncio
@pytest.mark.parametrize("close_code", [4006, 4007, 4009, 9001, 9005])
async def test_expired_gateway_close_requeues_a_fresh_session(close_code):
    session = {"session_id": "expired-session", "last_seq": 42}
    connection = SimpleNamespace(parser={}, add=lambda item: queued.append(item))
    queued = []
    socket = ManagedBotWebSocket(
        session, connection, SimpleNamespace(is_shutting_down=False)
    )

    await socket.on_closed(close_code, "session rejected")
    await socket.on_closed(close_code, "duplicate close")
    await socket.on_error(ConnectionError("late error"))

    assert queued == [session]
    assert session["session_id"] == ""
    assert session["last_seq"] == 0


@pytest.mark.asyncio
async def test_shutdown_does_not_queue_gateway_recovery():
    connection = SimpleNamespace(parser={}, add=lambda item: queued.append(item))
    queued = []
    socket = ManagedBotWebSocket(
        {"session_id": "old", "last_seq": 42},
        connection,
        SimpleNamespace(is_shutting_down=True),
    )
    ws = SimpleNamespace(close=AsyncMock(), close_code=1000)

    await socket.on_message(ws, json.dumps({"op": 9, "d": False}))
    await socket.on_closed(1000, "shutdown")
    await socket.on_error(ConnectionError("shutdown"))

    assert queued == []


@pytest.mark.asyncio
@pytest.mark.parametrize("close_code", [1000, 4004])
async def test_normal_close_preserves_resume_and_auth_failure_resets_token(close_code):
    token = SimpleNamespace(access_token="old-token")
    session = {"session_id": "live-session", "last_seq": 42, "token": token}
    queued = []
    connection = SimpleNamespace(parser={}, add=lambda item: queued.append(item))
    socket = ManagedBotWebSocket(
        session, connection, SimpleNamespace(is_shutting_down=False)
    )

    await socket.on_closed(close_code, "remote close")
    await socket.on_error(ConnectionError("late error"))

    assert queued == [session]
    assert session["session_id"] == "live-session"
    assert session["last_seq"] == 42
    assert token.access_token == (None if close_code == 4004 else "old-token")
