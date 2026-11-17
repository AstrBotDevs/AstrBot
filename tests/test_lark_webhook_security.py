import asyncio
import base64
import hashlib
import json
from unittest.mock import AsyncMock

import pytest
from Crypto.Cipher import AES

from astrbot.core.platform.sources.lark.server import LarkWebhookServer


class FakeRequest:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def get_data(self) -> bytes:
        return self._body

    @property
    async def json(self) -> dict:
        return json.loads(self._body)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "headers",
    [
        {},
        {
            "X-Lark-Request-Timestamp": "1710000000",
            "X-Lark-Request-Nonce": "test-nonce",
        },
        {
            "X-Lark-Request-Timestamp": "1710000000",
            "X-Lark-Request-Nonce": "test-nonce",
            "X-Lark-Signature": "0" * 64,
        },
    ],
)
async def test_lark_webhook_rejects_missing_or_invalid_signature(headers):
    callback = AsyncMock()
    server = LarkWebhookServer(
        {
            "app_id": "test-app",
            "app_secret": "test-secret",
            "lark_encrypt_key": "test-encrypt-key",
            "lark_verification_token": "",
        },
        asyncio.Queue(),
    )
    server.set_callback(callback)

    result = await server.handle_callback(
        FakeRequest(b'{"header":{"event_type":"im.message.receive_v1"}}', headers)
    )

    assert result == ({"error": "Invalid signature"}, 401)
    callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_webhook_rejects_plaintext_when_encryption_is_configured():
    encrypt_key = "test-encrypt-key"
    timestamp = "1710000000"
    nonce = "test-nonce"
    body = b'{"header":{"event_type":"im.message.receive_v1"}}'
    signature = hashlib.sha256(
        (timestamp + nonce + encrypt_key).encode() + body
    ).hexdigest()
    callback = AsyncMock()
    server = LarkWebhookServer(
        {
            "app_id": "test-app",
            "app_secret": "test-secret",
            "lark_encrypt_key": encrypt_key,
            "lark_verification_token": "",
        },
        asyncio.Queue(),
    )
    server.set_callback(callback)

    result = await server.handle_callback(
        FakeRequest(
            body,
            {
                "X-Lark-Request-Timestamp": timestamp,
                "X-Lark-Request-Nonce": nonce,
                "X-Lark-Signature": signature,
            },
        )
    )

    assert result == ({"error": "Encrypted event required"}, 400)
    callback.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("with_signature", [True, False])
async def test_lark_webhook_enforces_signature_for_encrypted_events(with_signature):
    encrypt_key = "test-encrypt-key"
    event = {"header": {"event_type": "im.message.receive_v1"}}
    plaintext = json.dumps(event, separators=(",", ":")).encode()
    iv = b"0123456789abcdef"
    padding_length = AES.block_size - len(plaintext) % AES.block_size
    padded_plaintext = plaintext + bytes([padding_length]) * padding_length
    cipher = AES.new(hashlib.sha256(encrypt_key.encode()).digest(), AES.MODE_CBC, iv)
    encrypted = base64.b64encode(iv + cipher.encrypt(padded_plaintext)).decode()
    body = json.dumps({"encrypt": encrypted}, separators=(",", ":")).encode()
    timestamp = "1710000000"
    nonce = "test-nonce"
    signature = hashlib.sha256(
        (timestamp + nonce + encrypt_key).encode() + body
    ).hexdigest()
    callback = AsyncMock()
    server = LarkWebhookServer(
        {
            "app_id": "test-app",
            "app_secret": "test-secret",
            "lark_encrypt_key": encrypt_key,
            "lark_verification_token": "",
        },
        asyncio.Queue(),
    )
    server.set_callback(callback)

    headers = {}
    if with_signature:
        headers = {
            "X-Lark-Request-Timestamp": timestamp,
            "X-Lark-Request-Nonce": nonce,
            "X-Lark-Signature": signature,
        }
    result = await server.handle_callback(FakeRequest(body, headers))

    if with_signature:
        assert result == {}
        callback.assert_awaited_once_with(event)
    else:
        assert result == ({"error": "Invalid signature"}, 401)
        callback.assert_not_awaited()


@pytest.mark.asyncio
async def test_lark_webhook_accepts_unsigned_encrypted_url_verification():
    encrypt_key = "test-encrypt-key"
    event = {
        "challenge": "test-challenge",
        "token": "test-verification-token",
        "type": "url_verification",
    }
    plaintext = json.dumps(event, separators=(",", ":")).encode()
    iv = b"0123456789abcdef"
    padding_length = AES.block_size - len(plaintext) % AES.block_size
    padded_plaintext = plaintext + bytes([padding_length]) * padding_length
    cipher = AES.new(hashlib.sha256(encrypt_key.encode()).digest(), AES.MODE_CBC, iv)
    encrypted = base64.b64encode(iv + cipher.encrypt(padded_plaintext)).decode()
    body = json.dumps({"encrypt": encrypted}, separators=(",", ":")).encode()
    callback = AsyncMock()
    server = LarkWebhookServer(
        {
            "app_id": "test-app",
            "app_secret": "test-secret",
            "lark_encrypt_key": encrypt_key,
            "lark_verification_token": "",
        },
        asyncio.Queue(),
    )
    server.set_callback(callback)

    result = await server.handle_callback(FakeRequest(body))

    assert result == {"challenge": "test-challenge"}
    callback.assert_not_awaited()
