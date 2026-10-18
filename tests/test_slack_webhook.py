import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.slack import client as slack_client
from astrbot.core.platform.sources.slack.client import SlackWebhookClient


@pytest.fixture
def webhook():
    queue = asyncio.Queue()
    client = SlackWebhookClient(
        AsyncMock(), "test-secret", event_handler=AsyncMock(side_effect=queue.put)
    )

    def request(event_id="Ev1"):
        body = json.dumps({"type": "event_callback", "event_id": event_id}).encode()
        signature = hmac.new(
            b"test-secret", b"v0:1700000000:" + body, hashlib.sha256
        ).hexdigest()
        return SimpleNamespace(
            get_data=AsyncMock(return_value=body),
            headers={
                "X-Slack-Request-Timestamp": "1700000000",
                "X-Slack-Signature": "v0=" + signature,
                "X-Slack-Retry-Num": "1",
                "X-Slack-Retry-Reason": "http_timeout",
            },
        )

    return client, queue, request


@pytest.mark.asyncio
async def test_slack_retry_does_not_enqueue_twice(webhook, monkeypatch):
    client, queue, request = webhook
    entered, release = asyncio.Event(), asyncio.Event()
    now = [0.0]
    monkeypatch.setattr(slack_client, "monotonic", lambda: now[0])

    async def slow_handler(event):
        entered.set()
        await release.wait()
        await queue.put(event)

    client.event_handler.side_effect = slow_handler
    first = asyncio.create_task(client.handle_callback(request()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert not first.done()
        # Pending work must not expire with the completed-event cache.
        now[0] = 700.0
        retry = await asyncio.wait_for(client.handle_callback(request()), timeout=1)
        assert retry.status_code == 503
        assert "x-slack-no-retry" not in retry.headers
        assert queue.empty()
        client.event_handler.assert_awaited_once()
    finally:
        release.set()
        result = await first

    assert result.status_code == 200
    assert (await client.handle_callback(request())).status_code == 200
    assert queue.qsize() == 1
    client.event_handler.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("failed"), asyncio.CancelledError()])
async def test_slack_failed_event_can_be_retried(webhook, error):
    client, queue, request = webhook
    client.event_handler.side_effect = error
    if isinstance(error, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await client.handle_callback(request())
    else:
        assert (await client.handle_callback(request())).status_code == 500
    assert queue.empty()

    client.event_handler.side_effect = queue.put
    assert (await client.handle_callback(request())).status_code == 200
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_slack_expiry_preserves_newer_events(webhook, monkeypatch):
    client, queue, request = webhook
    now = [0.0]
    monkeypatch.setattr(slack_client, "monotonic", lambda: now[0])

    async def slow_handler(event):
        now[0] = 700.0
        await queue.put(event)

    client.event_handler.side_effect = slow_handler
    assert (await client.handle_callback(request())).status_code == 200
    client.event_handler.side_effect = queue.put
    now[0] = 800.0
    assert (await client.handle_callback(request("Ev2"))).status_code == 200
    now[0] = 1299.0
    assert (await client.handle_callback(request())).status_code == 200
    assert queue.qsize() == 2
    now[0] = 1300.0
    assert (await client.handle_callback(request())).status_code == 200
    assert queue.qsize() == 3
    # Ev1 expires ten minutes after completion; Ev2 must still be deduplicated.
    assert (await client.handle_callback(request("Ev2"))).status_code == 200
    assert queue.qsize() == 3
