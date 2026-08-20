import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.sources.lark.server import LarkWebhookServer


class _FakeRequest:
    def __init__(
        self, body: bytes, event_data: dict, headers: dict | None = None
    ) -> None:
        self._body = body
        self._event_data = event_data
        self.headers = headers or {}

    async def get_data(self) -> bytes:
        return self._body

    @property
    async def json(self) -> dict:
        return self._event_data


@pytest.mark.asyncio
async def test_lark_webhook_rejects_missing_signature_headers_when_encrypt_key_enabled():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={},
        )
    )

    assert result == ({"error": "Missing signature headers"}, 401)


@pytest.mark.asyncio
async def test_lark_webhook_rejects_invalid_signature_when_encrypt_key_enabled():
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": "1",
                "X-Lark-Request-Nonce": "2",
                "X-Lark-Signature": "bad-signature",
            },
        )
    )

    assert result == ({"error": "Invalid signature"}, 401)


@pytest.mark.asyncio
async def test_lark_webhook_accepts_verified_request(monkeypatch: pytest.MonkeyPatch):
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )
    callback = AsyncMock()
    server.set_callback(callback)
    monkeypatch.setattr(server, "verify_signature", lambda *args: True)

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": "1",
                "X-Lark-Request-Nonce": "2",
                "X-Lark-Signature": "good-signature",
            },
        )
    )

    assert result == {}
    await asyncio.gather(*list(server._callback_tasks), return_exceptions=True)
    callback.assert_awaited_once_with({"type": "event_callback"})


@pytest.mark.asyncio
async def test_lark_webhook_returns_before_callback_finishes(
    monkeypatch: pytest.MonkeyPatch,
):
    server = LarkWebhookServer(
        {
            "app_id": "app-id",
            "app_secret": "secret",
            "lark_encrypt_key": "encrypt-key",
        },
        event_queue=SimpleNamespace(),
    )
    callback_started = asyncio.Event()
    release_callback = asyncio.Event()
    callback_finished = asyncio.Event()

    async def callback(_event_data: dict) -> None:
        callback_started.set()
        await release_callback.wait()
        callback_finished.set()

    server.set_callback(callback)
    monkeypatch.setattr(server, "verify_signature", lambda *args: True)

    result = await server.handle_callback(
        _FakeRequest(
            body=b"{}",
            event_data={"type": "event_callback"},
            headers={
                "X-Lark-Request-Timestamp": "1",
                "X-Lark-Request-Nonce": "2",
                "X-Lark-Signature": "good-signature",
            },
        )
    )

    assert result == {}
    await asyncio.wait_for(callback_started.wait(), timeout=1.0)
    assert not callback_finished.is_set()
    release_callback.set()
    await asyncio.gather(*list(server._callback_tasks), return_exceptions=True)
    assert callback_finished.is_set()
