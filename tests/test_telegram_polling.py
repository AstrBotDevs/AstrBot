import asyncio
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from telegram.error import NetworkError, TimedOut
from telegram.ext._utils.networkloop import network_retry_loop
from telegram.request import HTTPXRequest

from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter
from astrbot.core.platform.sources.telegram.tg_request import TelegramPollingRequest
from tests.fixtures.helpers import make_platform_config


@pytest.mark.asyncio
@pytest.mark.parametrize("detect_pool_timeouts", [False, True])
async def test_pool_timeout_recovery_bypasses_sdk_error_callback(detect_pool_timeouts):
    recovery = asyncio.Event()
    request = (
        TelegramPollingRequest(recovery, 3)
        if detect_pool_timeouts
        else HTTPXRequest(connection_pool_size=1)
    )
    callback = Mock()
    async with request:
        with patch.object(
            request._client,
            "request",
            AsyncMock(side_effect=httpx.PoolTimeout("pool exhausted")),
        ) as send:

            async def poll():
                await request.do_request("https://example.invalid/getUpdates", "POST")

            with pytest.raises(TimedOut) as raised:
                await network_retry_loop(
                    action_cb=poll,
                    on_err_cb=callback,
                    description="polling recovery regression",
                    interval=0,
                    max_retries=2,
                )

    assert isinstance(raised.value.__cause__, httpx.PoolTimeout)
    assert send.await_count == 3
    callback.assert_not_called()
    assert recovery.is_set() is detect_pool_timeouts


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "interruption",
    [
        httpx.Response(200, json={"ok": True, "result": []}),
        httpx.ReadTimeout("read timeout"),
        httpx.ConnectTimeout("connect timeout"),
        httpx.ConnectError("connection failed"),
    ],
    ids=["empty-poll", "read-timeout", "connect-timeout", "network-error"],
)
async def test_pool_timeout_streak_is_reset(interruption):
    recovery = asyncio.Event()
    pool_timeout = httpx.PoolTimeout("pool exhausted")
    outcomes = [pool_timeout, pool_timeout, interruption, pool_timeout, pool_timeout]
    async with TelegramPollingRequest(recovery, 3) as request:
        with patch.object(request._client, "request", AsyncMock(side_effect=outcomes)):
            for outcome in outcomes:
                if isinstance(outcome, Exception):
                    with pytest.raises(NetworkError):
                        await request.do_request(
                            "https://example.invalid/getUpdates", "POST"
                        )
                else:
                    assert await request.do_request(
                        "https://example.invalid/getUpdates", "POST"
                    ) == (outcome.status_code, outcome.content)
                assert not recovery.is_set()


@pytest.mark.asyncio
async def test_pool_timeout_detection_preserves_cancellation():
    recovery = asyncio.Event()
    async with TelegramPollingRequest(recovery, 3) as request:
        with patch.object(
            request._client, "request", AsyncMock(side_effect=asyncio.CancelledError)
        ):
            with pytest.raises(asyncio.CancelledError):
                await request.do_request("https://example.invalid/getUpdates", "POST")
    assert not recovery.is_set()


@pytest.mark.asyncio
async def test_adapter_rebuilds_pool_and_receives_update(monkeypatch):
    clients = []
    polling_requests = []
    received = asyncio.Event()
    broken_pool_attempts = 0
    delivered_update = False

    def build_client(request):
        if isinstance(request, TelegramPollingRequest):
            polling_requests.append(request)
        broken_pool = len(polling_requests) == 1 and request is polling_requests[0]

        async def respond(http_request):
            nonlocal broken_pool_attempts, delivered_update
            method = http_request.url.path.rsplit("/", 1)[-1]
            if method == "getUpdates":
                if broken_pool:
                    broken_pool_attempts += 1
                    # Yield as a real pool acquisition would, allowing recovery to run.
                    await asyncio.sleep(0.01)
                    raise httpx.PoolTimeout("pool exhausted")
                if not delivered_update:
                    delivered_update = True
                    result = [
                        {
                            "update_id": 42,
                            "message": {
                                "message_id": 1,
                                "date": 0,
                                "chat": {"id": 123, "type": "private"},
                                "text": "recovered",
                            },
                        }
                    ]
                else:
                    await asyncio.sleep(0.01)
                    result = []
            elif method == "getMe":
                result = {
                    "id": 123456,
                    "is_bot": True,
                    "first_name": "Test",
                    "username": "test_bot",
                }
            else:
                assert method == "deleteWebhook"
                result = True
            return httpx.Response(200, json={"ok": True, "result": result})

        client = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        clients.append(client)
        return client

    async def receive(update, context):
        assert update.message.text == "recovered"
        received.set()

    monkeypatch.setattr(HTTPXRequest, "_build_client", build_client)
    monkeypatch.setattr(
        TelegramPlatformAdapter, "message_handler", AsyncMock(side_effect=receive)
    )
    adapter = TelegramPlatformAdapter(
        make_platform_config(
            "telegram",
            telegram_token="123456:TEST",
            telegram_command_register=False,
            telegram_command_auto_refresh=False,
            telegram_polling_restart_delay=0.1,
        ),
        {},
        asyncio.Queue(),
    )
    first_application = adapter.application
    task = asyncio.create_task(adapter.run())
    try:
        await asyncio.wait_for(received.wait(), timeout=5)
        assert broken_pool_attempts >= 3
        assert len(polling_requests) == 2
        assert adapter.application is not first_application
        assert not first_application.running
        assert not first_application.updater.running
        assert all(client.is_closed for client in clients[:2])
        assert not any(client.is_closed for client in clients[2:])
        assert adapter._consecutive_polling_failures == 0
    finally:
        await adapter.terminate()
        await asyncio.wait_for(task, timeout=5)
    assert len(polling_requests) == 2
    assert all(client.is_closed for client in clients)
