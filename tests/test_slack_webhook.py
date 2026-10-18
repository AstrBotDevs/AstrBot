import asyncio
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.slack import client as slack_client
from astrbot.core.platform.sources.slack.client import SlackWebhookClient
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from tests.fixtures.helpers import make_platform_config


@pytest.fixture
def slack_webhook():
    queue = asyncio.Queue()
    adapter = SlackAdapter(
        make_platform_config(
            "slack",
            bot_token="xoxb-test",
            signing_secret="test-secret",
            slack_connection_mode="webhook",
        ),
        {},
        queue,
    )
    adapter.bot_self_id = "UBOT"
    adapter.web_client.users_info = AsyncMock(
        return_value={"user": {"real_name": "Tester"}}
    )
    adapter.web_client.conversations_info = AsyncMock(
        return_value={"channel": {"is_im": True}}
    )
    client = SlackWebhookClient(
        adapter.web_client,
        "test-secret",
        event_handler=adapter._handle_webhook_event,
    )
    adapter.webhook_client = client
    return adapter, client, queue


@pytest.fixture
def signed_request():
    def build(event_id="Ev1", *, retry=False, payload=None):
        if payload is None:
            payload = {
                "type": "event_callback",
                "event_id": event_id,
                "event": {
                    "type": "message",
                    "user": "UTEST",
                    "channel": "DTEST",
                    "text": "hello",
                    "client_msg_id": "message-1",
                    "ts": "1700000000.000001",
                },
            }
        body = json.dumps(payload).encode()
        timestamp = "1700000000"
        signature = (
            "v0="
            + hmac.new(
                b"test-secret",
                b"v0:" + timestamp.encode() + b":" + body,
                hashlib.sha256,
            ).hexdigest()
        )
        headers = {
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": signature,
        }
        if retry:
            headers.update(
                {"X-Slack-Retry-Num": "1", "X-Slack-Retry-Reason": "http_timeout"}
            )
        return SimpleNamespace(get_data=AsyncMock(return_value=body), headers=headers)

    return build


@pytest.mark.asyncio
async def test_slack_retry_while_processing_and_after_enqueue(
    slack_webhook, signed_request, monkeypatch
):
    adapter, _, queue = slack_webhook
    callback = adapter.webhook_callback
    entered = asyncio.Event()
    release = asyncio.Event()
    now = [0.0]
    monkeypatch.setattr(slack_client, "monotonic", lambda: now[0])

    async def slow_user_lookup(**kwargs):
        entered.set()
        await release.wait()
        return {"user": {"real_name": "Tester"}}

    adapter.web_client.users_info.side_effect = slow_user_lookup
    first = asyncio.create_task(callback(signed_request()))
    try:
        await asyncio.wait_for(entered.wait(), timeout=1)
        assert not first.done()
        assert queue.empty()
        # Pending work must not expire, even if it exceeds the completed-event TTL.
        now[0] = 700.0
        retry = await asyncio.wait_for(callback(signed_request(retry=True)), timeout=1)
        assert retry.status_code == 503
        assert "x-slack-no-retry" not in retry.headers
        assert queue.empty()
        adapter.web_client.users_info.assert_awaited_once()
    finally:
        release.set()
        result = await first

    assert result.status_code == 200
    assert queue.qsize() == 1
    assert (await callback(signed_request(retry=True))).status_code == 200
    assert queue.qsize() == 1
    adapter.web_client.users_info.assert_awaited_once()
    assert queue.get_nowait().message_obj.message_id == "message-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [RuntimeError("failed"), asyncio.CancelledError()])
async def test_slack_failed_event_can_be_retried(slack_webhook, signed_request, error):
    adapter, client, queue = slack_webhook
    original = adapter.handle_msg
    adapter.handle_msg = AsyncMock(side_effect=error)
    if isinstance(error, asyncio.CancelledError):
        with pytest.raises(asyncio.CancelledError):
            await client.handle_callback(signed_request())
    else:
        assert (await client.handle_callback(signed_request())).status_code == 500
    assert queue.empty()

    adapter.handle_msg = original
    assert (await client.handle_callback(signed_request(retry=True))).status_code == 200
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_slack_completed_event_expires_ten_minutes_after_enqueue(
    slack_webhook, signed_request, monkeypatch
):
    adapter, client, queue = slack_webhook
    now = [0.0]
    monkeypatch.setattr(slack_client, "monotonic", lambda: now[0])

    async def slow_user_lookup(**kwargs):
        now[0] = 700.0
        return {"user": {"real_name": "Tester"}}

    adapter.web_client.users_info.side_effect = slow_user_lookup
    assert (await client.handle_callback(signed_request())).status_code == 200
    adapter.web_client.users_info.side_effect = None
    now[0] = 800.0
    assert (await client.handle_callback(signed_request("Ev2"))).status_code == 200
    now[0] = 1299.0
    assert (await client.handle_callback(signed_request())).status_code == 200
    assert queue.qsize() == 2
    now[0] = 1300.0
    assert (await client.handle_callback(signed_request())).status_code == 200
    assert queue.qsize() == 3
    # Expiring Ev1 must preserve Ev2 until its own ten-minute window ends.
    assert (await client.handle_callback(signed_request("Ev2"))).status_code == 200
    assert queue.qsize() == 3


@pytest.mark.asyncio
async def test_slack_new_event_with_retry_header_is_not_dropped(
    slack_webhook, signed_request
):
    _, client, queue = slack_webhook
    for event_id in ("Ev1", "Ev2"):
        assert (
            await client.handle_callback(signed_request(event_id, retry=True))
        ).status_code == 200
    assert queue.qsize() == 2


@pytest.mark.asyncio
async def test_slack_signature_is_checked_before_deduplication(
    slack_webhook, signed_request
):
    _, client, queue = slack_webhook
    for _ in range(2):
        invalid = signed_request()
        invalid.headers["X-Slack-Signature"] = "v0=invalid"
        assert (await client.handle_callback(invalid)).status_code == 400
        assert (await client.handle_callback(signed_request())).status_code == 200
    assert queue.qsize() == 1


@pytest.mark.asyncio
async def test_slack_url_verification_does_not_require_event_id(
    slack_webhook, signed_request
):
    _, client, queue = slack_webhook
    result = await client.handle_callback(
        signed_request(payload={"type": "url_verification", "challenge": "challenge"})
    )
    assert result == {"challenge": "challenge"}
    assert queue.empty()


@pytest.mark.asyncio
async def test_slack_rejects_missing_event_id(slack_webhook, signed_request):
    adapter, client, queue = slack_webhook
    assert (await client.handle_callback(signed_request(None))).status_code == 400
    assert queue.empty()
    adapter.web_client.users_info.assert_not_awaited()
