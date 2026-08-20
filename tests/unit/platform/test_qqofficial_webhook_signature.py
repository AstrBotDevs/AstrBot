import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from astrbot.core.platform.astrbot_message import AstrBotMessage
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter import (
    QQOfficialWebhookPlatformAdapter,
)
from astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_server import (
    _SIGNATURE_HEADER,
    _SIGNATURE_TIMESTAMP_HEADER,
    QQOfficialWebhook,
    _sign_qq_webhook_payload,
    _verify_qq_webhook_signature,
)


class FakeRequest:
    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._body = body
        self.headers = headers or {}

    async def get_data(self) -> bytes:
        return self._body


class FakeBotpyClient:
    api = None
    http = None

    def ws_dispatch(self, *_args, **_kwargs) -> None:
        return None


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
async def test_qq_webhook_callback_rejects_invalid_json_body():
    webhook = object.__new__(QQOfficialWebhook)
    webhook.secret = "test-secret"

    result = await webhook.handle_callback(FakeRequest(b"{not-json"))

    assert result == ({"error": "Invalid JSON"}, 400)


@pytest.mark.asyncio
async def test_qq_webhook_callback_rejects_non_object_json():
    webhook = object.__new__(QQOfficialWebhook)
    webhook.secret = "test-secret"

    result = await webhook.handle_callback(FakeRequest(b"[1,2,3]"))

    assert result == ({"error": "Invalid JSON"}, 400)


@pytest.mark.asyncio
async def test_qq_webhook_callback_rejects_missing_signature():
    webhook = object.__new__(QQOfficialWebhook)
    webhook.secret = "test-secret"

    result = await webhook.handle_callback(FakeRequest(b'{"op":12,"d":0}'))

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

    result = await webhook.handle_callback(FakeRequest(body))

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
        FakeBotpyClient(),
    )

    result = await webhook.handle_callback(
        FakeRequest(
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


@pytest.mark.asyncio
async def test_qq_webhook_callback_deduplicates_retried_dispatch_event():
    secret = "test-secret"
    timestamp = "1710000000"
    dispatched: list[dict] = []
    body = json.dumps(
        {"op": 0, "t": "MESSAGE_CREATE", "id": "event-id", "d": {"id": "message-id"}},
        separators=(",", ":"),
    ).encode("utf-8")
    signature = _sign_qq_webhook_payload(secret, timestamp, body)
    webhook = QQOfficialWebhook(
        {"appid": "123", "secret": secret},
        asyncio.Queue(),
        FakeBotpyClient(),
    )
    webhook._connection = SimpleNamespace(
        parser={"message_create": lambda msg: dispatched.append(msg)}
    )

    headers = {
        _SIGNATURE_TIMESTAMP_HEADER: timestamp,
        _SIGNATURE_HEADER: signature,
    }
    first = await webhook.handle_callback(FakeRequest(body, headers))
    second = await webhook.handle_callback(FakeRequest(body, headers))

    assert first == {"opcode": 12}
    assert second == {"opcode": 12}
    assert dispatched == [json.loads(body.decode("utf-8"))]


@pytest.mark.asyncio
async def test_qq_webhook_callback_caches_extra_data_for_known_dispatch_event():
    secret = "test-secret"
    timestamp = "1710000000"
    dispatched: list[dict] = []
    payload = {
        "op": 0,
        "t": "MESSAGE_CREATE",
        "id": "event-id",
        "d": {
            "id": "message-id",
            "author": {"union_openid": "union-1"},
            "message_scene": "friend",
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _sign_qq_webhook_payload(secret, timestamp, body)
    webhook = QQOfficialWebhook(
        {"appid": "123", "secret": secret},
        asyncio.Queue(),
        FakeBotpyClient(),
    )
    webhook._connection = SimpleNamespace(
        parser={"message_create": lambda msg: dispatched.append(msg)}
    )

    result = await webhook.handle_callback(
        FakeRequest(
            body,
            {
                _SIGNATURE_TIMESTAMP_HEADER: timestamp,
                _SIGNATURE_HEADER: signature,
            },
        )
    )

    assert result == {"opcode": 12}
    assert dispatched == [payload]
    assert webhook.pop_extra_data("message-id") == {
        "union_openid": "union-1",
        "message_scene": "friend",
    }
    assert webhook.pop_extra_data("message-id") == {}


@pytest.mark.asyncio
async def test_qq_webhook_callback_clears_cached_extra_data_for_unknown_parser_event():
    secret = "test-secret"
    timestamp = "1710000000"
    payload = {
        "op": 0,
        "t": "UNKNOWN_EVENT",
        "id": "event-id",
        "d": {
            "id": "message-id",
            "author": {"union_openid": "union-1"},
            "message_scene": "group",
        },
    }
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    signature = _sign_qq_webhook_payload(secret, timestamp, body)
    webhook = QQOfficialWebhook(
        {"appid": "123", "secret": secret},
        asyncio.Queue(),
        FakeBotpyClient(),
    )
    webhook._connection = SimpleNamespace(parser={})

    result = await webhook.handle_callback(
        FakeRequest(
            body,
            {
                _SIGNATURE_TIMESTAMP_HEADER: timestamp,
                _SIGNATURE_HEADER: signature,
            },
        )
    )

    assert result == {"opcode": 12}
    assert webhook.pop_extra_data("message-id") == {}


@pytest.mark.asyncio
async def test_qqofficial_webhook_create_event_populates_webhook_extra_data():
    adapter = QQOfficialWebhookPlatformAdapter(
        {
            "id": "qq-official-webhook-test",
            "appid": "123",
            "secret": "secret",
        },
        {},
        asyncio.Queue(),
    )
    adapter.webhook_helper = SimpleNamespace(
        pop_extra_data=lambda message_id: {
            "webhook_trace_id": f"trace-{message_id}",
            "webhook_retry": True,
        }
    )

    message = AstrBotMessage()
    message.type = MessageType.FRIEND_MESSAGE
    message.message_id = "msg-123"
    message.session_id = "friend-1"
    message.message = []
    message.message_str = "hello"
    message.sender = SimpleNamespace(user_id="user-1", nickname="tester")
    message.raw_message = None

    event = adapter.create_event(message)

    assert event.get_extra("webhook_trace_id") == "trace-msg-123"
    assert event.get_extra("webhook_retry") is True
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"


@pytest.mark.asyncio
async def test_qqofficial_webhook_callback_returns_500_when_helper_missing():
    adapter = QQOfficialWebhookPlatformAdapter(
        {
            "id": "qq-official-webhook-test",
            "appid": "123",
            "secret": "secret",
        },
        {},
        asyncio.Queue(),
    )

    result = await adapter.webhook_callback(object())

    assert result == ({"error": "Webhook helper not initialized"}, 500)


@pytest.mark.asyncio
async def test_qqofficial_webhook_run_uses_unified_mode_wait_instead_of_polling(
    monkeypatch,
):
    shutdown_event = asyncio.Event()
    helper = SimpleNamespace(
        initialize=AsyncMock(),
        start_polling=AsyncMock(),
        shutdown_event=shutdown_event,
    )

    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter.QQOfficialWebhook",
        lambda *args, **kwargs: helper,
    )

    adapter = QQOfficialWebhookPlatformAdapter(
        {
            "id": "qq-official-webhook-test",
            "appid": "123",
            "secret": "secret",
            "unified_webhook_mode": True,
            "webhook_uuid": "hook-1",
        },
        {},
        asyncio.Queue(),
    )

    run_task = asyncio.create_task(adapter.run())
    await asyncio.sleep(0)
    helper.initialize.assert_awaited_once()
    helper.start_polling.assert_not_called()

    shutdown_event.set()
    await run_task


@pytest.mark.asyncio
async def test_qqofficial_webhook_run_starts_polling_when_not_in_unified_mode(
    monkeypatch,
):
    helper = SimpleNamespace(
        initialize=AsyncMock(),
        start_polling=AsyncMock(),
        shutdown_event=asyncio.Event(),
    )

    monkeypatch.setattr(
        "astrbot.core.platform.sources.qqofficial_webhook.qo_webhook_adapter.QQOfficialWebhook",
        lambda *args, **kwargs: helper,
    )

    adapter = QQOfficialWebhookPlatformAdapter(
        {
            "id": "qq-official-webhook-test",
            "appid": "123",
            "secret": "secret",
            "unified_webhook_mode": False,
        },
        {},
        asyncio.Queue(),
    )

    await adapter.run()

    helper.initialize.assert_awaited_once()
    helper.start_polling.assert_awaited_once()
