"""Authentication tests for the Lark unified webhook server."""

from __future__ import annotations

import hashlib
import json
import time

import pytest

from astrbot.core.platform.sources.lark.server import LarkWebhookServer


class _Request:
    def __init__(self, payload: dict, headers: dict[str, str]) -> None:
        self._payload = payload
        self._body = json.dumps(payload, separators=(",", ":")).encode()
        self.headers = headers

    async def get_data(self) -> bytes:
        return self._body

    @property
    async def json(self) -> dict:
        return self._payload


def _signed_request(payload: dict, *, nonce: str = "nonce") -> _Request:
    timestamp = str(int(time.time()))
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hashlib.sha256(
        timestamp.encode() + nonce.encode() + b"encrypt-key" + body
    ).hexdigest()
    return _Request(
        payload,
        {
            "X-Lark-Request-Timestamp": timestamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature,
        },
    )


@pytest.mark.asyncio
async def test_missing_signature_headers_are_rejected() -> None:
    called = False
    server = LarkWebhookServer(
        {
            "app_id": "id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
            "lark_verification_token": "verify-token",
        },
        None,
    )

    async def callback(_payload):
        nonlocal called
        called = True

    server.set_callback(callback)
    result = await server.handle_callback(
        _Request({"header": {"token": "verify-token"}}, {})
    )
    assert result[1] == 401
    assert called is False


@pytest.mark.asyncio
async def test_valid_signature_and_token_reach_callback() -> None:
    received = []
    server = LarkWebhookServer(
        {
            "app_id": "id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
            "lark_verification_token": "verify-token",
        },
        None,
    )

    async def callback(payload):
        received.append(payload)

    server.set_callback(callback)
    payload = {"header": {"token": "verify-token", "event_id": "event"}}
    result = await server.handle_callback(_signed_request(payload))
    assert result == {}
    assert received == [payload]


@pytest.mark.asyncio
async def test_signed_request_cannot_be_replayed() -> None:
    server = LarkWebhookServer(
        {
            "app_id": "id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
            "lark_verification_token": "verify-token",
        },
        None,
    )
    async def callback(_payload):
        return None

    server.set_callback(callback)
    request = _signed_request({"header": {"token": "verify-token"}})
    await server.handle_callback(request)
    replay = await server.handle_callback(request)
    assert replay[1] == 401


@pytest.mark.asyncio
async def test_webhook_without_verification_token_is_rejected() -> None:
    server = LarkWebhookServer(
        {"app_id": "id", "app_secret": "secret"},
        None,
    )
    result = await server.handle_callback(_Request({"header": {}}, {}))
    assert result[1] == 401
