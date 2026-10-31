"""Regression coverage for Slack webhook request freshness."""

import hashlib
import hmac
import json
from unittest.mock import AsyncMock
from urllib.parse import urlencode

import pytest

from astrbot.core.platform.sources.slack.client import SlackWebhookClient


@pytest.mark.asyncio
@pytest.mark.parametrize("form_encoded", [False, True])
@pytest.mark.parametrize(
    ("timestamp", "expected_status"),
    [
        ("1700000000", 200),
        ("1699999700", 200),
        ("1700000300", 200),
        ("1699999699", 400),
        ("1700000301", 400),
        ("1600000000", 400),
        ("invalid", 400),
        ("1700000000.0", 400),
    ],
)
async def test_webhook_timestamp_window(
    monkeypatch: pytest.MonkeyPatch,
    timestamp: str,
    expected_status: int,
    form_encoded: bool,
) -> None:
    """Reject stale signed requests before dispatching their events."""
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.client.time.time", lambda: 1700000000
    )
    secret = "test-signing-secret"
    payload = {"type": "event_callback", "event": {"type": "app_mention"}}
    text = json.dumps(payload)
    body = (urlencode({"payload": text}) if form_encoded else text).encode()
    signature = (
        "v0="
        + hmac.new(
            secret.encode(), b"v0:" + timestamp.encode() + b":" + body, hashlib.sha256
        ).hexdigest()
    )
    request = AsyncMock()
    request.get_data.return_value = body
    request.headers = {
        "Content-Type": (
            "application/x-www-form-urlencoded" if form_encoded else "application/json"
        ),
        "X-Slack-Request-Timestamp": timestamp,
        "X-Slack-Signature": signature,
    }
    handler = AsyncMock()
    client = SlackWebhookClient(AsyncMock(), secret, event_handler=handler)

    response = await client.handle_callback(request)

    assert response.status_code == expected_status
    if expected_status == 200:
        handler.assert_awaited_once_with(payload)
    else:
        handler.assert_not_awaited()
