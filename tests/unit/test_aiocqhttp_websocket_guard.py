import asyncio
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.aiocqhttp.guarded_cqhttp import GuardedCQHttp


def make_guard(timeout: float = 60.0) -> GuardedCQHttp:
    guard = object.__new__(GuardedCQHttp)
    guard.ws_receive_timeout_sec = timeout
    guard.connection_label = "test-adapter"
    guard._wsr_api_clients = {}
    guard._wsr_event_clients = set()
    return guard


@pytest.mark.asyncio
async def test_receive_payload_accepts_valid_json_object():
    guard = make_guard()
    ws = AsyncMock()
    ws.receive.return_value = '{"post_type":"meta_event"}'

    connected, payload = await guard._receive_payload(ws)

    assert connected is True
    assert payload == {"post_type": "meta_event"}
    ws.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_receive_payload_ignores_non_object_json():
    guard = make_guard()
    ws = AsyncMock()
    ws.receive.return_value = "[]"

    connected, payload = await guard._receive_payload(ws)

    assert connected is True
    assert payload is None


@pytest.mark.asyncio
async def test_receive_payload_can_disable_idle_timeout():
    guard = make_guard(timeout=0)
    ws = AsyncMock()

    async def delayed_payload():
        await asyncio.sleep(0.01)
        return '{"post_type":"meta_event"}'

    ws.receive.side_effect = delayed_payload

    connected, payload = await guard._receive_payload(ws)

    assert connected is True
    assert payload == {"post_type": "meta_event"}
    ws.close.assert_not_awaited()


@pytest.mark.asyncio
async def test_receive_payload_closes_connection_after_timeout():
    guard = make_guard(timeout=0.01)
    ws = AsyncMock()

    async def wait_forever():
        await asyncio.Event().wait()

    ws.receive.side_effect = wait_forever

    connected, payload = await guard._receive_payload(ws)

    assert connected is False
    assert payload is None
    ws.close.assert_awaited_once_with(code=1011, reason="Inbound frame timeout")


@pytest.mark.asyncio
async def test_close_ws_accepts_synchronous_close_implementation():
    guard = make_guard()

    class SyncCloseWebSocket:
        def __init__(self):
            self.closed_with = None

        def close(self, *, code, reason):
            self.closed_with = (code, reason)

    ws = SyncCloseWebSocket()

    await guard._close_ws(ws, code=1000, reason="test close")

    assert ws.closed_with == (1000, "test close")


@pytest.mark.asyncio
async def test_new_api_connection_replaces_and_closes_previous_connection():
    guard = make_guard()
    previous = AsyncMock()
    current = AsyncMock()
    guard._wsr_api_clients["self-id"] = previous

    await guard._register_api_client("self-id", current)

    assert guard._wsr_api_clients["self-id"] is current
    previous.close.assert_awaited_once_with(
        code=1000,
        reason="Replaced by new connection",
    )


def test_old_connection_cleanup_does_not_remove_new_mapping():
    guard = make_guard()
    previous = object()
    current = object()
    guard._wsr_api_clients["self-id"] = current

    guard._remove_api_client("self-id", previous)

    assert guard._wsr_api_clients["self-id"] is current


def test_current_connection_cleanup_removes_its_mapping():
    guard = make_guard()
    current = object()
    guard._wsr_api_clients["self-id"] = current

    guard._remove_api_client("self-id", current)

    assert "self-id" not in guard._wsr_api_clients
