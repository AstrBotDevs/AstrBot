import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.slack.client import SlackWebhookClient


class _FakeRequest:
    def __init__(self, body: bytes, headers: dict[str, str]) -> None:
        self._body = body
        self.headers = headers

    async def get_data(self) -> bytes:
        return self._body


@pytest.mark.asyncio
async def test_slack_webhook_rejects_stale_timestamp(monkeypatch: pytest.MonkeyPatch):
    body = json.dumps({"type": "event_callback"}).encode("utf-8")
    client = SlackWebhookClient(
        web_client=SimpleNamespace(),
        signing_secret="secret",
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.client.time.time",
        lambda: 2_000_000_000,
    )

    request = _FakeRequest(
        body,
        {
            "X-Slack-Request-Timestamp": str(2_000_000_000 - 301),
            "X-Slack-Signature": "v0=deadbeef",
        },
    )

    response = await client.handle_callback(request)

    assert response.status_code == 400
    assert response.body == b"Stale timestamp"


@pytest.mark.asyncio
async def test_slack_webhook_accepts_fresh_valid_signature(
    monkeypatch: pytest.MonkeyPatch,
):
    body = json.dumps({"type": "event_callback"}).encode("utf-8")
    handler = AsyncMock()
    client = SlackWebhookClient(
        web_client=SimpleNamespace(),
        signing_secret="secret",
        event_handler=handler,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.client.time.time",
        lambda: 2_000_000_000,
    )
    signature = (
        "v0="
        + hmac.new(
            b"secret",
            b'v0:2000000000:{"type": "event_callback"}',
            hashlib.sha256,
        ).hexdigest()
    )
    request = _FakeRequest(
        body,
        {
            "X-Slack-Request-Timestamp": str(2_000_000_000),
            "X-Slack-Signature": signature,
        },
    )

    response = await client.handle_callback(request)

    assert response.status_code == 200
    handler.assert_awaited_once_with({"type": "event_callback"})
