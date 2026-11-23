import asyncio
import json
from unittest.mock import Mock

import botpy
import pytest

from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
    _SIGNATURE_HEADER,
    _SIGNATURE_TIMESTAMP_HEADER,
    QQOfficialWebhook,
    _sign_qq_webhook_payload,
    _verify_qq_webhook_signature,
)
from tests.test_platform_regressions import make_webhook_request


def test_qq_webhook_signature_verification_accepts_valid_signature():
    secret = "test-secret"
    timestamp = "1710000000"
    body = b'{"op":12,"d":0}'
    signature = _sign_qq_webhook_payload(secret, timestamp, body)

    assert _verify_qq_webhook_signature(secret, timestamp, signature, body)


def test_qq_webhook_signature_verification_rejects_tampered_body():
    secret = "test-secret"
    timestamp = "1710000000"
    body = b'{"op":12,"d":0}'
    signature = _sign_qq_webhook_payload(secret, timestamp, body)

    assert not _verify_qq_webhook_signature(
        secret,
        timestamp,
        signature,
        b'{"op":12,"d":1}',
    )


@pytest.mark.asyncio
async def test_qq_webhook_callback_rejects_missing_signature():
    webhook = object.__new__(QQOfficialWebhook)
    webhook.secret = "test-secret"

    result = await webhook.handle_callback(make_webhook_request(b'{"op":12,"d":0}'))

    assert result == ({"error": "Invalid signature"}, 401)


@pytest.mark.asyncio
async def test_qq_webhook_callback_accepts_unsigned_validation():
    secret = "test-secret"
    event_ts = "1710000000"
    plain_token = "plain-token"
    body = json.dumps(
        {"op": 13, "d": {"event_ts": event_ts, "plain_token": plain_token}},
        separators=(",", ":"),
    ).encode("utf-8")
    webhook = object.__new__(QQOfficialWebhook)
    webhook.secret = secret

    result = await webhook.handle_callback(make_webhook_request(body))

    assert result == {
        "plain_token": plain_token,
        "signature": _sign_qq_webhook_payload(secret, event_ts, plain_token.encode()),
    }


@pytest.mark.asyncio
async def test_qq_webhook_callback_lazily_creates_botpy_connection():
    secret = "test-secret"
    timestamp = "1710000000"
    body = json.dumps(
        {"op": 0, "t": "UNKNOWN_EVENT", "id": "event-id", "d": {"id": "message-id"}},
        separators=(",", ":"),
    ).encode("utf-8")
    signature = _sign_qq_webhook_payload(secret, timestamp, body)
    webhook = QQOfficialWebhook(
        {"appid": "123", "secret": secret},
        asyncio.Queue(),
        Mock(spec=botpy.Client, api=None, http=None),
    )

    result = await webhook.handle_callback(
        make_webhook_request(
            body,
            {
                _SIGNATURE_TIMESTAMP_HEADER: timestamp,
                _SIGNATURE_HEADER: signature,
            },
        )
    )

    assert result == {"opcode": 12}
    assert webhook._connection is not None
    assert webhook.http._token is not None
    assert webhook.http._token.app_id == "123"
    assert webhook.client.api is webhook.api
    assert webhook.client.http is webhook.http
