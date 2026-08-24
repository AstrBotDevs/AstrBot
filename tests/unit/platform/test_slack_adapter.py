import asyncio
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import astrbot.api.message_components as Comp
from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageType
from astrbot.core.platform.sources.slack.client import (
    SlackSocketClient,
    SlackWebhookClient,
)
from astrbot.core.platform.sources.slack.slack_adapter import SlackAdapter
from tests.fixtures.helpers import make_platform_config

pytestmark = pytest.mark.platform


def _build_adapter(**overrides) -> SlackAdapter:
    config = {
        "id": "test_slack",
        "bot_token": "xoxb-test",
        "app_token": "xapp-test",
        "signing_secret": "secret",
        "slack_connection_mode": "socket",
    }
    config.update(overrides)
    return SlackAdapter(
        make_platform_config("slack", **config),
        {},
        asyncio.Queue(),
    )


def _slack_signature(secret: str, timestamp: str, body: bytes) -> str:
    sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
    return (
        "v0="
        + hmac.new(
            secret.encode("utf-8"),
            sig_basestring.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
    )


def test_slack_adapter_requires_required_tokens_by_mode():
    with pytest.raises(ValueError, match="Slack bot_token 是必需的"):
        SlackAdapter(
            make_platform_config(
                "slack",
                id="test_slack",
                bot_token=None,
                app_token="xapp-test",
                signing_secret="secret",
                slack_connection_mode="socket",
            ),
            {},
            asyncio.Queue(),
        )

    with pytest.raises(ValueError, match="Socket Mode 需要 app_token"):
        _build_adapter(app_token=None, slack_connection_mode="socket")

    with pytest.raises(ValueError, match="Webhook Mode 需要 signing_secret"):
        _build_adapter(signing_secret=None, slack_connection_mode="webhook")


@pytest.mark.asyncio
async def test_slack_convert_message_falls_back_when_slack_lookups_fail():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    adapter.web_client.users_info = AsyncMock(side_effect=RuntimeError("lookup failed"))
    adapter.web_client.conversations_info = AsyncMock(
        side_effect=RuntimeError("channel failed")
    )

    with patch(
        "astrbot.core.platform.sources.slack.slack_adapter.uuid.uuid4",
        return_value=SimpleNamespace(hex="generated-id"),
    ):
        result = await adapter.convert_message(
            {
                "user": "U1",
                "channel": "C1",
                "text": "hello slack",
                "ts": "1700000000.123",
            }
        )

    assert result.self_id == "B1"
    assert result.sender.user_id == "U1"
    assert result.sender.nickname == "U1"
    assert result.type is MessageType.GROUP_MESSAGE
    assert result.group_id == "C1"
    assert result.session_id == "C1"
    assert result.message_id == "generated-id"
    assert result.timestamp == 1_700_000_000
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.Plain)
    assert result.message[0].text == "hello slack"
    adapter.web_client.users_info.assert_not_awaited()
    adapter.web_client.conversations_info.assert_not_awaited()


@pytest.mark.asyncio
async def test_slack_webhook_client_background_dispatches_event_handler(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    async def _handler(_payload):
        started.set()
        await release.wait()

    client = SlackWebhookClient(
        web_client=AsyncMock(),
        signing_secret="secret",
        event_handler=_handler,
    )

    payload = {"type": "event_callback", "event": {"type": "message"}}
    body = json.dumps(payload).encode("utf-8")
    timestamp = str(int(time.time()))

    class _Req:
        headers = {
            "X-Slack-Request-Timestamp": timestamp,
            "X-Slack-Signature": _slack_signature("secret", timestamp, body),
        }

        async def get_data(self):
            return body

    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.client.time.time",
        lambda: int(timestamp),
    )

    response = await client.handle_callback(_Req())

    assert response.status_code == 200
    await asyncio.wait_for(started.wait(), timeout=1.0)
    release.set()
    if client._event_tasks:
        await asyncio.gather(*list(client._event_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_slack_socket_client_background_dispatches_event_handler():
    started = asyncio.Event()
    release = asyncio.Event()

    async def _handler(_req):
        started.set()
        await release.wait()

    client = SlackSocketClient(
        web_client=AsyncMock(),
        app_token="xapp-test",
        event_handler=_handler,
    )
    client.socket_client = SimpleNamespace(
        send_socket_mode_response=AsyncMock(),
        disconnect=AsyncMock(),
        close=AsyncMock(),
    )
    request = SimpleNamespace(envelope_id="env-1")

    await client._handle_events(AsyncMock(), request)

    client.socket_client.send_socket_mode_response.assert_awaited_once()
    await asyncio.wait_for(started.wait(), timeout=1.0)
    release.set()
    if client._event_tasks:
        await asyncio.gather(*list(client._event_tasks), return_exceptions=True)


@pytest.mark.asyncio
async def test_slack_convert_message_uses_blocks_and_attachment_parsing():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    adapter._parse_blocks = MagicMock(
        return_value=[
            Comp.Plain("Hello "),
            Comp.At(qq="U2", name="Alice"),
            Comp.Plain("world"),
        ]
    )
    adapter.get_file_base64 = AsyncMock(return_value="base64-image")

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "D1",
            "text": "ignored because blocks exist",
            "blocks": [{"type": "rich_text"}],
            "files": [
                {
                    "name": "image.png",
                    "url_private": "https://files.example.com/image",
                    "mimetype": "image/png",
                },
                {
                    "name": "notes.pdf",
                    "url_private": "https://files.example.com/notes",
                    "mimetype": "application/pdf",
                },
            ],
        }
    )

    assert result.type is MessageType.FRIEND_MESSAGE
    assert result.session_id == "U1"
    assert result.sender.nickname == "U1"
    assert result.message_str == "Hello world"
    assert isinstance(result.message[0], Comp.Plain)
    assert isinstance(result.message[1], Comp.At)
    assert isinstance(result.message[2], Comp.Plain)
    assert isinstance(result.message[3], Comp.Image)
    assert isinstance(result.message[4], Comp.File)
    assert result.message[3].file == ""
    assert result.message[4].url == ""
    assert result.message[4].file_ == ""
    adapter._parse_blocks.assert_called_once_with([{"type": "rich_text"}])
    adapter.get_file_base64.assert_not_awaited()

    await result.message[3]._resolve_deferred_source()

    adapter.get_file_base64.assert_awaited_once_with("https://files.example.com/image")
    assert result.message[3].file == "base64://base64-image"


class _FakeSlackFileResponse:
    def __init__(
        self,
        *,
        status: int = 200,
        body: bytes = b"payload",
        headers: dict[str, str] | None = None,
        text: str = "ok",
        chunks: list[bytes] | None = None,
    ):
        self.status = status
        self._body = body
        self.headers = headers or {}
        self._text = text
        self._chunks = chunks if chunks is not None else [body]
        self.content = SimpleNamespace(iter_chunked=self._iter_chunked)

    async def read(self):
        return self._body

    async def text(self):
        return self._text

    async def _iter_chunked(self, _size: int):
        for chunk in self._chunks:
            yield chunk

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeSlackFileSession:
    def __init__(self, response: _FakeSlackFileResponse):
        self.response = response
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    def get(self, url, headers=None):
        self.calls.append((url, headers))
        return self.response

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_slack_non_image_file_downloads_lazily_with_bearer(monkeypatch, tmp_path):
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    session = _FakeSlackFileSession(_FakeSlackFileResponse(body=b"pdf-bytes"))
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "D1",
            "text": "notes",
            "files": [
                {
                    "name": "notes.pdf",
                    "url_private": "https://files.example.com/notes",
                    "mimetype": "application/pdf",
                },
            ],
        }
    )

    file_component = next(c for c in result.message if isinstance(c, Comp.File))
    assert file_component.url == ""
    assert file_component.file_ == ""
    assert session.calls == []

    path = await file_component.get_file()

    assert session.calls == [
        (
            "https://files.example.com/notes",
            {"Authorization": "Bearer xoxb-test"},
        )
    ]
    assert path
    assert Path(path).read_bytes() == b"pdf-bytes"
    assert file_component.url == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403])
async def test_slack_non_image_file_auth_failure_does_not_backfill_url(
    monkeypatch, tmp_path, status
):
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    session = _FakeSlackFileSession(
        _FakeSlackFileResponse(status=status, text="forbidden")
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "D1",
            "text": "notes",
            "files": [
                {
                    "name": "notes.pdf",
                    "url_private": "https://files.example.com/notes",
                    "mimetype": "application/pdf",
                },
            ],
        }
    )
    file_component = next(c for c in result.message if isinstance(c, Comp.File))

    path = await file_component.get_file()

    assert path == ""
    assert file_component.url == ""
    assert file_component.file_ == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_slack_non_image_file_oversize_download_is_rejected(
    monkeypatch, tmp_path
):
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter._SLACK_FILE_MAX_BYTES",
        8,
    )
    session = _FakeSlackFileSession(
        _FakeSlackFileResponse(body=b"0123456789", chunks=[b"0123456789"])
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "D1",
            "text": "notes",
            "files": [
                {
                    "name": "notes.pdf",
                    "url_private": "https://files.example.com/notes",
                    "mimetype": "application/pdf",
                },
            ],
        }
    )
    file_component = next(c for c in result.message if isinstance(c, Comp.File))

    path = await file_component.get_file()

    assert path == ""
    assert file_component.url == ""
    assert file_component.file_ == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_slack_non_image_file_oversize_content_length_is_rejected(
    monkeypatch, tmp_path
):
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    session = _FakeSlackFileSession(
        _FakeSlackFileResponse(
            headers={"Content-Length": str(32 * 1024 * 1024 + 1)},
            body=b"should-not-be-written",
        )
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.aiohttp.ClientSession",
        lambda: session,
    )
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.get_astrbot_temp_path",
        lambda: str(tmp_path),
    )

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "D1",
            "text": "notes",
            "files": [
                {
                    "name": "notes.pdf",
                    "url_private": "https://files.example.com/notes",
                    "mimetype": "application/pdf",
                },
            ],
        }
    )

    file_component = next(c for c in result.message if isinstance(c, Comp.File))
    path = await file_component.get_file()

    assert path == ""
    assert file_component.url == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_slack_convert_message_parses_mentions_and_mention_lookup_failures():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"
    adapter.web_client.users_info = AsyncMock()

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "C2",
            "text": "<@U2> hi there",
            "client_msg_id": "msg-1",
        }
    )

    assert result.type is MessageType.GROUP_MESSAGE
    assert result.group_id == "C2"
    assert result.message_str == "<@U2> hi there"
    assert len(result.message) == 2
    assert isinstance(result.message[0], Comp.At)
    assert result.message[0].qq == "U2"
    assert result.message[0].name == ""
    assert isinstance(result.message[1], Comp.Plain)
    assert result.message[1].text == "hi there"
    adapter.web_client.users_info.assert_not_awaited()


def test_slack_parse_blocks_handles_rich_text_lists_and_markdown_sections():
    adapter = _build_adapter()

    components = adapter._parse_blocks(
        [
            {
                "type": "rich_text",
                "elements": [
                    {
                        "type": "rich_text_section",
                        "elements": [
                            {"type": "text", "text": "Hello "},
                            {"type": "user", "user_id": "U2"},
                            {"type": "channel", "channel_id": "C1"},
                            {
                                "type": "link",
                                "url": "https://example.com",
                                "text": "doc",
                            },
                            {"type": "emoji", "name": "wave"},
                        ],
                    },
                    {
                        "type": "rich_text_list",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "first"}],
                            },
                            {
                                "type": "rich_text_section",
                                "elements": [{"type": "text", "text": "second"}],
                            },
                        ],
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "*bold*"},
            },
        ]
    )

    assert len(components) == 5
    assert isinstance(components[0], Comp.Plain)
    assert components[0].text == "Hello "
    assert isinstance(components[1], Comp.At)
    assert components[1].qq == "U2"
    assert isinstance(components[2], Comp.Plain)
    assert components[2].text == "#C1[doc](https://example.com):wave:"
    assert isinstance(components[3], Comp.Plain)
    assert components[3].text == "• first\n• second"
    assert isinstance(components[4], Comp.Plain)
    assert components[4].text == "*bold*"


@pytest.mark.asyncio
async def test_slack_handle_socket_event_filters_noise_and_forwards_valid_message():
    adapter = _build_adapter()
    converted = object()
    adapter.convert_message = AsyncMock(return_value=converted)
    adapter.handle_msg = AsyncMock()

    ignored_requests = [
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "message", "subtype": "bot_message"}},
        ),
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "message_changed"}},
        ),
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "message", "bot_id": "B2"}},
        ),
        SimpleNamespace(
            type="events_api",
            payload={"event": {"type": "reaction_added"}},
        ),
        SimpleNamespace(type="disconnect", payload={"event": {"type": "message"}}),
    ]

    for request in ignored_requests:
        await adapter._handle_socket_event(request)

    valid_request = SimpleNamespace(
        type="events_api",
        payload={"event": {"type": "app_mention", "text": "hello", "user": "U1"}},
    )
    await adapter._handle_socket_event(valid_request)

    adapter.convert_message.assert_awaited_once_with(valid_request.payload["event"])
    adapter.handle_msg.assert_awaited_once_with(converted)


@pytest.mark.asyncio
async def test_slack_send_by_session_uses_group_channel_suffix_and_blocks():
    adapter = _build_adapter()
    adapter.web_client.chat_postMessage = AsyncMock()

    with patch(
        "astrbot.core.platform.sources.slack.slack_adapter.SlackMessageEvent._parse_slack_blocks",
        AsyncMock(return_value=([{"type": "section"}], "")),
    ):
        await adapter.send_by_session(
            SimpleNamespace(
                message_type=MessageType.GROUP_MESSAGE,
                session_id="slack_C123",
            ),
            MessageChain().message("hello"),
        )

    adapter.web_client.chat_postMessage.assert_awaited_once_with(
        channel="C123",
        text="",
        blocks=[{"type": "section"}],
    )


@pytest.mark.asyncio
async def test_slack_send_by_session_uses_dm_session_id_directly():
    adapter = _build_adapter()
    adapter.web_client.chat_postMessage = AsyncMock()

    with patch(
        "astrbot.core.platform.sources.slack.slack_adapter.SlackMessageEvent._parse_slack_blocks",
        AsyncMock(return_value=([], "hello direct")),
    ):
        await adapter.send_by_session(
            SimpleNamespace(
                message_type=MessageType.FRIEND_MESSAGE,
                session_id="U123",
            ),
            MessageChain().message("hello"),
        )

    adapter.web_client.chat_postMessage.assert_awaited_once_with(
        channel="U123",
        text="hello direct",
        blocks=None,
    )


@pytest.mark.asyncio
async def test_slack_convert_message_uses_group_fallback_when_conversation_lookup_fails():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "C-fallback",
            "text": "fallback group",
            "client_msg_id": "msg-1",
        }
    )

    assert result.type is MessageType.GROUP_MESSAGE
    assert result.group_id == "C-fallback"
    assert result.session_id == "C-fallback"
    assert result.message[0].text == "fallback group"


@pytest.mark.asyncio
async def test_slack_convert_message_keeps_whitespace_only_text_out_of_components():
    adapter = _build_adapter()
    adapter.bot_self_id = "B1"

    result = await adapter.convert_message(
        {
            "user": "U1",
            "channel": "C2",
            "text": "<@U2>   ",
            "client_msg_id": "msg-2",
        }
    )

    assert result.message_str == "<@U2>   "
    assert len(result.message) == 1
    assert isinstance(result.message[0], Comp.At)
    assert result.message[0].qq == "U2"


@pytest.mark.asyncio
async def test_slack_handle_webhook_event_ignores_noise_and_forwards_message():
    adapter = _build_adapter(slack_connection_mode="webhook")
    adapter.convert_message = AsyncMock(return_value="converted")
    adapter.handle_msg = AsyncMock()

    ignored_events = [
        {"event": {"type": "message", "subtype": "bot_message"}},
        {"event": {"type": "message_changed"}},
        {"event": {"type": "message", "bot_id": "B2"}},
        {"event": {"type": "reaction_added"}},
    ]

    for payload in ignored_events:
        await adapter._handle_webhook_event(payload)

    valid_payload = {"event": {"type": "message", "text": "hello", "user": "U1"}}
    await adapter._handle_webhook_event(valid_payload)

    adapter.convert_message.assert_awaited_once_with(valid_payload["event"])
    adapter.handle_msg.assert_awaited_once_with("converted")


@pytest.mark.asyncio
async def test_slack_get_file_base64_returns_base64_for_success(monkeypatch):
    adapter = _build_adapter()

    class FakeResponse:
        status = 200
        headers: dict[str, str] = {}

        async def read(self):
            return b"file-bytes"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def __init__(self, *args, **kwargs):
            self.calls = []

        def get(self, url, headers=None):
            self.calls.append((url, headers))
            return FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    fake_session = FakeSession()
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.aiohttp.ClientSession",
        lambda: fake_session,
    )

    encoded = await adapter.get_file_base64("https://files.example.com/private")

    assert encoded == base64.b64encode(b"file-bytes").decode("utf-8")
    assert fake_session.calls == [
        (
            "https://files.example.com/private",
            {"Authorization": "Bearer xoxb-test"},
        )
    ]


@pytest.mark.asyncio
async def test_slack_get_file_base64_raises_on_non_200(monkeypatch):
    adapter = _build_adapter()

    class FakeResponse:
        status = 403
        headers: dict[str, str] = {}

        async def text(self):
            return "forbidden"

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeSession:
        def get(self, url, headers=None):
            return FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.aiohttp.ClientSession",
        lambda: FakeSession(),
    )

    with pytest.raises(Exception, match="下载文件失败: 403"):
        await adapter.get_file_base64("https://files.example.com/private")


@pytest.mark.asyncio
async def test_slack_webhook_callback_rejects_non_webhook_mode():
    adapter = _build_adapter(slack_connection_mode="socket")

    result = await adapter.webhook_callback(SimpleNamespace())

    assert result == ({"error": "Slack adapter is not in webhook mode"}, 400)


@pytest.mark.asyncio
async def test_slack_webhook_callback_delegates_to_webhook_client():
    adapter = _build_adapter(slack_connection_mode="webhook")
    adapter.webhook_client = SimpleNamespace(
        handle_callback=AsyncMock(return_value={"ok": True})
    )

    result = await adapter.webhook_callback(SimpleNamespace(method="POST"))

    assert result == {"ok": True}
    adapter.webhook_client.handle_callback.assert_awaited_once()


def test_slack_unified_webhook_requires_webhook_mode_and_uuid():
    webhook_adapter = _build_adapter(
        slack_connection_mode="webhook",
        unified_webhook_mode=True,
        webhook_uuid="uuid-1",
    )
    socket_adapter = _build_adapter(
        slack_connection_mode="socket",
        unified_webhook_mode=True,
        webhook_uuid="uuid-1",
    )
    missing_uuid_adapter = _build_adapter(
        slack_connection_mode="webhook",
        unified_webhook_mode=True,
        webhook_uuid=None,
    )

    assert webhook_adapter.unified_webhook() is True
    assert socket_adapter.unified_webhook() is False
    assert missing_uuid_adapter.unified_webhook() is False


@pytest.mark.asyncio
async def test_slack_run_starts_socket_client(monkeypatch):
    adapter = _build_adapter(slack_connection_mode="socket")
    start = AsyncMock()
    socket_clients = []

    class FakeSocketClient:
        def __init__(self, web_client, app_token, handler):
            socket_clients.append((web_client, app_token, handler))
            self.start = start

    adapter.get_bot_user_id = AsyncMock(return_value="B1")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.SlackSocketClient",
        FakeSocketClient,
    )

    await adapter.run()

    assert adapter.bot_self_id == "B1"
    assert len(socket_clients) == 1
    assert socket_clients[0][1] == "xapp-test"
    start.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_run_waits_on_unified_webhook_mode(monkeypatch):
    adapter = _build_adapter(
        slack_connection_mode="webhook",
        unified_webhook_mode=True,
        webhook_uuid="uuid-1",
    )
    waiter = AsyncMock()
    webhook_clients = []

    class FakeWebhookClient:
        def __init__(self, web_client, signing_secret, host, port, path, handler):
            webhook_clients.append((signing_secret, host, port, path, handler))
            self.shutdown_event = SimpleNamespace(wait=waiter)
            self.start = AsyncMock()

    adapter.get_bot_user_id = AsyncMock(return_value="B1")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.SlackWebhookClient",
        FakeWebhookClient,
    )

    await adapter.run()

    assert adapter.bot_self_id == "B1"
    assert len(webhook_clients) == 1
    assert webhook_clients[0][:4] == (
        "secret",
        "127.0.0.1",
        3000,
        "/astrbot-slack-webhook/callback",
    )
    waiter.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_run_starts_webhook_server_when_not_unified(monkeypatch):
    adapter = _build_adapter(
        slack_connection_mode="webhook", unified_webhook_mode=False
    )
    start = AsyncMock()

    class FakeWebhookClient:
        def __init__(self, web_client, signing_secret, host, port, path, handler):
            self.shutdown_event = SimpleNamespace(wait=AsyncMock())
            self.start = start

    adapter.get_bot_user_id = AsyncMock(return_value="B1")
    monkeypatch.setattr(
        "astrbot.core.platform.sources.slack.slack_adapter.SlackWebhookClient",
        FakeWebhookClient,
    )

    await adapter.run()

    start.assert_awaited_once()


@pytest.mark.asyncio
async def test_slack_terminate_stops_socket_and_webhook_clients():
    adapter = _build_adapter()
    adapter.socket_client = SimpleNamespace(stop=AsyncMock())
    adapter.webhook_client = SimpleNamespace(stop=AsyncMock())

    await adapter.terminate()

    adapter.socket_client.stop.assert_awaited_once()
    adapter.webhook_client.stop.assert_awaited_once()


def test_slack_create_event_does_not_promote_workspace_admin():
    from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember

    adapter = _build_adapter()
    message = AstrBotMessage()
    message.type = MessageType.GROUP_MESSAGE
    message.group_id = "C123"
    message.session_id = "C123"
    message.sender = MessageMember("U1", "tester")
    message.raw_message = {"user": "U1", "channel": "C123", "is_admin": True}
    message.message_str = "hello"
    message.message = []
    event = adapter.create_event(message)
    assert event.platform_member_role == "member"
    assert event.platform_role_source == "none"
